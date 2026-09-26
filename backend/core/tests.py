from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from core.environment import resolve_app_environment, validate_runtime_environment


class ProductionEnvironmentTests(SimpleTestCase):
    def test_render_defaults_to_production_when_app_env_is_missing(self):
        self.assertEqual(resolve_app_environment('', hosted=True), 'production')
        self.assertEqual(resolve_app_environment(None, hosted=True), 'production')
        self.assertEqual(resolve_app_environment('development', hosted=True), 'development')

    def test_missing_app_env_fails_closed_to_production(self):
        self.assertEqual(resolve_app_environment('', hosted=False), 'production')
        self.assertEqual(resolve_app_environment('', debug_requested='False'), 'production')
        self.assertEqual(resolve_app_environment('', debug_requested='True'), 'development')
        self.assertEqual(resolve_app_environment('', debug_requested='True', hosted=True), 'production')
        self.assertEqual(resolve_app_environment('', running_tests=True), 'test')

    def test_placeholder_secret_keys_are_rejected(self):
        for key in (
            'replace-with-a-unique-random-secret-at-least-32-characters',
            'my-example-secret-key-which-is-long-enough-1234',
            'change-me-please-this-is-a-long-enough-secret-key',
            'short',
        ):
            errors = validate_runtime_environment(
                app_env='production', debug=False, secret_key=key,
                database_url='postgresql://u:p@db/x', demo_accounts_enabled=False,
            )
            self.assertTrue(any('SECRET_KEY' in error for error in errors), key)

    def test_production_requires_secure_external_configuration(self):
        errors = validate_runtime_environment(
            app_env='production',
            debug=True,
            secret_key='change-me-to-a-long-random-secret',
            database_url='',
            demo_accounts_enabled=True,
        )

        self.assertTrue(any('DEBUG' in error for error in errors))
        self.assertTrue(any('SECRET_KEY' in error for error in errors))
        self.assertTrue(any('DATABASE_URL' in error for error in errors))
        self.assertTrue(any('ENABLE_DEMO_ACCOUNTS' in error for error in errors))

    def test_secure_production_configuration_is_accepted(self):
        errors = validate_runtime_environment(
            app_env='production',
            debug=False,
            secret_key='a-unique-production-secret-with-more-than-32-characters',
            database_url='postgresql://user:password@db.example.com:5432/naseeb',
            demo_accounts_enabled=False,
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


class TokenLifetimeTests(SimpleTestCase):
    def test_access_tokens_are_short_lived_and_refresh_tokens_rotate(self):
        from datetime import timedelta
        from django.conf import settings
        self.assertLessEqual(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'], timedelta(minutes=30))
        self.assertTrue(settings.SIMPLE_JWT['ROTATE_REFRESH_TOKENS'])
        self.assertTrue(settings.SIMPLE_JWT['BLACKLIST_AFTER_ROTATION'])


class ScalingSettingsTests(SimpleTestCase):
    def test_postgres_uses_native_pool_with_conn_max_age_zero(self):
        from core.environment import build_database_settings
        config = build_database_settings('postgres://u:p@db:5432/naseeb', pool_min=2, pool_max=16, pool_timeout=5)
        self.assertEqual(config['CONN_MAX_AGE'], 0)
        self.assertEqual(config['OPTIONS']['pool'], {'min_size': 2, 'max_size': 16, 'timeout': 5})

    def test_pool_can_be_disabled(self):
        from core.environment import build_database_settings
        config = build_database_settings('postgres://u:p@db:5432/naseeb', pool_max=0, conn_max_age=60)
        self.assertNotIn('pool', config.get('OPTIONS', {}))
        self.assertEqual(config['CONN_MAX_AGE'], 60)

    def test_local_memory_cache_is_flagged_outside_debug(self):
        from core.checks import shared_cache_check
        locmem = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
        redis = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': 'redis://x'}}
        with override_settings(DEBUG=False, CACHES=locmem):
            self.assertEqual([item.id for item in shared_cache_check(None)], ['naseeb.W001'])
        with override_settings(DEBUG=False, CACHES=redis):
            self.assertEqual(shared_cache_check(None), [])


class MigrateLockedCommandTests(TestCase):
    def test_migrate_locked_runs_cleanly_when_up_to_date(self):
        output = StringIO()
        call_command('migrate_locked', interactive=False, stdout=output)
        self.assertIn('No migrations to apply', output.getvalue())

    def test_migrations_use_the_direct_connection_when_configured(self):
        from unittest import mock
        from contextlib import nullcontext
        base = 'apps.users.management.commands.migrate_locked'
        with mock.patch(f'{base}.session_alias', return_value='direct'), \
                mock.patch(f'{base}.advisory_lock', return_value=nullcontext(True)) as lock, \
                mock.patch(f'{base}.call_command') as migrate:
            call_command('migrate_locked', interactive=False, stdout=StringIO())
        self.assertEqual(lock.call_args.kwargs['alias'], 'direct')
        self.assertEqual(migrate.call_args.kwargs['database'], 'direct')


class PgBouncerSettingsTests(SimpleTestCase):
    def test_pooler_mode_disables_session_features(self):
        from core.environment import build_database_settings
        config = build_database_settings('postgres://u:p@pgbouncer:6432/naseeb', pool_max=8, behind_pooler=True)
        self.assertNotIn('pool', config['OPTIONS'])
        self.assertTrue(config['DISABLE_SERVER_SIDE_CURSORS'])
        self.assertIsNone(config['OPTIONS']['prepare_threshold'])

    def test_direct_alias_is_unpooled_and_mirrors_default_in_tests(self):
        from core.environment import direct_database_settings
        config = direct_database_settings('postgres://u:p@db:5432/naseeb')
        self.assertNotIn('pool', config.get('OPTIONS', {}))
        self.assertEqual(config['TEST'], {'MIRROR': 'default'})

    def test_environment_switches_reach_settings(self):
        import json
        import os
        import subprocess
        import sys
        from django.conf import settings
        env = {
            **{key: value for key, value in os.environ.items() if key in {'PATH', 'HOME', 'SYSTEMROOT'}},
            'APP_ENV': 'development', 'SECRET_KEY': 'x' * 40, 'DEBUG': 'True',
            'DATABASE_URL': 'postgres://u:p@pgbouncer:6432/naseeb', 'PGBOUNCER': '1',
            'DIRECT_DATABASE_URL': 'postgres://u:p@db:5432/naseeb',
        }
        script = (
            'import django, json; django.setup(); from django.conf import settings as s; '
            'print(json.dumps({"default": s.DATABASES["default"], "direct": s.DATABASES["direct"]["HOST"]}, default=str))'
        )
        result = subprocess.run(
            [sys.executable, '-c', script], cwd=settings.BASE_DIR, capture_output=True, text=True, timeout=120,
            env={**env, 'DJANGO_SETTINGS_MODULE': 'core.settings'},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(data['default']['DISABLE_SERVER_SIDE_CURSORS'])
        self.assertNotIn('pool', data['default']['OPTIONS'])
        self.assertEqual(data['direct'], 'db')

    def test_session_locks_refuse_to_go_through_the_pooler(self):
        from unittest import mock
        from core.db import session_alias
        postgres = {'default': mock.Mock(vendor='postgresql')}
        with override_settings(DB_BEHIND_POOLER=True), mock.patch('core.db.connections', postgres):
            with self.assertRaisesMessage(CommandError, 'DIRECT_DATABASE_URL'):
                session_alias()
        with override_settings(DB_BEHIND_POOLER=False), mock.patch('core.db.connections', postgres):
            self.assertEqual(session_alias(), 'default')


class LoggingConfigTests(SimpleTestCase):
    def test_app_and_request_errors_reach_the_console(self):
        from django.conf import settings
        self.assertIn('console', settings.LOGGING['loggers']['apps']['handlers'])
        self.assertEqual(settings.LOGGING['loggers']['django.request']['level'], 'WARNING')


class FreshCheckoutMessageTests(SimpleTestCase):
    def test_missing_app_env_explains_how_to_run_locally(self):
        import os
        import subprocess
        import sys
        from django.conf import settings
        env = {key: value for key, value in os.environ.items() if key in {'PATH', 'HOME', 'SYSTEMROOT'}}
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check'],
            cwd=settings.BASE_DIR, env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('APP_ENV=development', result.stderr)
        self.assertIn('.env.example', result.stderr)


class RedisTimeoutTests(SimpleTestCase):
    def test_redis_settings_bound_every_call(self):
        from core.environment import build_cache_settings
        options = build_cache_settings('redis://cache:6379', connect_timeout=0.2, socket_timeout=0.3)['default']['OPTIONS']
        self.assertEqual(options['socket_connect_timeout'], 0.2)
        self.assertEqual(options['socket_timeout'], 0.3)
        self.assertIs(options['retry_on_timeout'], False)
        self.assertGreater(options['health_check_interval'], 0)
        self.assertTrue(build_cache_settings('')['default']['BACKEND'].endswith('LocMemCache'))

    def test_hanging_redis_fails_open_quickly(self):
        """A Redis that accepts connections but never answers must not stall the request thread."""
        import socket
        import time
        from core.environment import build_cache_settings
        from apps.users.cache_safety import cache_get, cache_increment

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(8)
        self.addCleanup(listener.close)
        port = listener.getsockname()[1]
        caches = build_cache_settings(f'redis://127.0.0.1:{port}/0', connect_timeout=0.2, socket_timeout=0.2)
        with override_settings(CACHES=caches), self.assertLogs('naseeb.cache', level='WARNING'):
            started = time.monotonic()
            self.assertEqual(cache_get('anything', 'fallback'), 'fallback')
            self.assertIsNone(cache_increment('counter', 60))
            self.assertLess(time.monotonic() - started, 2)


class ApiCompressionTests(TestCase):
    def setUp(self):
        from apps.users.models import User
        self.user = User.objects.create_user(
            username='gzip-user', email='gzip@example.com', password='StrongPass123!', role=User.Role.STUDENT,
        )
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_json_api_responses_are_gzipped(self):
        import gzip
        import json
        response = self.client.get('/api/users/accounts/me/', HTTP_ACCEPT_ENCODING='gzip, br')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Encoding'], 'gzip')
        self.assertIn('Accept-Encoding', response['Vary'])
        self.assertEqual(json.loads(gzip.decompress(response.content))['username'], 'gzip-user')

    def test_uncompressed_without_accept_encoding(self):
        response = self.client.get('/api/users/accounts/me/')
        self.assertFalse(response.has_header('Content-Encoding'))

    def test_streams_are_not_compressed(self):
        response = self.client.post(
            '/api/assistant/chat/', {'messages': [{'role': 'user', 'content': 'Help with my tasks ' * 30}]},
            format='json', HTTP_ACCEPT_ENCODING='gzip',
        )
        self.assertTrue(response.streaming)
        self.assertFalse(response.has_header('Content-Encoding'))
        self.assertIn(b'guidance', b''.join(response.streaming_content))

    def test_file_downloads_are_not_compressed(self):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from core.middleware import ApiGZipMiddleware
        request = RequestFactory().get('/api/documents/1/file/', HTTP_ACCEPT_ENCODING='gzip')
        download = HttpResponse(b'{}' * 500, content_type='application/json')
        download['Content-Disposition'] = 'attachment; filename="export.json"'
        response = ApiGZipMiddleware(lambda r: download)(request)
        self.assertFalse(response.has_header('Content-Encoding'))


class HealthTests(TestCase):
    def test_liveness_touches_nothing(self):
        with self.assertNumQueries(0):
            response = self.client.get('/api/health/')
        self.assertEqual(response.json(), {'status': 'ok', 'service': 'naseeb-edu'})

    def test_ready_checks_database_and_cache(self):
        response = self.client.get('/api/health/ready/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'checks': {'database': 'ok', 'cache': 'ok'}})
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_database_failure_is_503(self):
        from unittest import mock
        from django.db import OperationalError
        with mock.patch('core.health.connection.cursor', side_effect=OperationalError('down')), \
                self.assertLogs('naseeb.health', level='WARNING'):
            response = self.client.get('/api/health/ready/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['checks']['database'], 'error')

    def test_cache_outage_is_degraded_not_down(self):
        from core.environment import build_cache_settings
        with override_settings(CACHES=build_cache_settings('redis://127.0.0.1:1/0')), \
                self.assertLogs('naseeb.health', level='WARNING'):
            response = self.client.get('/api/health/ready/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'degraded', 'checks': {'database': 'ok', 'cache': 'error'}})


class SentryTests(SimpleTestCase):
    def test_disabled_without_dsn(self):
        from unittest import mock
        from core.observability import init_sentry
        with mock.patch('sentry_sdk.init') as init:
            self.assertFalse(init_sentry(''))
        init.assert_not_called()

    def test_enabled_with_dsn_and_no_default_pii(self):
        from unittest import mock
        from core.observability import init_sentry, scrub_event
        with mock.patch('sentry_sdk.init') as init:
            self.assertTrue(init_sentry('https://key@sentry.example/1', environment='production', traces_sample_rate=5))
        options = init.call_args.kwargs
        self.assertIs(options['send_default_pii'], False)
        self.assertEqual(options['traces_sample_rate'], 1.0)
        self.assertIs(options['before_send'], scrub_event)
        self.assertEqual(options['environment'], 'production')

    def test_scrub_removes_credentials(self):
        from core.observability import scrub_event
        event = {'request': {
            'headers': {'Authorization': 'Bearer abc', 'X-CSRFToken': 't', 'Accept': 'application/json'},
            'cookies': {'sessionid': 'x'},
            'data': {'username': 'ali', 'password': 'secret', 'refresh': 'jwt'},
        }}
        request = scrub_event(event)['request']
        self.assertEqual(request['headers'], {'Authorization': '[Filtered]', 'X-CSRFToken': '[Filtered]',
                                              'Accept': 'application/json'})
        self.assertNotIn('cookies', request)
        self.assertEqual(request['data'], {'username': 'ali', 'password': '[Filtered]', 'refresh': '[Filtered]'})
