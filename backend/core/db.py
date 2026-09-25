"""PostgreSQL advisory locks that stay correct behind PgBouncer."""
from contextlib import contextmanager

from django.conf import settings
from django.core.management.base import CommandError
from django.db import DEFAULT_DB_ALIAS, connections

DIRECT_ALIAS = 'direct'


def session_alias(default=DEFAULT_DB_ALIAS):
    """The alias to hold a session-level lock on.

    A session lock must stay on one server connection for its whole life,
    which PgBouncer's transaction mode doesn't guarantee (the unlock could
    reach another connection and the lock would leak). Behind the pooler the
    lock therefore goes through DIRECT_DATABASE_URL.
    """
    if DIRECT_ALIAS in settings.DATABASES:
        return DIRECT_ALIAS
    if settings.DB_BEHIND_POOLER and connections[default].vendor == 'postgresql':
        raise CommandError(
            'DATABASE_URL points at PgBouncer (PGBOUNCER/DB_POOLER is set): set DIRECT_DATABASE_URL '
            'to the database itself so migrations and scheduled jobs can take their advisory lock.'
        )
    return default


@contextmanager
def advisory_lock(lock_id, *, alias=None, wait=True):
    """Hold ``pg_advisory_lock(lock_id)`` for the block; yields False if ``wait=False`` and it is taken.

    Other databases (SQLite in development) have no advisory locks: the block
    just runs.
    """
    connection = connections[alias or session_alias()]
    if connection.vendor != 'postgresql':
        yield True
        return
    with connection.cursor() as cursor:
        if wait:
            cursor.execute('SELECT pg_advisory_lock(%s)', [lock_id])
            acquired = True
        else:
            cursor.execute('SELECT pg_try_advisory_lock(%s)', [lock_id])
            acquired = cursor.fetchone()[0]
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_unlock(%s)', [lock_id])
