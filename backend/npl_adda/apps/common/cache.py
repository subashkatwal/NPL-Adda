"""Small read-through cache helper for expensive, public, non-personal API reads."""
from django.core.cache import cache


def cached(key, ttl, compute):
    """
    Return the cached value for ``key`` or compute, store and return it.

    Only use for data identical for every caller (no per-user fields). Staleness is
    bounded by ``ttl``; writes are not invalidated explicitly.
    """
    value = cache.get(key)
    if value is None:
        value = compute()
        cache.set(key, value, ttl)
    return value
