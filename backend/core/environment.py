VALID_APP_ENVIRONMENTS = {'development', 'test', 'production'}
INSECURE_SECRET_KEYS = {
    '',
    'change-me-to-a-long-random-secret',
    'dev-only-naseeb-secret-key-change-in-production',
    'dev-only-rbis-secret-key-change-in-production',
    'local-docker-secret-change-me',
}


def resolve_app_environment(value, *, hosted=False):
    """Default hosted runtimes to production without weakening explicit overrides."""
    normalized = str(value or '').strip().lower()
    return normalized or ('production' if hosted else 'development')


def validate_runtime_environment(
    *,
    app_env,
    debug,
    secret_key,
    database_url,
    demo_accounts_enabled,
    media_root='',
    document_storage_root='',
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
    if secret_key in INSECURE_SECRET_KEYS or len(secret_key) < 32:
        errors.append('SECRET_KEY must be a unique production secret of at least 32 characters.')
    if not database_url:
        errors.append('DATABASE_URL is required in production; local SQLite is development-only.')
    elif database_url.lower().startswith('sqlite'):
        errors.append('SQLite is not allowed in production; configure PostgreSQL DATABASE_URL.')
    if demo_accounts_enabled:
        errors.append('ENABLE_DEMO_ACCOUNTS must be False in production.')
    if not media_root:
        errors.append('MEDIA_ROOT is required in production and must point to persistent storage.')
    if not document_storage_root:
        errors.append(
            'DOCUMENT_STORAGE_ROOT is required in production and must point to private persistent storage.'
        )
    return errors
