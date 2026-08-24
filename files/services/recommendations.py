"""Collaborative-filtering recommendation strategy and cache helpers."""

import logging
import math
from collections import defaultdict
from itertools import combinations

from django.conf import settings
from django.core.cache import cache

from actions.models import MediaAction

from ..methods import show_recommended_media
from ..models import Media, PlaylistMedia

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {"watch": 1.0, "like": 3.0, "playlist": 4.0}


def _algorithm_version():
    return getattr(settings, "COLLABORATIVE_FILTERING_ALGORITHM_VERSION", "item_cf_v1")


def _similarities_cache_key():
    return f"recommendations:{_algorithm_version()}:similarities"


def _user_cache_key(user_id):
    return f"recommendations:{_algorithm_version()}:user:{user_id}"


def _weights():
    configured = getattr(settings, "COLLABORATIVE_FILTERING_WEIGHTS", DEFAULT_WEIGHTS)
    return {key: float(value) for key, value in configured.items() if float(value) > 0}


def build_interaction_matrix():
    """Return a sparse {user_id: {media_id: implicit_score}} matrix."""
    weights = _weights()
    matrix = defaultdict(lambda: defaultdict(float))
    seen_actions = set()

    enabled_actions = [action for action in ("watch", "like") if action in weights]
    actions = (
        MediaAction.objects.filter(user_id__isnull=False, action__in=enabled_actions)
        .values_list("user_id", "media_id", "action")
        .iterator()
    )
    for user_id, media_id, action in actions:
        key = (user_id, media_id, action)
        if key not in seen_actions:
            matrix[user_id][media_id] += weights[action]
            seen_actions.add(key)

    if "playlist" in weights:
        seen_playlist_items = set()
        playlist_items = PlaylistMedia.objects.values_list("playlist__user_id", "media_id").iterator()
        for user_id, media_id in playlist_items:
            key = (user_id, media_id)
            if key not in seen_playlist_items:
                matrix[user_id][media_id] += weights["playlist"]
                seen_playlist_items.add(key)

    return {user_id: dict(items) for user_id, items in matrix.items()}


def calculate_item_similarities(interaction_matrix, max_similar_items=None):
    """Calculate sparse item cosine similarities from a user-item matrix."""
    max_similar_items = max_similar_items or getattr(
        settings, "COLLABORATIVE_FILTERING_MAX_SIMILAR_ITEMS", 100
    )
    norms = defaultdict(float)
    dot_products = defaultdict(float)

    for media_scores in interaction_matrix.values():
        items = sorted(media_scores.items())
        for media_id, score in items:
            norms[media_id] += score * score
        for (left_id, left_score), (right_id, right_score) in combinations(items, 2):
            dot_products[(left_id, right_id)] += left_score * right_score

    similarities = defaultdict(list)
    for (left_id, right_id), dot_product in dot_products.items():
        denominator = math.sqrt(norms[left_id]) * math.sqrt(norms[right_id])
        if not denominator:
            continue
        similarity = dot_product / denominator
        if similarity <= 0:
            continue
        similarities[left_id].append((right_id, similarity))
        similarities[right_id].append((left_id, similarity))

    result = {}
    for media_id, related in similarities.items():
        result[media_id] = sorted(related, key=lambda item: (-item[1], item[0]))[
            :max_similar_items
        ]
    return result


def build_and_cache_item_similarities():
    """Build item similarities and cache only primitive Python structures."""
    matrix = build_interaction_matrix()
    similarities = calculate_item_similarities(matrix)
    timeout = getattr(settings, "COLLABORATIVE_FILTERING_CACHE_TIMEOUT", 60 * 60 * 12)
    cache.set(_similarities_cache_key(), similarities, timeout)
    logger.info(
        "Collaborative-filtering similarities cached",
        extra={"users": len(matrix), "items": len(similarities), "algorithm": _algorithm_version()},
    )
    return similarities


