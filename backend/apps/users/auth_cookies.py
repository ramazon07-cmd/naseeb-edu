"""The refresh token lives in an HttpOnly cookie scoped to /api/auth/, never in
a response body, so script on the page (an XSS) cannot read it. The SPA keeps
only the short-lived access token, in memory.

Because the browser attaches the cookie by itself, the endpoints that read it
(refresh, logout) are CSRF-protected: they require the X-Requested-With header,
which a cross-site form cannot send and a cross-origin fetch can only send after
a CORS preflight the API answers for allowed origins only, and the request's
Origin must be an allowed origin (origin_allowed).
"""
from urllib.parse import urlsplit

from corsheaders.middleware import CorsMiddleware
from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework.exceptions import PermissionDenied

CSRF_HEADER = 'HTTP_X_REQUESTED_WITH'


def refresh_cookie(request):
    return request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME, '').strip()


def set_refresh_cookie(response, refresh):
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        refresh,
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


def clear_refresh_cookie(response):
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        domain=settings.AUTH_REFRESH_COOKIE_DOMAIN,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


def move_refresh_to_cookie(response):
    """Set the cookie from a token-pair response and drop the token from its body."""
    refresh = response.data.pop('refresh', None) if isinstance(response.data, dict) else None
    if refresh:
        set_refresh_cookie(response, refresh)
    return response


# The middlewares are instantiated only for their origin checks.
def _unused_get_response(request):
    return None


def origin_allowed(request, origin):
    """The one origin check: the API's own origin and CSRF_TRUSTED_ORIGINS
    (exact and wildcard, through Django's CSRF middleware), or
    CORS_ALLOWED_ORIGINS / CORS_ALLOWED_ORIGIN_REGEXES (through
    django-cors-headers). `origin` must be the request's Origin header.
    "null" (sandboxed frames, privacy redirects) never passes."""
    if not origin or origin == 'null':
        return False
    django_request = getattr(request, '_request', request)
    if CsrfViewMiddleware(_unused_get_response)._origin_verified(django_request):
        return True
    return CorsMiddleware(_unused_get_response).origin_found_in_white_lists(origin, urlsplit(origin))


def _reject():
    return PermissionDenied({'detail': 'Cross-site request rejected.', 'code': 'csrf_failed'})


def enforce_cookie_csrf(request):
    """For endpoints authenticated by the refresh cookie alone. Browsers send
    Origin with every POST fetch, so a request without one is refused."""
    if not request.META.get(CSRF_HEADER, '').strip():
        raise _reject()
    if not origin_allowed(request, request.META.get('HTTP_ORIGIN', '')):
        raise _reject()


def enforce_login_origin(request):
    """Sign-in sets the cookie: a cross-site form must not log the browser into
    another account (login CSRF). Clients that send no Origin (scripts, the
    test client) are not browsers and are allowed."""
    origin = request.META.get('HTTP_ORIGIN', '')
    if origin and not origin_allowed(request, origin):
        raise _reject()
