"""Fail-open wrappers around the shared cache (Redis).

Throttles, login lockouts and the AI budget are protections, not features: if
the cache is unreachable or misconfigured they must not turn every request
into a 500. Cache errors are logged as warnings and the request is allowed.
"""
import logging

from django.core.cache import cache, caches
from django.core.cache.backends.redis import RedisCache

try:  # redis-py is only installed where RedisCache is used
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover
    RedisError = OSError

logger = logging.getLogger('naseeb.cache')
CACHE_ERRORS = (RedisError, OSError)


def _warn(operation, exc):
    logger.warning('cache_unavailable operation=%s error=%s: failing open', operation, exc.__class__.__name__)


def cache_get(key, default=None):
    try:
        return cache.get(key, default)
    except CACHE_ERRORS as exc:
        _warn('get', exc)
        return default


def cache_set(key, value, timeout=None):
    try:
        cache.set(key, value, timeout)
    except CACHE_ERRORS as exc:
        _warn('set', exc)


def cache_set_many(mapping, timeout=None):
    try:
        cache.set_many(mapping, timeout)
    except CACHE_ERRORS as exc:
        _warn('set_many', exc)


def cache_delete_many(keys):
    try:
        cache.delete_many(keys)
    except CACHE_ERRORS as exc:
        _warn('delete_many', exc)


def _redis_backend():
    backend = caches['default']
    return backend if isinstance(backend, RedisCache) else None


def count_hit(key, timeout, *, also_read=None):
    """Add one to the counter ``key`` and optionally read another counter, atomically.

    The counter is created with ``timeout`` seconds to live on its first hit
    (later hits keep that expiry). Returns ``(count, other)``, where ``other``
    is the value of ``also_read`` (0 when missing), or ``None`` when the cache
    is down. On Redis this is one round trip (MULTI: SET NX EX, INCR, GET);
    Django's own add()+incr() would take three.
    """
    timeout = max(1, int(timeout))
    try:
        backend = _redis_backend()
        if backend is not None:
            full_key = backend.make_and_validate_key(key)
            pipe = backend._cache.get_client(full_key, write=True).pipeline(transaction=True)
            pipe.set(full_key, 0, ex=timeout, nx=True)
            pipe.incr(full_key)
            if also_read:
                pipe.get(backend.make_and_validate_key(also_read))
            results = pipe.execute()
            other = int(results[2]) if also_read and results[2] is not None else 0
            return int(results[1]), other
        if cache.add(key, 1, timeout):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:  # expired between add() and incr()
                cache.set(key, 1, timeout)
                count = 1
        other = int(cache.get(also_read) or 0) if also_read else 0
        return count, other
    except CACHE_ERRORS as exc:
        _warn('increment', exc)
        return None


def count_hits(keys, timeout):
    """Add one to each counter in ``keys`` in one atomic step; ``None`` if the cache is down."""
    timeout = max(1, int(timeout))
    try:
        backend = _redis_backend()
        if backend is not None:
            full_keys = [backend.make_and_validate_key(key) for key in keys]
            pipe = backend._cache.get_client(write=True).pipeline(transaction=True)
            for full_key in full_keys:
                pipe.set(full_key, 0, ex=timeout, nx=True)
                pipe.incr(full_key)
            return [int(value) for value in pipe.execute()[1::2]]
    except CACHE_ERRORS as exc:
        _warn('increment', exc)
        return None
    counts = []
    for key in keys:
        result = count_hit(key, timeout)
        if result is None:
            return None
        counts.append(result[0])
    return counts


# DECR only an existing key: a plain DECR on an expired key would recreate it
# without a TTL.
_DECR_IF_EXISTS = "if redis.call('exists', KEYS[1]) == 1 then return redis.call('decr', KEYS[1]) end return 0"


def cache_decrement(key):
    """Undo one :func:`count_hit` (best effort; a missing key stays missing)."""
    try:
        backend = _redis_backend()
        if backend is not None:
            full_key = backend.make_and_validate_key(key)
            backend._cache.get_client(full_key, write=True).eval(_DECR_IF_EXISTS, 1, full_key)
            return
        try:
            cache.decr(key)
        except ValueError:
            pass
    except CACHE_ERRORS as exc:
        _warn('decrement', exc)


def cache_increment(key, timeout):
    """Increment a counter (creating it with ``timeout``); ``None`` if the cache is down."""
    result = count_hit(key, timeout)
    return None if result is None else result[0]
