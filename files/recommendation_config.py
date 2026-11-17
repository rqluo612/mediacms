"""Recommendation configuration validation (no model imports)."""

import math

from django.core.exceptions import ImproperlyConfigured


def resolve_strategy(value, enabled=False):
    if value is None or value == "":
        return "cf" if enabled else "legacy"
    if value not in ("cf", "content", "legacy"):
        raise ImproperlyConfigured("RECOMMENDATION_STRATEGY must be empty, cf, content or legacy")
    return value


def content_parameters(alpha, weights):
    try:
        alpha = float(alpha)
        weights = {name: float(weights.get(name, 0)) for name in ("watch", "like", "playlist")}
        if not math.isfinite(alpha) or not 0 <= alpha <= 1:
            raise ValueError
        if any(not math.isfinite(w) or w < 0 for w in weights.values()):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ImproperlyConfigured("CONTENT alpha must be 0..1 and behavior weights finite and nonnegative")
    return alpha, weights
