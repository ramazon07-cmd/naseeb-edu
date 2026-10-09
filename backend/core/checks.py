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

    keys = [name for name in ('AI_GATEWAY_API_KEY', 'GROQ_API_KEY') if getattr(settings, name, '')]
    if not keys or outbound_ai_allowed():
        return []
    return [checks.Warning(
        f'{" and ".join(keys)} set, but OUTBOUND_AI_ENABLED is off, so no AI provider is called.',
        hint='Set OUTBOUND_AI_ENABLED=True only after legal sign-off (open item H8), or remove the keys.',
        id='naseeb.W002',
    )]
