"""Limits for long-lived AI streams.

A streaming reply holds a gunicorn thread for up to AI_STREAM_MAX_SECONDS.
Without a cap, a burst of chats could occupy every thread of a worker and
starve ordinary requests, so each process serves at most
AI_MAX_STREAMS_PER_PROCESS streams at once and each user at most
AI_USER_MAX_CONCURRENT_STREAMS (counted in the shared cache; fails open).
"""
import threading

from django.conf import settings
from django.db import connection

from apps.users.cache_safety import cache_decrement, cache_increment

_lock = threading.Lock()
_semaphore = None
_semaphore_size = None


def _process_semaphore():
    global _semaphore, _semaphore_size
    size = max(0, settings.AI_MAX_STREAMS_PER_PROCESS)
    with _lock:
        if _semaphore is None or _semaphore_size != size:
            # Slots already taken are released on the semaphore they came from.
            _semaphore, _semaphore_size = threading.BoundedSemaphore(size) if size else None, size
        return _semaphore


class StreamSlot:
    """One process slot plus one per-user slot; ``release()`` is idempotent."""

    def __init__(self, semaphore, user_key):
        self._semaphore = semaphore
        self._user_key = user_key
        self._released = False
        self._release_lock = threading.Lock()

    def release(self):
        with self._release_lock:
            if self._released:
                return
            self._released = True
        if self._user_key:
            cache_decrement(self._user_key)
        self._semaphore.release()


def acquire_stream_slot(user):
    """Return ``(slot, None)``, or ``(None, 'busy' | 'user_limit')`` when a cap is reached."""
    semaphore = _process_semaphore()
    if semaphore is None or not semaphore.acquire(blocking=False):
        return None, 'busy'
    user_key = None
    limit = settings.AI_USER_MAX_CONCURRENT_STREAMS
    if limit > 0:
        user_key = f'ai-streams:{user.pk}'
        # The TTL only matters if a process dies mid-stream without releasing.
        count = cache_increment(user_key, settings.AI_STREAM_MAX_SECONDS + 30)
        if count is None:
            user_key = None  # cache down: the process cap still applies
        elif count > limit:
            cache_decrement(user_key)
            semaphore.release()
            return None, 'user_limit'
    return StreamSlot(semaphore, user_key), None


class GuardedStream:
    """Wrap a streaming body so ``on_close`` runs exactly once, even if the
    client disconnects before the first chunk (a generator that never started
    does not run its ``finally`` on close)."""

    def __init__(self, iterable, on_close):
        self._iterable = iterable
        self._iterator = iter(iterable)
        self._on_close = on_close

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iterator)

    def close(self):
        try:
            close = getattr(self._iterable, 'close', None)
            if close is not None:
                close()
        finally:
            self._on_close()


def release_db_connection():
    """Hand this thread's database connection back before a long stream.

    With the psycopg pool this returns it to the pool; the stream itself
    never touches the database. Inside a transaction (tests) it is left alone.
    """
    if not connection.in_atomic_block:
        connection.close()
