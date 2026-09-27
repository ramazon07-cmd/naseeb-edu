from core.storage_config import S3_STORAGE, STORAGE_BACKENDS

VALID_APP_ENVIRONMENTS = {'development', 'test', 'production'}
INSECURE_SECRET_KEYS = {
    '',
    'change-me-to-a-long-random-secret',
    'dev-only-naseeb-secret-key-change-in-production',
    'dev-only-rbis-secret-key-change-in-production',
    'local-docker-secret-change-me',
    'ci-only-secret',
}
# Placeholder fragments copied from example env files must never reach production.
INSECURE_SECRET_MARKERS = ('replace', 'example', 'change-me', 'changeme', 'change_me', 'dev-only', 'insecure')
TRUTHY = {'1', 'true', 'yes', 'on'}


def is_insecure_secret_key(secret_key):
    value = str(secret_key or '')
    lowered = value.lower()
    return (
        value in INSECURE_SECRET_KEYS
        or len(value) < 32
        or any(marker in lowered for marker in INSECURE_SECRET_MARKERS)
    )


def resolve_app_environment(value, *, hosted=False, debug_requested=False, running_tests=False):
    """Resolve APP_ENV, failing closed to production when nothing says otherwise.

    An explicit APP_ENV always wins. Without one, only the test runner or an
    explicit ``DEBUG=True`` on a non-hosted machine selects a non-production
    mode; everything else (including a hosted runtime) is production.
    """
    normalized = str(value or '').strip().lower()
    if normalized:
        return normalized
    if hosted:
        return 'production'
    if running_tests:
        return 'test'
    if str(debug_requested).strip().lower() in TRUTHY:
        return 'development'
    return 'production'


def validate_runtime_environment(
    *,
    app_env,
    debug,
    secret_key,
    database_url,
    demo_accounts_enabled,
    hosted=False,
):
    """Return configuration errors that must stop a production deployment."""
    errors = []
    if app_env not in VALID_APP_ENVIRONMENTS:
        errors.append(f'APP_ENV must be one of: {", ".join(sorted(VALID_APP_ENVIRONMENTS))}.')
        return errors

    if hosted and app_env != 'production':
        errors.append('Hosted deployments must set APP_ENV=production; ephemeral SQLite data is not allowed.')
    if app_env != 'production':
        return errors

    if debug:
        errors.append('DEBUG must be False in production.')
    if is_insecure_secret_key(secret_key):
        errors.append('SECRET_KEY must be a unique production secret of at least 32 characters.')
    if not database_url:
        errors.append('DATABASE_URL is required in production; local SQLite is development-only.')
    elif database_url.lower().startswith('sqlite'):
        errors.append('SQLite is not allowed in production; configure PostgreSQL DATABASE_URL.')
    if demo_accounts_enabled:
        errors.append('ENABLE_DEMO_ACCOUNTS must be False in production.')
    return errors


def validate_storage_environment(
    *,
    app_env,
    backend,
    bucket='',
    access_key='',
    secret_key='',
    media_root='',
    document_storage_root='',
    single_instance=False,
):
    """Return file-storage configuration errors.

    Object storage needs a bucket in every environment. Production on the local
    disk is refused unless FILE_STORAGE_SINGLE_INSTANCE acknowledges that only
    one instance can ever run (a second one would not see the first one's files).
    """
    if backend not in STORAGE_BACKENDS:
        return [f'STORAGE_BACKEND must be one of: {", ".join(STORAGE_BACKENDS)}.']
    errors = []
    if backend == S3_STORAGE:
        if not bucket:
            errors.append('AWS_STORAGE_BUCKET_NAME is required when STORAGE_BACKEND=s3.')
        if app_env == 'production' and bool(access_key) != bool(secret_key):
            errors.append('Set both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or neither (instance role).')
        return errors
    if app_env != 'production':
        return errors
    if not single_instance:
        errors.append(
            'Production needs STORAGE_BACKEND=s3 so uploads are shared by every instance. '
            'To keep files on one persistent disk, set FILE_STORAGE_SINGLE_INSTANCE=True and run a single instance.'
        )
        return errors
    if not media_root:
        errors.append('MEDIA_ROOT is required with local file storage and must point to persistent storage.')
    if not document_storage_root:
        errors.append(
            'DOCUMENT_STORAGE_ROOT is required with local file storage and must point to private persistent storage.'
        )
    return errors


def build_database_settings(
    database_url, *, pool_min=2, pool_max=16, pool_timeout=10, conn_max_age=60, behind_pooler=False,
):
    """Parse DATABASE_URL; PostgreSQL gets Django's native psycopg pool.

    The pool is per process (one per gunicorn worker) and requires
    CONN_MAX_AGE=0. ``pool_max <= 0`` disables pooling and falls back to
    persistent connections with ``conn_max_age``.

    ``behind_pooler`` is for PgBouncer in transaction mode, where consecutive
    transactions of one client can run on different server connections: the
    in-process pool is pointless there, and named server-side cursors and
    prepared statements (both tied to one server session) must be off.
    """
    import dj_database_url

    config = dj_database_url.parse(
        database_url,
        conn_max_age=0,
        ssl_require='sslmode=require' in database_url,
    )
    if config['ENGINE'] != 'django.db.backends.postgresql':
        return config
    if behind_pooler:
        # Persistent client connections to PgBouncer are cheap and save a
        # handshake per request; health checks drop ones PgBouncer closed.
        config['CONN_MAX_AGE'] = conn_max_age
        config['CONN_HEALTH_CHECKS'] = True
        config['DISABLE_SERVER_SIDE_CURSORS'] = True
        config.setdefault('OPTIONS', {})['prepare_threshold'] = None
    elif pool_max > 0:
        config.setdefault('OPTIONS', {})['pool'] = {
            'min_size': max(0, min(pool_min, pool_max)),
            'max_size': pool_max,
            'timeout': pool_timeout,
        }
    else:
        config['CONN_MAX_AGE'] = conn_max_age
    return config


def direct_database_settings(direct_url):
    """A second alias that bypasses PgBouncer, for session-level work (advisory
    locks held across many transactions: migrations and scheduled jobs)."""
    config = build_database_settings(direct_url, pool_max=0, conn_max_age=0)
    config['TEST'] = {'MIRROR': 'default'}
    return config


def is_enabled(value):
    return str(value or '').strip().lower() not in {'', '0', 'false', 'no', 'off'}


def build_cache_settings(
    redis_url, *, key_prefix='naseeb', connect_timeout=0.25, socket_timeout=0.25, health_check_interval=30,
):
    """Return CACHES: Redis when ``redis_url`` is set, otherwise per-process memory.

    Every cache call sits on the request path (throttles, lockouts, budgets), so
    a hung or unreachable Redis must fail within a fraction of a second instead
    of redis-py's 5 s defaults; callers then fail open. No retries: a retry
    only doubles the stall while Redis is down.
    """
    if not redis_url:
        return {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'naseeb-local'}}
    return {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': redis_url,
            'KEY_PREFIX': key_prefix,
            'TIMEOUT': 300,
            'OPTIONS': {
                'socket_connect_timeout': connect_timeout,
                'socket_timeout': socket_timeout,
                'retry_on_timeout': False,
                'health_check_interval': health_check_interval,
            },
        }
    }
