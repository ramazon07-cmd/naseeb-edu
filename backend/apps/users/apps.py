from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'

    def ready(self):
        from core import checks  # noqa: F401  (registers deployment checks)
        from django.db.models.signals import post_save

        from .entitlements import create_default_subscription

        post_save.connect(
            create_default_subscription,
            sender='admissions.School',
            dispatch_uid='users.create_default_subscription',
        )
