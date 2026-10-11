from django.conf import settings

# What the SPA sends with every cookie-authenticated auth request.
COOKIE_AUTH_HEADERS = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest', 'HTTP_ORIGIN': 'http://testserver'}


def refresh_cookie_value(response):
    return response.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value


def post_refresh(client, token=None, **extra):
    """POST to the refresh endpoint with `token` (or the client's current cookie)."""
    if token is not None:
        client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = token
    return client.post('/api/auth/token/refresh/', format='json', **{**COOKIE_AUTH_HEADERS, **extra})
