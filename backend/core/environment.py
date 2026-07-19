VALID_APP_ENVIRONMENTS = {'development', 'test', 'production'}
INSECURE_SECRET_KEYS = {
    '',
    'change-me-to-a-long-random-secret',
    'dev-only-naseeb-secret-key-change-in-production',
    'dev-only-rbis-secret-key-change-in-production',
    'local-docker-secret-change-me',
}


def validate_runtime_environment(*, app_env, debug, secret_key, database_url, demo_accounts_enabled):
    """Return configuration errors that must stop a production deployment."""
    errors = []
    if app_env not in VALID_APP_ENVIRONMENTS:
        errors.append(f'APP_ENV must be one of: {", ".join(sorted(VALID_APP_ENVIRONMENTS))}.')
        return errors

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
    return errors
