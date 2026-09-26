"""Liveness (`/api/health/`) and readiness (`/api/health/ready/`) probes."""
import logging
import secrets

from django.core.cache import cache
from django.db import connection, transaction
from django.http import JsonResponse

logger = logging.getLogger('naseeb.health')
DATABASE_TIMEOUT_MS = 2000


def _no_store(response):
    response['Cache-Control'] = 'no-store'
    return response


def health_check(request):
    """Liveness: the process answers. Touches neither the database nor the cache."""
    return _no_store(JsonResponse({'status': 'ok', 'service': 'naseeb-edu'}))


def _check_database():
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute('SET LOCAL statement_timeout = %s', [DATABASE_TIMEOUT_MS])
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return 'ok'
    except Exception as exc:  # a probe reports failures, it never raises them
        logger.warning('readiness_database_failed error=%s', exc.__class__.__name__)
        return 'error'


def _check_cache():
    # The cache client's own socket timeouts (REDIS_*_TIMEOUT) bound this.
    token = secrets.token_hex(8)
    try:
        cache.set('health:ready', token, 10)
        return 'ok' if cache.get('health:ready') == token else 'error'
    except Exception as exc:
        logger.warning('readiness_cache_failed error=%s', exc.__class__.__name__)
        return 'error'


def readiness_check(request):
    """Readiness: the database answers, and whether the shared cache does.

    Only the database decides the status code. Throttles and budgets fail
    open without the cache, so a Redis outage reports ``degraded`` with 200
    instead of taking every instance out of rotation at once.
    """
    checks = {'database': _check_database(), 'cache': _check_cache()}
    if checks['database'] != 'ok':
        overall, code = 'unavailable', 503
    else:
        overall, code = ('ok' if checks['cache'] == 'ok' else 'degraded'), 200
    return _no_store(JsonResponse({'status': overall, 'checks': checks}, status=code))
