import logging

from django.http import HttpResponseNotFound
from django.middleware.gzip import GZipMiddleware

# Paths bots probe all day (framework defaults, config files, other APIs). None of them is a route here.
PROBE_PATHS = frozenset({'/', '/schema/', '/api/credentials', '/api/v1/auto_login', '/settings/settings.py'})
PROBE_PREFIXES = ('/api-auth/', '/api/v1/', '/api/v2/')


def is_probe_path(path):
    return path in PROBE_PATHS or path.startswith(PROBE_PREFIXES)


class ProbePathMiddleware:
    """Answers known scanner probes with a bare 404 before URL resolution and the rest of the stack."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_probe_path(request.path_info):
            return HttpResponseNotFound()
        return self.get_response(request)


class ProbeNotFoundFilter(logging.Filter):
    """Drops the django.request "Not Found" warning for probe paths; other 404s (real API paths) stay logged."""

    def filter(self, record):
        request = getattr(record, 'request', None)
        if getattr(record, 'status_code', None) == 404 and request is not None:
            return not is_probe_path(getattr(request, 'path_info', '') or '')
        return True


class ApiGZipMiddleware(GZipMiddleware):
    """Gzip JSON API responses (list pages are 10-170 KB and compress ~5-10x).

    Streaming responses are left alone: the assistant's text must reach the
    browser chunk by chunk, and file downloads are already compressed formats
    served with a Content-Length. Django's gzip adds random padding against
    BREACH-style length attacks on the JWTs in these bodies.
    """

    def process_response(self, request, response):
        if (
            response.streaming
            or not request.path.startswith('/api/')
            or not response.get('Content-Type', '').startswith('application/json')
            or response.has_header('Content-Disposition')
        ):
            return response
        return super().process_response(request, response)
