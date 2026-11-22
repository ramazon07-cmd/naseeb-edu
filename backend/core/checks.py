from django.conf import settings
from django.core import checks


@checks.register(checks.Tags.caches, deploy=True)
def shared_cache_check(app_configs, **kwargs):
    """Rate limits, login lockouts and the AI budget need one cache shared by all processes."""
    backend = settings.CACHES.get('default', {}).get('BACKEND', '')
    if settings.DEBUG or not backend.endswith('LocMemCache'):
        return []
    return [checks.Warning(
        'CACHES uses a per-process local-memory cache.',
        hint='Set REDIS_URL so throttles, login lockouts and the AI budget are shared across workers and instances.',
        id='naseeb.W001',
    )]


@checks.register()
def unused_ai_keys_check(app_configs, **kwargs):
    """Provider keys do nothing while the outbound-AI switch is off; say so instead of staying silent."""
    from core.ai_policy import outbound_ai_allowed

    keys = [name for name in ('AI_GATEWAY_API_KEY',) if getattr(settings, name, '')]
    if not keys or outbound_ai_allowed():
        return []
    return [checks.Warning(
        f'{" and ".join(keys)} set, but OUTBOUND_AI_ENABLED is off, so no AI provider is called.',
        hint='Set OUTBOUND_AI_ENABLED=True only after legal sign-off (open item H8), or remove the keys.',
        id='naseeb.W002',
    )]


@checks.register(checks.Tags.compatibility, deploy=True)
def email_backend_check(app_configs, **kwargs):
    """Meeting emails, reminders and invites need a real mail backend in production."""
    if settings.DEBUG or not settings.EMAIL_BACKEND.endswith('console.EmailBackend'):
        return []
    return [checks.Warning(
        'EMAIL_BACKEND is the console backend, so no email leaves the server.',
        hint='Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend and the EMAIL_HOST/PORT/USER/PASSWORD variables.',
        id='naseeb.W003',
    )]


@checks.register()
def ai_provider_check(app_configs, **kwargs):
    """The Claude CLI provider is for local testing; it must never be selected in production."""
    provider = getattr(settings, 'AI_PROVIDER', 'gateway')
    if provider == 'claude_cli' and settings.APP_ENV not in ('development', 'test'):
        if getattr(settings, 'AI_CLI_ALLOW_PRODUCTION', False):
            return [checks.Warning(
                'Production is using the Claude CLI (AI_CLI_ALLOW_PRODUCTION is on).',
                hint='Temporary: set the API key, then unset AI_PROVIDER and AI_CLI_ALLOW_PRODUCTION.',
                id='naseeb.W010',
            )]
        return [checks.Error(
            'AI_PROVIDER=claude_cli is only allowed when APP_ENV is development or test.',
            hint='Unset AI_PROVIDER (it defaults to gateway) in production.',
            id='naseeb.E001',
        )]
    if provider not in ('gateway', 'claude_cli'):
        return [checks.Error('AI_PROVIDER must be gateway or claude_cli.', id='naseeb.E002')]
    return []


@checks.register()
def public_site_url_check(app_configs, **kwargs):
    """FRONTEND_URL is put into every Telegram message and email, so a wrong one reaches users.

    In production it must be the public https address (a private IP like 10.200.x.x,
    localhost or plain http makes links that don't open for anyone outside the server).
    """
    from core.public_urls import frontend_url_problems

    if not settings.IS_PRODUCTION:
        return []
    return [
        checks.Error(
            f'FRONTEND_URL={settings.FRONTEND_URL!r} cannot be the public site address: {problem}.',
            hint='Set FRONTEND_URL=https://www.naseebedu.com (or unset it to use that default). '
                 'It is the address put into Telegram messages and emails.',
            id='naseeb.E003',
        )
        for problem in frontend_url_problems(settings.FRONTEND_URL)
    ]
