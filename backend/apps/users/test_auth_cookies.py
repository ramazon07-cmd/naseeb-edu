from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import UntypedToken

from apps.users.auth_test_utils import COOKIE_AUTH_HEADERS, post_refresh, refresh_cookie_value
from apps.admissions.models import School
from apps.users.models import User

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
        self.assertEqual(cookie['samesite'], 'Strict')
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
        evil_referer = self.client.post(
            '/api/auth/token/refresh/', format='json', HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_REFERER='https://evil.example/page',
        )
        self.assertEqual(evil_referer.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(CORS_ALLOWED_ORIGINS=['https://app.example.com'])
    def test_refresh_from_a_configured_frontend_origin_is_accepted(self):
        self.login()
        self.assertEqual(post_refresh(self.client, HTTP_ORIGIN='https://app.example.com').status_code, status.HTTP_200_OK)

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
