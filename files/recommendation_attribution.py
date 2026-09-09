from django.core import signing
from django.core.cache import cache


ATTRIBUTION_SALT = "mediacms.recommendation-attribution.v1"
ATTRIBUTION_MAX_AGE_SECONDS = 60 * 60 * 24
ATTRIBUTION_CACHE_SECONDS = 60 * 30


def _cache_key(user, video_id):
    return f"recommendation-attribution:{user.pk}:{video_id}"


def remember_recommendation_attribution(user, video_id, token):
    cache.set(_cache_key(user, video_id), token, ATTRIBUTION_CACHE_SECONDS)


def get_remembered_recommendation_attribution(user, video_id):
    if not user.is_authenticated:
        return None
    return cache.get(_cache_key(user, video_id))


def create_recommendation_attribution(user, media, context):
    """Create a signed, short-lived token that survives navigation to the player."""
    return signing.dumps(
        {
            "user_id": user.pk,
            "video_id": media.friendly_token,
            "recommendation_request_id": context["recommendation_request_id"],
            "algorithm_id": context["algorithm_id"],
            "algorithm_version": context.get("algorithm_version", ""),
            "recommendation_rank": context["recommendation_rank"],
        },
        salt=ATTRIBUTION_SALT,
        compress=True,
    )


def read_recommendation_attribution(token, user, video_id):
    """Return verified attribution data, or None for stale/tampered/mismatched data."""
    if not token:
        return None
    try:
        data = signing.loads(
            token,
            salt=ATTRIBUTION_SALT,
            max_age=ATTRIBUTION_MAX_AGE_SECONDS,
        )
    except signing.BadSignature:
        return None
    if data.get("user_id") != user.pk or data.get("video_id") != video_id:
        return None
    return data
