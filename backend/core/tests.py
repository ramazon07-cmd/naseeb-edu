from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from core.environment import resolve_app_environment, validate_runtime_environment


class ProductionEnvironmentTests(SimpleTestCase):
    def test_render_defaults_to_production_when_app_env_is_missing(self):
        self.assertEqual(resolve_app_environment('', hosted=True), 'production')
        self.assertEqual(resolve_app_environment(None, hosted=True), 'production')
        self.assertEqual(resolve_app_environment('', hosted=False), 'development')
        self.assertEqual(resolve_app_environment('development', hosted=True), 'development')

    def test_production_requires_secure_external_configuration(self):
        errors = validate_runtime_environment(
            app_env='production',
            debug=True,
            secret_key='change-me-to-a-long-random-secret',
            database_url='',
            demo_accounts_enabled=True,
            media_root='',
            document_storage_root='',
        )

        self.assertTrue(any('DEBUG' in error for error in errors))
        self.assertTrue(any('SECRET_KEY' in error for error in errors))
        self.assertTrue(any('DATABASE_URL' in error for error in errors))
        self.assertTrue(any('ENABLE_DEMO_ACCOUNTS' in error for error in errors))
        self.assertTrue(any('MEDIA_ROOT' in error for error in errors))
        self.assertTrue(any('DOCUMENT_STORAGE_ROOT' in error for error in errors))

    def test_secure_production_configuration_is_accepted(self):
        errors = validate_runtime_environment(
            app_env='production',
            debug=False,
            secret_key='a-unique-production-secret-with-more-than-32-characters',
            database_url='postgresql://user:password@db.example.com:5432/naseeb',
            demo_accounts_enabled=False,
            media_root='/mnt/naseeb/media',
            document_storage_root='/mnt/naseeb/private-documents',
        )

        self.assertEqual(errors, [])

    def test_production_rejects_sqlite(self):
        errors = validate_runtime_environment(
            app_env='production',
            debug=False,
            secret_key='a-unique-production-secret-with-more-than-32-characters',
            database_url='sqlite:///db.sqlite3',
            demo_accounts_enabled=False,
        )

        self.assertTrue(any('SQLite' in error for error in errors))

    def test_hosted_runtime_rejects_development_sqlite_fallback(self):
        errors = validate_runtime_environment(
            app_env='development',
            debug=True,
            secret_key='dev-only-naseeb-secret-key-change-in-production',
            database_url='',
            demo_accounts_enabled=True,
            hosted=True,
        )

        self.assertTrue(any('APP_ENV=production' in error for error in errors))

    @override_settings(DEMO_ACCOUNTS_ENABLED=False)
    def test_demo_seed_is_safely_skipped_when_disabled(self):
        output = StringIO()
        call_command('seed_demo', stdout=output)
        self.assertIn('skipping seed_demo', output.getvalue())

    @override_settings(DEMO_ACCOUNTS_ENABLED=False)
    def test_demo_reset_is_blocked_before_database_flush(self):
        with self.assertRaisesMessage(CommandError, 'Demo accounts are disabled'):
            call_command('reset_demo', stdout=StringIO())