def get_user_interactions(user):
    """Return positive implicit scores and all media that should be excluded."""
    weights = _weights()
    scores = defaultdict(float)
    excluded = set()

    actions = MediaAction.objects.filter(user=user).values_list("media_id", "action")
    for media_id, action in actions:
        if action in ("watch", "like") and action in weights:
            scores[media_id] += weights[action]
            excluded.add(media_id)
        elif action == "dislike":
            excluded.add(media_id)

    if "playlist" in weights:
        playlist_media_ids = PlaylistMedia.objects.filter(
            playlist__user=user
        ).values_list("media_id", flat=True).distinct()
        for media_id in playlist_media_ids:
            scores[media_id] += weights["playlist"]
            excluded.add(media_id)

    return dict(scores), excluded


def score_candidates(interactions, similarities):
    """Score unseen candidates from a user's interactions and item similarities."""
    scores = defaultdict(float)
    for media_id, interaction_score in interactions.items():
        for candidate_id, similarity in similarities.get(media_id, ()):
            scores[candidate_id] += interaction_score * similarity
    return dict(scores)


def _rank_candidates(candidate_scores, excluded_ids, limit):
    candidate_ids = set(candidate_scores).difference(excluded_ids)
    media = Media.objects.filter(id__in=candidate_ids, listable=True).prefetch_related(
        "user", "tags"
    )
    media_by_id = {item.id: item for item in media}
    ranked_ids = sorted(
        media_by_id,
        key=lambda media_id: (
            -candidate_scores[media_id],
            -(media_by_id[media_id].add_date.timestamp() if media_by_id[media_id].add_date else 0),
            -media_by_id[media_id].views,
            media_id,
        ),
    )
    return [media_by_id[media_id] for media_id in ranked_ids[:limit]]


def get_collaborative_recommendations(
    user, limit=50, interactions=None, excluded_ids=None
):
    """Return personalized public media, or an empty list when data is insufficient."""
    if interactions is None or excluded_ids is None:
        interactions, excluded_ids = get_user_interactions(user)

    cached_ids = cache.get(_user_cache_key(user.id))
    if cached_ids is not None:
        media_by_id = {
            item.id: item
            for item in Media.objects.filter(id__in=cached_ids, listable=True).prefetch_related(
                "user", "tags"
            )
        }
        return [media_by_id[media_id] for media_id in cached_ids if media_id in media_by_id][
            :limit
        ]

    minimum = getattr(settings, "COLLABORATIVE_FILTERING_MIN_INTERACTIONS", 3)
    if len(interactions) < minimum:
        return []

    similarities = cache.get(_similarities_cache_key())
    if not similarities:
        return []

    candidate_scores = score_candidates(interactions, similarities)
    result = _rank_candidates(candidate_scores, excluded_ids, limit)
    timeout = getattr(settings, "COLLABORATIVE_FILTERING_USER_CACHE_TIMEOUT", 15 * 60)
    cache.set(_user_cache_key(user.id), [item.id for item in result], timeout)
    return result


def _fill_with_fallback(personalized, request, excluded_ids, limit):
    result = []
    seen = set(excluded_ids)
    for media in personalized:
        if media.id not in seen:
            result.append(media)
            seen.add(media.id)

    if len(result) < limit:
        fallback = show_recommended_media(request, limit=max(100, limit * 3))
        for media in fallback:
            if media.id in seen:
                continue
            result.append(media)
            seen.add(media.id)
            if len(result) >= limit:
                break
    return result


def get_recommended_media(request, limit=50):
    """Recommendation strategy entry point with safe fallback to legacy behavior."""
    if not getattr(settings, "ENABLE_COLLABORATIVE_FILTERING", False):
        return show_recommended_media(request, limit=limit)
    if not request.user.is_authenticated:
        return show_recommended_media(request, limit=limit)

    try:
        interactions, excluded_ids = get_user_interactions(request.user)
        personalized = get_collaborative_recommendations(
            request.user, limit=limit, interactions=interactions, excluded_ids=excluded_ids
        )
        return _fill_with_fallback(personalized, request, excluded_ids, limit)
    except Exception:
        logger.exception(
            "Collaborative recommendation failed; using legacy fallback",
            extra={"algorithm": _algorithm_version()},
        )
        return show_recommended_media(request, limit=limit)
