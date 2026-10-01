"""Discover public channel posts; media/content stay inside Telegram's widget."""
import http.client
import logging
import os
import re
import ssl
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.cache_safety import cache_get, cache_set, count_hit
from apps.users.throttles import ScopedRateThrottle, UserRateThrottle

CHANNEL = 'naseeb_edu'
MAX_PAGE_BYTES = 2 * 1024 * 1024
UPSTREAM_TIMEOUT = 6
# The newest page changes with every post; older pages hardly ever do. A page is
# kept far longer than it is fresh, as the answer while Telegram is slow or down.
FRESH_LATEST = 60
FRESH_HISTORY = 3600
KEEP_STALE = 24 * 3600
# Only one request per page asks Telegram. For FETCH_LOCK seconds (a failed try
# too, so an outage is retried every few seconds, not by every request) the others
# get the copy they already have, or wait up to WAIT_FOR_OTHER for it.
FETCH_LOCK = 10
WAIT_FOR_OTHER = 3.0
# Whatever cursors are asked for, no more pages than this leave for Telegram per minute.
UPSTREAM_PAGES_PER_MINUTE = 20
FETCH_ERRORS = (URLError, OSError, ValueError, http.client.HTTPException)
logger = logging.getLogger(__name__)


def telegram_ssl_context():
    context = ssl.create_default_context()
    # python.org macOS builds do not automatically load the operating system's
    # CA bundle. Add it without disabling certificate or hostname verification.
    # Explicit operator-provided trust configuration always takes precedence.
    system_bundle = Path('/etc/ssl/cert.pem')
    if (sys.platform == 'darwin' and not os.environ.get('SSL_CERT_FILE')
            and not os.environ.get('SSL_CERT_DIR') and system_bundle.is_file()):
        context.load_verify_locations(cafile=str(system_bundle))
    return context


class PublicPostParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.before = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        post = re.fullmatch(rf'{CHANNEL}/([1-9][0-9]{{0,11}})', attrs.get('data-post', ''))
        if post:
            self.ids.add(int(post[1]))
        before = attrs.get('data-before', '')
        if re.fullmatch(r'[1-9][0-9]{0,11}', before):
            self.before = int(before)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_posts(before=None):
    # Only the fixed public channel is fetched; callers cannot supply URLs.
    url = f'https://t.me/s/{CHANNEL}' + (f'?before={before}' if before else '')
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 NaseebEdu/1.0'})
    with build_opener(NoRedirects(), HTTPSHandler(context=telegram_ssl_context())).open(request, timeout=UPSTREAM_TIMEOUT) as response:
        content = response.read(MAX_PAGE_BYTES + 1)
    if len(content) > MAX_PAGE_BYTES:
        raise ValueError('Oversized Telegram response')
    parser = PublicPostParser()
    parser.feed(content.decode('utf-8'))
    if not parser.ids:
        raise ValueError('Public channel preview unavailable')
    ids = sorted(post_id for post_id in parser.ids if not before or post_id < before)
    cursor = parser.before
    if cursor is not None and (not ids or cursor > min(ids) or (before and cursor >= before)):
        cursor = None
    return {'channel': CHANNEL, 'posts': [f'{CHANNEL}/{post_id}' for post_id in ids], 'before': cursor}


def page_key(before):
    return f'telegram-feed:v2:{CHANNEL}:{before or "latest"}'


def newest_post(page):
    return max((int(post.split('/')[1]) for post in page['posts']), default=0)


def refresh_page(key, before):
    """Ask Telegram for one page and cache it; ``None`` when it could not be had."""
    asked = count_hit('telegram-feed:v2:upstream-budget', 60)
    if asked is not None and asked[0] > UPSTREAM_PAGES_PER_MINUTE:
        logger.warning('Telegram public feed not asked: over %s pages a minute', UPSTREAM_PAGES_PER_MINUTE)
        return None
    try:
        page = fetch_posts(before)
    except FETCH_ERRORS as exc:
        logger.warning('Telegram public feed failed: %s', exc)
        return None
    cache_set(key, {'page': page, 'at': time.time()}, KEEP_STALE)
    return page


def load_page(before):
    """The page for ``before`` from the cache, asking Telegram at most once per page at a time."""
    key = page_key(before)
    entry = cache_get(key)
    if entry and time.time() - entry['at'] < (FRESH_HISTORY if before else FRESH_LATEST):
        return entry['page']
    stale = entry['page'] if entry else None
    asked = count_hit(f'{key}:lock', FETCH_LOCK)
    if asked is None or asked[0] == 1:  # the first to ask, or no shared cache to coordinate with
        return refresh_page(key, before) or stale
    if stale:
        return stale
    deadline = time.monotonic() + WAIT_FOR_OTHER
    while time.monotonic() < deadline:
        time.sleep(0.1)
        entry = cache_get(key)
        if entry:
            return entry['page']
    return None


class TelegramFeedView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = 'telegram_feed'

    def get(self, request):
        raw_before = request.query_params.get('before', '')
        if raw_before and not re.fullmatch(r'[1-9][0-9]{0,11}', raw_before):
            return Response({'detail': 'Invalid post cursor.'}, status=400)
        before = int(raw_before) if raw_before else None
        # A cursor past the newest post names no page of its own: answer with the
        # newest page, so made-up cursors cannot each cost a fetch from Telegram.
        latest = cache_get(page_key(None))
        if before and latest and before > newest_post(latest['page']) + 1:
            before = None
        page = load_page(before)
        if page is None:
            return Response({'detail': 'Telegram posts are temporarily unavailable.'}, status=503, headers={'Retry-After': '3'})
        return Response(page)
