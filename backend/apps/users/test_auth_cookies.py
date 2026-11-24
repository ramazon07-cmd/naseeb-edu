from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

from apps.admissions.models import School
from datetime import timedelta

from django.utils import timezone

from apps.users.models import RefreshRotation, RevokedRefreshSession, User
from testing.auth_cookies import COOKIE_AUTH_HEADERS, post_refresh, refresh_cookie_value

COOKIE = settings.AUTH_REFRESH_COOKIE_NAME
PASSWORD = 'CookiePass123!'


class RefreshCookieTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='cookie-user', email='cookie@example.com', password=PASSWORD, role=User.Role.COUNSELOR,
            school=School.objects.create(name='Cookie School', code='cookie-school'),
        )

    def login(self, **extra):
        return self.client.post('/api/auth/token/', {'username': 'cookie-user', 'password': PASSWORD}, format='json', **extra)

    def test_login_sets_an_httponly_cookie_and_keeps_the_token_out_of_the_body(self):
        response = self.login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        self.assertNotIn(b'"refresh"', response.content)
        cookie = response.cookies[COOKIE]
        self.assertTrue(cookie.value)
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['path'], '/api/auth/')
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertEqual(cookie['max-age'], int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()))

    @override_settings(AUTH_REFRESH_COOKIE_SECURE=True)
    def test_cookie_is_secure_when_configured(self):
        self.assertTrue(self.login().cookies[COOKIE]['secure'])

    def test_login_from_a_foreign_origin_is_rejected(self):
        response = self.login(HTTP_ORIGIN='https://evil.example')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn(COOKIE, response.cookies)

    def test_refresh_works_from_the_cookie_and_rotates_it(self):
        first = refresh_cookie_value(self.login())
        response = post_refresh(self.client)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        rotated = refresh_cookie_value(response)
        self.assertNotEqual(rotated, first)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(self.client.get('/api/users/accounts/me/').status_code, status.HTTP_200_OK)
        # The used token is blacklisted (outside the reuse grace); the rotated one still works.
        self.client.credentials()
        with override_settings(AUTH_REFRESH_REUSE_GRACE_SECONDS=0):
            self.assertEqual(post_refresh(self.client, first).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(post_refresh(self.client, rotated).status_code, status.HTTP_200_OK)

    def test_a_refresh_token_in_the_body_is_ignored(self):
        token = refresh_cookie_value(self.login())
        self.client.cookies.pop(COOKIE)
        response = self.client.post('/api/auth/token/refresh/', {'refresh': token}, format='json', **COOKIE_AUTH_HEADERS)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_without_the_csrf_header_is_rejected(self):
        self.login()
        response = self.client.post('/api/auth/token/refresh/', format='json', HTTP_ORIGIN='http://testserver')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'csrf_failed')

    def test_refresh_with_a_foreign_or_missing_origin_is_rejected(self):
        self.login()
        for origin in ('https://evil.example', 'null'):
            response = post_refresh(self.client, HTTP_ORIGIN=origin)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, origin)
        no_origin = self.client.post('/api/auth/token/refresh/', format='json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(no_origin.status_code, status.HTTP_403_FORBIDDEN)
        # A Referer is not a substitute for Origin, even a same-origin one.
        referer_only = self.client.post(
            '/api/auth/token/refresh/', format='json', HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_REFERER='http://testserver/dashboard',
        )
        self.assertEqual(referer_only.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(CORS_ALLOWED_ORIGINS=['https://app.example.com'])
    def test_refresh_from_a_configured_frontend_origin_is_accepted(self):
        self.login()
        self.assertEqual(post_refresh(self.client, HTTP_ORIGIN='https://app.example.com').status_code, status.HTTP_200_OK)

    @override_settings(CORS_ALLOWED_ORIGINS=[], CSRF_TRUSTED_ORIGINS=['https://*.naseeb.example'])
    def test_wildcard_csrf_trusted_origins_are_honoured(self):
        self.login()
        self.assertEqual(post_refresh(self.client, HTTP_ORIGIN='https://app.naseeb.example').status_code, status.HTTP_200_OK)
        self.assertEqual(post_refresh(self.client, HTTP_ORIGIN='https://naseeb.example.evil.com').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(post_refresh(self.client, HTTP_ORIGIN='http://app.naseeb.example').status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(CORS_ALLOWED_ORIGINS=[], CORS_ALLOWED_ORIGIN_REGEXES=[r'^https://preview-\d+\.naseeb\.example$'])
    def test_cors_origin_regexes_are_honoured(self):
        self.login()
        self.assertEqual(post_refresh(self.client, HTTP_ORIGIN='https://preview-42.naseeb.example').status_code, status.HTTP_200_OK)
        self.assertEqual(post_refresh(self.client, HTTP_ORIGIN='https://preview-x.naseeb.example').status_code, status.HTTP_403_FORBIDDEN)

    def test_logout_is_never_throttled(self):
        from apps.users.test_throttles import rates

        token = refresh_cookie_value(self.login())
        with rates(anon='1/hour', refresh_ip='1/hour'):
            for _ in range(3):
                self.client.post('/api/auth/logout/', **COOKIE_AUTH_HEADERS)
            self.client.cookies[COOKIE] = token
            response = self.client.post('/api/auth/logout/', **COOKIE_AUTH_HEADERS)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=UntypedToken(token)['jti']).exists())

    def test_refresh_without_a_cookie_is_401(self):
        response = post_refresh(self.client)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_the_token_and_clears_the_cookie(self):
        token = refresh_cookie_value(self.login())
        response = self.client.post('/api/auth/logout/', **COOKIE_AUTH_HEADERS)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        cleared = response.cookies[COOKIE]
        self.assertEqual(cleared.value, '')
        self.assertEqual(cleared['max-age'], 0)
        self.assertEqual(cleared['path'], '/api/auth/')
        self.assertEqual(BlacklistedToken.objects.filter(token__jti=UntypedToken(token)["jti"]).count(), 1)
        self.assertEqual(post_refresh(self.client, token).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_revokes_tokens_rotated_after_it(self):
        # A refresh that was in flight (or ran in another tab) when the user
        # signed out: the logout carried the old cookie, the rotation's newer
        # token reaches the browser afterwards. The whole chain is dead.
        old = refresh_cookie_value(self.login())
        rotated = refresh_cookie_value(post_refresh(self.client, old))
        self.client.cookies[COOKIE] = old
        self.assertEqual(self.client.post('/api/auth/logout/', **COOKIE_AUTH_HEADERS).status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(RevokedRefreshSession.objects.filter(sid=UntypedToken(rotated)['sid']).exists())
        response = post_refresh(self.client, rotated)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        # Other sign-ins (another device) are separate sessions and keep working.
        other = APIClient()
        other_token = refresh_cookie_value(other.post('/api/auth/token/', {'username': 'cookie-user', 'password': PASSWORD}, format='json'))
        self.assertNotEqual(UntypedToken(other_token)['sid'], UntypedToken(rotated)['sid'])
        self.assertEqual(post_refresh(other).status_code, status.HTTP_200_OK)

    def test_logout_of_a_legacy_body_token_revokes_it_and_keeps_the_cookie(self):
        # The previous frontend's localStorage token (no session id).
        legacy = str(RefreshToken.for_user(self.user))
        current = refresh_cookie_value(self.login())
        response = self.client.post('/api/auth/logout/', {'refresh': legacy}, format='json', **COOKIE_AUTH_HEADERS)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertNotIn(COOKIE, response.cookies, 'the cookie may belong to a newer sign-in')
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=UntypedToken(legacy)['jti']).exists())
        self.assertEqual(post_refresh(self.client, current).status_code, status.HTTP_200_OK)
        rejected = self.client.post('/api/auth/logout/', {'refresh': legacy}, format='json', HTTP_ORIGIN='http://testserver')
        self.assertEqual(rejected.status_code, status.HTTP_403_FORBIDDEN, 'the CSRF header is still required')

    def test_logout_needs_the_csrf_header_and_works_without_a_session(self):
        token = refresh_cookie_value(self.login())
        rejected = self.client.post('/api/auth/logout/', HTTP_ORIGIN='https://evil.example', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(rejected.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(BlacklistedToken.objects.filter(token__jti=UntypedToken(token)["jti"]).exists())
        self.client.cookies.pop(COOKIE)
        self.assertEqual(self.client.post('/api/auth/logout/', **COOKIE_AUTH_HEADERS).status_code, status.HTTP_204_NO_CONTENT)

    def test_password_change_moves_the_new_refresh_token_into_the_cookie(self):
        login = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        response = self.client.post('/api/users/accounts/me/password/', {
            'current_password': PASSWORD, 'new_password': 'AnotherPass456!', 'confirm_password': 'AnotherPass456!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertNotIn('refresh', response.data)
        self.client.credentials()
        self.assertEqual(post_refresh(self.client, refresh_cookie_value(response)).status_code, status.HTTP_200_OK)


class RefreshReuseGraceTests(APITestCase):
    """The same refresh cookie arriving twice (two tabs, a retry) must not sign
    the user out, but only inside the grace window and never after logout."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='grace-user', email='grace@example.com', password=PASSWORD, role=User.Role.COUNSELOR,
            school=School.objects.create(name='Grace School', code='grace-school'),
        )
        login = self.client.post('/api/auth/token/', {'username': 'grace-user', 'password': PASSWORD}, format='json')
        self.original = refresh_cookie_value(login)

    def tab(self):
        return APIClient()

    def test_two_tabs_with_the_same_cookie_both_succeed_inside_the_window(self):
        tab_one, tab_two = self.tab(), self.tab()
        first = post_refresh(tab_one, self.original)
        second = post_refresh(tab_two, self.original)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertIn('access', second.data)
        one, two = refresh_cookie_value(first), refresh_cookie_value(second)
        # Same session, fresh tokens; the second tab's token works and so does the first's.
        self.assertEqual(UntypedToken(one)['sid'], UntypedToken(two)['sid'])
        self.assertNotEqual(UntypedToken(one)['jti'], UntypedToken(two)['jti'])
        self.assertEqual(UntypedToken(two)['pv'], self.user.password_version)
        self.assertEqual(post_refresh(self.tab(), two).status_code, status.HTTP_200_OK)
        self.assertEqual(post_refresh(self.tab(), one).status_code, status.HTTP_200_OK)
        tab_two.credentials(HTTP_AUTHORIZATION=f"Bearer {second.data['access']}")
        self.assertEqual(tab_two.get('/api/users/accounts/me/').status_code, status.HTTP_200_OK)

    def test_replay_after_the_window_is_refused(self):
        post_refresh(self.tab(), self.original)
        RefreshRotation.objects.update(rotated_at=timezone.now() - timedelta(seconds=settings.AUTH_REFRESH_REUSE_GRACE_SECONDS + 5))
        response = post_refresh(self.tab(), self.original)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn(COOKIE, response.cookies)

    def test_a_token_that_was_never_rotated_through_us_is_not_accepted_by_grace(self):
        # Blacklisted by logout (no rotation record): never revived.
        token = refresh_cookie_value(self.tab().post('/api/auth/token/', {'username': 'grace-user', 'password': PASSWORD}, format='json'))
        client = self.tab()
        client.cookies[COOKIE] = token
        client.post('/api/auth/logout/', **COOKIE_AUTH_HEADERS)
        self.assertEqual(post_refresh(self.tab(), token).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_then_refresh_fails_even_inside_the_window(self):
        rotated = refresh_cookie_value(post_refresh(self.tab(), self.original))
        client = self.tab()
        client.cookies[COOKIE] = rotated
        self.assertEqual(client.post('/api/auth/logout/', **COOKIE_AUTH_HEADERS).status_code, status.HTTP_204_NO_CONTENT)
        # The old token was rotated moments ago, yet its session is signed out.
        self.assertEqual(post_refresh(self.tab(), self.original).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(post_refresh(self.tab(), rotated).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_change_ends_the_grace(self):
        post_refresh(self.tab(), self.original)
        User.objects.filter(pk=self.user.pk).update(password_version=self.user.password_version + 1)
        self.assertEqual(post_refresh(self.tab(), self.original).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_grace_is_capped_and_can_be_switched_off(self):
        post_refresh(self.tab(), self.original)
        with override_settings(AUTH_REFRESH_REUSE_GRACE_SECONDS=0):
            self.assertEqual(post_refresh(self.tab(), self.original).status_code, status.HTTP_401_UNAUTHORIZED)
        from apps.users.auth_views import MAX_GRACE_REUSES
        codes = [post_refresh(self.tab(), self.original).status_code for _ in range(MAX_GRACE_REUSES + 1)]
        self.assertEqual(codes, [200] * MAX_GRACE_REUSES + [401])

    def test_inactive_user_gets_no_grace_pair(self):
        post_refresh(self.tab(), self.original)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(post_refresh(self.tab(), self.original).status_code, status.HTTP_401_UNAUTHORIZED)


class RefreshRefusalLoggingTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='log-user', email='log@example.com', password=PASSWORD, role=User.Role.COUNSELOR,
            school=School.objects.create(name='Log School', code='log-school'),
        )
        self.original = refresh_cookie_value(
            self.client.post('/api/auth/token/', {'username': 'log-user', 'password': PASSWORD}, format='json'))

    def refused(self, token=None, **kwargs):
        client = APIClient()
        with self.assertLogs('naseeb.security', level='WARNING') as captured:
            if token is None:
                response = client.post('/api/auth/token/refresh/', format='json', **COOKIE_AUTH_HEADERS)
            else:
                response = post_refresh(client, token, **kwargs)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        return '\n'.join(captured.output)

    def test_missing_cookie(self):
        self.assertIn('reason=missing_cookie', self.refused())

    def test_blacklisted_after_the_window_names_the_user_and_never_the_token(self):
        post_refresh(APIClient(), self.original)
        RefreshRotation.objects.update(rotated_at=timezone.now() - timedelta(minutes=5))
        line = self.refused(self.original)
        self.assertIn('reason=blacklisted', line)
        self.assertIn(f'user={self.user.pk}', line)
        self.assertIn('rotated_seconds_ago=', line)
        self.assertNotIn(self.original, line)
        self.assertNotIn(self.original.split('.')[1], line)

    def test_revoked_session(self):
        client = APIClient()
        client.cookies[COOKIE] = self.original
        client.post('/api/auth/logout/', **COOKIE_AUTH_HEADERS)
        line = self.refused(self.original)
        self.assertIn('reason=revoked_session', line)
        self.assertIn(f'user={self.user.pk}', line)

    def test_expired(self):
        expired = RefreshToken.for_user(self.user)
        expired.set_exp(from_time=timezone.now() - timedelta(days=30), lifetime=timedelta(days=1))
        line = self.refused(str(expired))
        self.assertIn('reason=expired', line)
        self.assertIn(f'user={self.user.pk}', line)

    def test_invalid_and_deleted_user(self):
        self.assertIn('reason=invalid', self.refused('not-a-token'))
        self.assertIn('user=unknown', self.refused('not-a-token'))
        token = RefreshToken.for_user(self.user)
        sid_token = str(token)
        self.user.delete()
        self.assertIn('reason=no_active_account', self.refused(sid_token))


class ExpiredTemporaryPasswordMessageTests(APITestCase):
    def test_default_ttl_is_a_week(self):
        self.assertEqual(settings.TEMPORARY_CREDENTIAL_TTL_HOURS, 168)

    def test_message_names_the_counselor_in_every_language(self):
        from apps.users.localization import localized_message

        self.assertEqual(
            localized_message('credential_expired', language='en'),
            'Your temporary password has expired. Ask your counselor for a new one.',
        )
        self.assertIn('консультанта', localized_message('credential_expired', language='ru'))
        self.assertIn('Maslahatchingizdan', localized_message('credential_expired', language='uz'))
