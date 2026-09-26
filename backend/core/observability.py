"""Optional error reporting through Sentry (enabled only when SENTRY_DSN is set)."""

FILTERED = '[Filtered]'
SENSITIVE_HEADERS = {
    'authorization', 'proxy-authorization', 'cookie', 'set-cookie', 'x-csrftoken', 'x-api-key',
}
SENSITIVE_FIELDS = {
    'password', 'new_password', 'old_password', 'current_password', 'temporary_password',
    'refresh', 'access', 'token', 'secret', 'api_key',
}


def _scrub_mapping(mapping, sensitive):
    if isinstance(mapping, dict):
        for key in mapping:
            if str(key).lower() in sensitive:
                mapping[key] = FILTERED


def scrub_event(event, hint=None):
    """Drop credentials from an event before it leaves the process.

    ``send_default_pii=False`` already omits cookies and the user's IP; this
    also covers bearer tokens and passwords/JWTs in request bodies, whatever
    the SDK's defaults become.
    """
    request = event.get('request')
    if isinstance(request, dict):
        _scrub_mapping(request.get('headers'), SENSITIVE_HEADERS)
        _scrub_mapping(request.get('data'), SENSITIVE_FIELDS)
        request.pop('cookies', None)
    return event


def init_sentry(dsn, *, environment='', release='', traces_sample_rate=0.0):
    """Initialise Sentry when ``dsn`` is set; return whether it was."""
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration()],
        environment=environment or None,
        release=release or None,
        traces_sample_rate=max(0.0, min(1.0, traces_sample_rate)),
        send_default_pii=False,
        before_send=scrub_event,
        before_send_transaction=scrub_event,
    )
    return True
