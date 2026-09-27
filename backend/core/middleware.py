from django.middleware.gzip import GZipMiddleware


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
