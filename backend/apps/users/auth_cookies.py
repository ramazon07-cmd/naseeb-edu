"""The refresh token lives in an HttpOnly cookie scoped to /api/auth/, never in
a response body, so script on the page (an XSS) cannot read it. The SPA keeps
only the short-lived access token, in memory.

Because the browser attaches the cookie by itself, the endpoints that read it
(refresh, logout) are CSRF-protected: they require the X-Requested-With header,
which a cross-site form cannot send and a cross-origin fetch can only send after
a CORS preflight the API answers for allowed origins only, and the request's
Origin must be an allowed origin (origin_allowed). That holds for every
AUTH_REFRESH_COOKIE_SAMESITE value, including None for a cross-site frontend.
"""
import functools
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.core.signals import setting_changed
from django.utils.http import is_same_domain
from rest_framework.exceptions import PermissionDenied

CSRF_HEADER = 'HTTP_X_REQUESTED_WITH'
ORIGIN_SETTINGS = frozenset({'CSRF_TRUSTED_ORIGINS', 'CORS_ALLOWED_ORIGINS', 'CORS_ALLOWED_ORIGIN_REGEXES'})


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


def _normalise(origin):
    parts = urlsplit(origin)
    if parts.scheme not in {'http', 'https'} or not parts.netloc:
        return ''
    return f'{parts.scheme}://{parts.netloc}'.lower()


@functools.cache
def _allow_lists():
    """(exact origins, wildcard (scheme, .domain) pairs, compiled regexes), built
    once from CSRF_TRUSTED_ORIGINS (exact and https://*.example.com forms),
    CORS_ALLOWED_ORIGINS and CORS_ALLOWED_ORIGIN_REGEXES."""
    exact = set()
    wildcards = []
    for entry in [*settings.CSRF_TRUSTED_ORIGINS, *settings.CORS_ALLOWED_ORIGINS]:
        parts = urlsplit(entry.lower())
        if parts.netloc.startswith('*'):
            wildcards.append((parts.scheme, parts.netloc[1:]))
        elif _normalise(entry):
            exact.add(_normalise(entry))
    regexes = [re.compile(pattern) for pattern in getattr(settings, 'CORS_ALLOWED_ORIGIN_REGEXES', ())]
    return frozenset(exact), tuple(wildcards), tuple(regexes)


def _settings_changed(*, setting, **kwargs):
    if setting in ORIGIN_SETTINGS:
        _allow_lists.cache_clear()


setting_changed.connect(_settings_changed)


def origin_allowed(request, origin):
    """True when `origin` (an Origin header value) is the API's own origin or
    an allowed frontend origin. "null" and anything malformed never pass."""
    normalised = _normalise(origin or '')
    if not normalised:
        return False
    own = f"{'https' if request.is_secure() else 'http'}://{request.get_host()}".lower()
    if normalised == own:
        return True
    exact, wildcards, regexes = _allow_lists()
    if normalised in exact:
        return True
    scheme, netloc = normalised.split('://', 1)
    if any(scheme == wild_scheme and is_same_domain(netloc, domain) for wild_scheme, domain in wildcards):
        return True
    return any(regex.match(origin) for regex in regexes)


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
