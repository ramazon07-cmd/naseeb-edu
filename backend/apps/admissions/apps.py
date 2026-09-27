from django.apps import AppConfig


class AdmissionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.admissions'

    def ready(self):
        from . import catalog_cache, progress_cache, signals

        signals.connect()
        catalog_cache.connect()
        progress_cache.connect()
