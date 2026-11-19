"""One JSON POST to an AI provider, with a bounded retry for transient failures.

Used by the non-streaming AI features. A call is retried at most
``AI_PROVIDER_RETRIES`` times (default 1), only for a connection error, a
timeout, HTTP 429 or a 5xx: never for a 4xx that retrying cannot fix. The
caller counts the call against the budget once, however many attempts it takes.
"""
import json
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger('naseeb.ai_http')
RETRY_PAUSE_SECONDS = 0.5


def _transient(error):
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or error.code >= 500
    return isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError))


def post_json(url, api_key, body, *, timeout, extra_headers=None):
    """POST ``body`` and return the decoded JSON response."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            **(extra_headers or {}),
        },
        method='POST',
    )
    retries = max(0, int(getattr(settings, 'AI_PROVIDER_RETRIES', 1)))
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt >= retries or not _transient(error):
                raise
            logger.warning('ai_provider_retry attempt=%s error=%s', attempt + 1, type(error).__name__)
            time.sleep(RETRY_PAUSE_SECONDS)
