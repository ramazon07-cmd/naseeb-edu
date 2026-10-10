from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

from apps.admissions.models import School
from apps.users.models import RevokedRefreshSession, User
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
        # The used token is blacklisted; the rotated one still works.
        self.client.credentials()
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
