"""Real-time tag and TF-IDF recommendations; no recommendation cache access."""
import html
import math
import re
from collections import Counter, defaultdict

from django.conf import settings
from django.utils.html import strip_tags

from actions.models import MediaAction
from files.helpers import get_alphanumeric_and_spaces
from files.models import Media, PlaylistMedia
from files.recommendation_config import content_parameters

ALGORITHM_VERSION = "tag_text_content_v1"


def unit(vector):
    length = math.sqrt(sum(value * value for value in vector.values()))
    return {key: value / length for key, value in vector.items()} if length else {}


def tag_vector(titles):
    # Same cleaner as upload/Tag.save, without imposing new-upload length rules
    # on legacy metadata. A normalized tag is a single binary feature.
    values = {get_alphanumeric_and_spaces(title).lower() for title in titles}
    return unit({value: 1.0 for value in values if value})


def tokenize(text):
    import jieba

    text = html.unescape(strip_tags(text)).lower()
    return [word for word in jieba.cut(text) if re.fullmatch(r"[^\W_]+", word)]


def text_vectors(documents):
    """Fit one smooth IDF on all eligible public videos, including seed videos."""
    counts = {key: Counter(tokenize(text)) for key, text in documents.items()}
    frequency = Counter(word for terms in counts.values() for word in terms)
    size = len(counts)
    idf = {word: math.log((1 + size) / (1 + count)) + 1 for word, count in frequency.items()}
    return {
        key: unit({word: count * idf[word] for word, count in terms.items()})
        for key, terms in counts.items()
    }


def profile(vectors, interactions):
    result = defaultdict(float)
    total = sum(weight for key, weight in interactions.items() if vectors.get(key))
    if not total:
        return {}
    for key, weight in interactions.items():
        for feature, value in vectors.get(key, {}).items():
            result[feature] += weight * value / total
    return unit(result)


def combined_score(tag_profile, text_profile, tags, text, alpha):
    channels = [(alpha, tag_profile, tags), (1 - alpha, text_profile, text)]
    valid = [(weight, left, right) for weight, left, right in channels if weight > 0 and left and right]
    denominator = sum(weight for weight, _, _ in valid)
    if not denominator:
        return 0.0
    return sum(weight * sum(value * right.get(key, 0) for key, value in left.items())
               for weight, left, right in valid) / denominator


def user_interactions(user, weights):
    if not user.is_authenticated:
        return {}, set()
    actions = set(MediaAction.objects.filter(user=user).values_list("media_id", "action"))
    playlists = set(PlaylistMedia.objects.filter(playlist__user=user).values_list("media_id", flat=True))
    disliked = {key for key, action in actions if action == "dislike"}
    excluded = playlists | {key for key, action in actions if action in ("watch", "like", "dislike")}
    scores = defaultdict(float)
    for key, action in actions:
        if action in ("watch", "like") and key not in disliked:
            scores[key] += weights[action]
    for key in playlists - disliked:
        scores[key] += weights["playlist"]
    return {key: value for key, value in scores.items() if value > 0}, excluded


def get_content_recommendations(user, limit=50, current_media_id=None):
    alpha, weights = content_parameters(
        getattr(settings, "CONTENT_RECOMMENDATION_ALPHA", 0.5),
        getattr(settings, "CONTENT_RECOMMENDATION_WEIGHTS", {"watch": 1, "like": 3, "playlist": 4}),
    )
    if limit <= 0:
        return []
    interactions, excluded = user_interactions(user, weights)
    if current_media_id is not None:
        excluded.add(current_media_id)
    # Deliberately stricter than CF. Do not reuse this filter in the CF branch.
    catalogue = list(Media.objects.filter(
        media_type="video", state="public", is_reviewed=True,
        encoding_status="success", listable=True,
    ).select_related("user").prefetch_related("tags"))
    candidates = [media for media in catalogue if media.pk not in excluded]
    if not candidates:
        return []
    tags = {media.pk: tag_vector(tag.title for tag in media.tags.all()) for media in catalogue}
    texts = text_vectors({media.pk: media.title + " " + media.description for media in catalogue}) if interactions else {}
    tag_interest = profile(tags, interactions)
    text_interest = profile(texts, interactions)
    scores = {media.pk: combined_score(tag_interest, text_interest, tags[media.pk], texts.get(media.pk, {}), alpha)
              for media in candidates}
    matched = [media for media in candidates if scores[media.pk] > 0]
    if matched:
        result = sorted(matched, key=lambda media: (-scores[media.pk], -(media.add_date.timestamp() if media.add_date else 0), media.pk))[:limit]
        algorithm, version = "CONTENT", ALGORITHM_VERSION
    else:
        result = sorted(candidates, key=lambda media: (-media.views, -media.likes, -(media.add_date.timestamp() if media.add_date else 0), media.pk))[:limit]
        algorithm, version = "LEGACY", ""
    for media in result:
        media.recommendation_algorithm_id = algorithm
        media.recommendation_algorithm_version = version
    return result
