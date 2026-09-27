import ast
import os
from pathlib import Path
from unittest import mock, skipUnless

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase

from apps.users.cache_safety import cache_decrement, cache_get, count_hit
from apps.users.models import User
from apps.users.throttles import ScopedRateThrottle, UserRateThrottle, WindowRateThrottle, parse_rate


class Clock:
    def __init__(self, now):
        self.now = now

    def time(self):
        return self.now


class FixedIdentThrottle(WindowRateThrottle):
    scope = 'test'
    limits = [(3, 60)]

    def get_limits(self):
        return self.limits

    def get_cache_key(self, request, view):
        return 'client'


class WindowThrottleTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.clock = Clock(600.0)
        patcher = mock.patch('apps.users.throttles.time', self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def hit(self, throttle_class=FixedIdentThrottle):
        throttle = throttle_class()
        return throttle.allow_request(None, None), throttle.wait()

    def test_parse_rate_matches_drf_format(self):
        self.assertEqual(parse_rate('1200/hour'), (1200, 3600))
        self.assertEqual(parse_rate('10/min'), (10, 60))
        self.assertEqual(parse_rate('5/s'), (5, 1))
        self.assertIsNone(parse_rate(None))

    def test_sliding_window_limit_and_exact_retry_after(self):
        for _ in range(3):
            self.assertEqual(self.hit(), (True, None))
        self.clock.now = 610.0
        allowed, wait = self.hit()
        self.assertFalse(allowed)
        # 50 s left in this window, then the 3 old requests must decay to 2 (a third of the next window).
        self.assertEqual(wait, 70)
        self.clock.now = 679.0
        self.assertFalse(self.hit()[0])
        self.clock.now = 680.0
        self.assertTrue(self.hit()[0])

    def test_rejected_requests_are_not_counted(self):
        for _ in range(3):
            self.hit()
        for _ in range(20):
            self.assertFalse(self.hit()[0])
        self.assertEqual(cache_get('throttle:test:client:60:10'), 3)

    def test_previous_window_blocks_a_boundary_burst(self):
        self.clock.now = 659.0
        for _ in range(3):
            self.assertTrue(self.hit()[0])
        self.clock.now = 661.0  # a fixed window would allow 3 more here
        self.assertFalse(self.hit()[0])

    def test_fixed_window_resets_at_the_boundary(self):
        class Fixed(FixedIdentThrottle):
            sliding = False

        self.clock.now = 659.0
        for _ in range(3):
            self.assertTrue(self.hit(Fixed)[0])
        self.assertEqual(self.hit(Fixed), (False, 1))
        self.clock.now = 660.0
        self.assertTrue(self.hit(Fixed)[0])

    def test_a_failing_second_limit_refunds_the_first(self):
        class Two(FixedIdentThrottle):
            limits = [(10, 60), (1, 3600)]

        self.assertTrue(self.hit(Two)[0])
        self.assertFalse(self.hit(Two)[0])
        self.assertEqual(cache_get('throttle:test:client:60:10'), 1)

    def test_cache_outage_fails_open(self):
        with mock.patch('apps.users.throttles.count_hit', return_value=None):
            for _ in range(10):
                self.assertTrue(self.hit()[0])

    def test_scoped_throttle_keys_users_and_ips_separately(self):
        request = APIRequestFactory().get('/')
        request.user = mock.Mock(is_authenticated=True, pk=7)
        view = mock.Mock(throttle_scope='login')
        self.assertEqual(ScopedRateThrottle().get_cache_key(request, view), 'user:7')
        request.user = mock.Mock(is_authenticated=False)
        self.assertEqual(ScopedRateThrottle().get_cache_key(request, view), 'ip:127.0.0.1')
        self.assertTrue(ScopedRateThrottle().allow_request(request, mock.Mock(throttle_scope=None)))


class ApiThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(username='rate-user', password='StrongPass123!', role=User.Role.STUDENT)

    def test_user_rate_returns_429_with_retry_after(self):
        from django.conf import settings
        rates = {**settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'], 'user': '2/minute'}
        self.client.force_authenticate(self.user)
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': rates}):
            codes = [self.client.get('/api/users/accounts/me/').status_code for _ in range(3)]
            self.assertEqual(codes, [200, 200, 429])
            response = self.client.get('/api/users/accounts/me/')
        self.assertGreaterEqual(int(response['Retry-After']), 1)

    def test_counter_is_a_single_integer_per_window(self):
        # O(1): the stored state is one integer, however many requests were made.
        self.client.force_authenticate(self.user)
        for _ in range(5):
            self.client.get('/api/users/accounts/me/')
        throttle = UserRateThrottle()
        limit, window = throttle.get_limits()[0]
        import time
        bucket = int(time.time() // window)
        self.assertEqual(cache_get(f'throttle:user:{self.user.pk}:{window}:{bucket}'), 5)


@skipUnless(os.environ.get('REDIS_TEST_URL'), 'set REDIS_TEST_URL to run against a real Redis')
class RedisCounterTests(SimpleTestCase):
    """The single-round-trip Redis path of the shared counters."""

    def setUp(self):
        from core.environment import build_cache_settings
        self.override = override_settings(CACHES=build_cache_settings(os.environ['REDIS_TEST_URL'], key_prefix='t'))
        self.override.enable()
        self.addCleanup(self.override.disable)
        cache.clear()
        self.addCleanup(cache.clear)

    def test_count_hit_sets_expiry_once_and_reads_the_other_key(self):
        from django.core.cache import caches
        cache.set('prev', 4)
        self.assertEqual(count_hit('cur', 30, also_read='prev'), (1, 4))
        self.assertEqual(count_hit('cur', 30), (2, 0))
        self.assertEqual(cache.get('cur'), 2)
        backend = caches['default']
        client = backend._cache.get_client(write=True)
        ttl = client.ttl(backend.make_and_validate_key('cur'))
        self.assertTrue(0 < ttl <= 30)

    def test_decrement_never_recreates_an_expired_key(self):
        count_hit('gone', 30)
        cache_decrement('gone')
        self.assertEqual(cache.get('gone'), 0)
        cache.delete('gone')
        cache_decrement('gone')
        self.assertIsNone(cache.get('gone'))


def rates(**overrides):
    from django.conf import settings
    merged = {**settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'], **overrides}
    return override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': merged})


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SharedAddressAuthThrottleTests(APITestCase):
    """A whole class behind one school/carrier IP must be able to sign in and stay signed in."""

    SCHOOL_IP = '203.0.113.7'

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.users = [
            User.objects.create_user(
                username=f'pupil{i}', email=f'pupil{i}@example.com', password='StrongPass123!', role=User.Role.STUDENT,
            )
            for i in range(12)
        ]

    def login(self, username, password='StrongPass123!', ip=SCHOOL_IP):
        return self.client.post('/api/auth/token/', {'username': username, 'password': password},
                                format='json', REMOTE_ADDR=ip)

    def test_many_accounts_sign_in_from_one_address(self):
        with rates(login='10/minute', anon='1/hour'):
            codes = {self.login(user.username).status_code for user in self.users}
        self.assertEqual(codes, {status.HTTP_200_OK})

    def test_one_account_is_limited_per_address(self):
        with rates(login='3/minute'), override_settings(LOGIN_LOCKOUT_THRESHOLD=100):
            codes = [self.login('pupil0', 'wrong', ip='198.51.100.1').status_code for _ in range(4)]
            elsewhere = self.login('pupil0', 'wrong', ip='198.51.100.2').status_code
        self.assertEqual(codes, [401, 401, 401, 429])
        self.assertEqual(elsewhere, 401)

    def test_account_wide_ceiling_slows_guessing_across_addresses(self):
        with rates(login_account='3/minute'), override_settings(LOGIN_LOCKOUT_THRESHOLD=100):
            codes = [self.login('pupil0', 'wrong', ip=f'198.51.100.{i}').status_code for i in range(4)]
            # A correct password from a new address waits too.
            fresh = self.login('pupil0', ip='198.51.100.200').status_code
        self.assertEqual(codes, [401, 401, 401, 429])
        self.assertEqual(fresh, 429)

    def test_guessing_from_many_addresses_cannot_keep_the_owner_out(self):
        home = '192.0.2.10'
        self.assertEqual(self.login('pupil0', ip=home).status_code, 200)
        with rates(login='3/minute', login_account='5/minute'), override_settings(LOGIN_LOCKOUT_THRESHOLD=100):
            attacks = [self.login('pupil0', 'wrong', ip=f'198.51.100.{i}').status_code for i in range(30)]
            owner = [self.login(name, ip=home).status_code for name in ('pupil0', 'PUPIL0@example.com')]
        self.assertIn(429, attacks)
        self.assertEqual(owner, [200, 200])

    def test_known_address_is_per_account(self):
        home = '192.0.2.10'
        self.login('pupil1', ip=home)
        with rates(login_account='2/minute'), override_settings(LOGIN_LOCKOUT_THRESHOLD=100):
            for i in range(2):
                self.login('pupil0', 'wrong', ip=f'198.51.100.{i}')
            self.assertEqual(self.login('pupil0', ip=home).status_code, 429)

    def test_known_address_is_not_stored_in_clear(self):
        from apps.users.security import is_known_login_device
        self.login('pupil0', ip='192.0.2.10')
        self.assertTrue(is_known_login_device('pupil0', '192.0.2.10'))
        self.assertTrue(is_known_login_device('pupil0@example.com', '192.0.2.10'))
        self.assertFalse(is_known_login_device('pupil0', '192.0.2.11'))
        keys = [key for key in getattr(cache, '_cache', {}) if 'login-device' in key]
        self.assertEqual(len(keys), 2)
        self.assertFalse([key for key in keys if '192.0.2.10' in key or 'pupil0' in key])

    def test_failed_sign_in_does_not_mark_the_address_known(self):
        from apps.users.security import is_known_login_device
        self.login('pupil0', 'wrong', ip='198.51.100.9')
        self.assertFalse(is_known_login_device('pupil0', '198.51.100.9'))

    def test_distributed_failures_still_raise_a_security_warning(self):
        with override_settings(LOGIN_ACCOUNT_ALERT_THRESHOLD=5, LOGIN_LOCKOUT_THRESHOLD=100), \
                self.assertLogs('naseeb.security', 'WARNING') as logs:
            for i in range(5):
                self.login('pupil0', 'wrong', ip=f'198.51.100.{i}')
        self.assertIn('login_failures_spread_across_ips', logs.output[0])

    def test_account_name_is_normalised(self):
        with rates(login='2/minute'), override_settings(LOGIN_LOCKOUT_THRESHOLD=100):
            self.login('pupil0', 'wrong')
            self.login('  PUPIL0 ', 'wrong')
            self.assertEqual(self.login('Pupil0', 'wrong').status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_per_address_ceiling_still_stops_floods(self):
        with rates(login_ip='3/minute'):
            codes = [self.login(user.username).status_code for user in self.users[:4]]
        self.assertEqual(codes, [200, 200, 200, 429])

    def test_refresh_is_not_limited_per_address(self):
        tokens = [self.login(user.username).data['refresh'] for user in self.users]
        with rates(anon='1/hour'):
            codes = {
                self.client.post('/api/auth/token/refresh/', {'refresh': token}, format='json',
                                 REMOTE_ADDR=self.SCHOOL_IP).status_code
                for token in tokens
            }
        self.assertEqual(codes, {status.HTTP_200_OK})

    def test_refresh_is_limited_per_token(self):
        token = self.login('pupil0').data['refresh']
        with rates(refresh='2/hour'):
            codes = [
                self.client.post('/api/auth/token/refresh/', {'refresh': token}, format='json').status_code
                for _ in range(3)
            ]
        # The second use fails because the token was rotated; the third is throttled.
        self.assertEqual(codes, [200, 401, 429])

    def test_credential_endpoints_are_limited_per_user(self):
        first, second = self.users[:2]
        with rates(password_change='1/hour'):
            self.client.force_authenticate(first)
            self.client.post('/api/users/accounts/change-password/', {}, format='json', REMOTE_ADDR=self.SCHOOL_IP)
            again = self.client.post('/api/users/accounts/change-password/', {}, format='json',
                                     REMOTE_ADDR=self.SCHOOL_IP)
            self.client.force_authenticate(second)
            other = self.client.post('/api/users/accounts/change-password/', {}, format='json',
                                     REMOTE_ADDR=self.SCHOOL_IP)
        self.assertEqual(again.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertNotEqual(other.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_malformed_login_body_is_not_a_server_error(self):
        response = self.client.post('/api/auth/token/', [1, 2], format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_count_hits_counts_several_keys_in_one_step(self):
        from apps.users.cache_safety import count_hits
        self.assertEqual(count_hits(['a', 'b'], 30), [1, 1])
        self.assertEqual(count_hits(['a', 'b', 'c'], 30), [2, 2, 1])


class CacheSafetyLayeringTests(SimpleTestCase):
    def test_cache_safety_is_a_leaf_module(self):
        """throttles and security build on cache_safety, so it must not import them back."""
        source = Path(__file__).with_name('cache_safety.py').read_text(encoding='utf-8')
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom):
                imported.add('.' * node.level + (node.module or ''))
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        local = {name for name in imported if name.startswith(('.', 'apps.', 'core.'))}
        self.assertEqual(local, set())
