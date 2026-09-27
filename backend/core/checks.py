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
