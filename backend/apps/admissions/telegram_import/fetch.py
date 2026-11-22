"""Read posts from a public channel's web preview (https://t.me/s/<channel>).

No Telegram account, bot or API key is used: the preview is the same page anyone
sees in a browser. Only the channel names in settings are fetched, redirects are
refused, and pages are size-capped.
"""
import logging
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.request import HTTPSHandler, Request, build_opener

from ..telegram_feed import MAX_PAGE_BYTES, NoRedirects, telegram_ssl_context

logger = logging.getLogger('naseeb.telegram_import')
FETCH_TIMEOUT = 15
# Pages read back to the saved cursor in one run (about 20 posts each). The run's time
# budget stops it earlier; nothing is handled until the whole gap has been read, so a
# long backlog is never half-skipped.
MAX_BACKLOG_PAGES = 30
CHANNEL_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{3,31}')
POST_ID = re.compile(r'[1-9][0-9]{0,11}')
BLOCK_TAGS = {'p', 'div', 'blockquote', 'li', 'pre'}


@dataclass
class Post:
    channel: str
    id: int
    text: str = ''
    posted_at: str = ''

    @property
    def url(self):
        return f'https://t.me/{self.channel}/{self.id}'


@dataclass
class Page:
    posts: list = field(default_factory=list)
    before: int | None = None


def valid_channel(name):
    return bool(CHANNEL_NAME.fullmatch(name or ''))


class ChannelPageParser(HTMLParser):
    """Collect each post's id, date and text. Links are written into the text as
    ``label (url)`` so that a line removed later takes its links with it."""

    def __init__(self, channel):
        super().__init__(convert_charrefs=True)
        self.channel = channel
        self.page = Page()
        self.post = None
        self.text_depth = 0  # open <div>s inside the post text; 0 = not in the text
        self.parts = []
        self.link = None  # (href, [label parts]) while inside <a>

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get('class') or '').split()
        if tag == 'div' and 'tgme_widget_message' in classes:
            match = re.fullmatch(rf'{re.escape(self.channel)}/({POST_ID.pattern})', attrs.get('data-post') or '', re.IGNORECASE)
            self._finish_post()
            self.post = Post(self.channel, int(match[1])) if match else None
            return
        before = attrs.get('data-before') or ''
        if 'js-messages_more' in classes and POST_ID.fullmatch(before):
            self.page.before = int(before)
        if self.post is None:
            return
        if tag == 'time' and attrs.get('datetime') and not self.post.posted_at:
            self.post.posted_at = attrs['datetime'][:25]
        if self.text_depth:
            if tag == 'div':
                self.text_depth += 1
            if tag == 'br':
                self._write('\n')
            elif tag in BLOCK_TAGS:
                self._write('\n')
            elif tag == 'a':
                self.link = (attrs.get('href') or '', [])
            return
        if tag == 'div' and 'js-message_text' in classes and not self.post.text:
            self.text_depth = 1
            self.parts = []

    def handle_startendtag(self, tag, attrs):
        if tag == 'br' and self.text_depth:
            self._write('\n')
        else:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if not self.text_depth:
            return
        if tag == 'a' and self.link is not None:
            href, label = self.link
            self.link = None
            label = ''.join(label).strip()
            if re.match(r'https?://', href):
                self._write(href if not label or label.rstrip('/') == href.rstrip('/') or label.startswith('http') else f'{label} ({href})')
            else:
                self._write(label)
        elif tag == 'div':
            self.text_depth -= 1
            if not self.text_depth and self.post is not None:
                self.post.text = ''.join(self.parts).strip()

    def handle_data(self, data):
        if self.text_depth:
            self._write(data)

    def _write(self, text):
        if self.link is not None:
            self.link[1].append(text)
        else:
            self.parts.append(text)

    def _finish_post(self):
        if self.post is not None and self.post.text:
            self.page.posts.append(self.post)
        self.post = None
        self.text_depth = 0

    def close(self):
        super().close()
        self._finish_post()


def parse_page(channel, html):
    parser = ChannelPageParser(channel)
    parser.feed(html)
    parser.close()
    unique = {post.id: post for post in parser.page.posts}
    parser.page.posts = [unique[key] for key in sorted(unique)]
    return parser.page


def fetch_html(channel, before=None):
    """One preview page as text. Raises on network errors, redirects and oversized pages."""
    if not valid_channel(channel):
        raise ValueError('Invalid channel name')
    url = f'https://t.me/s/{channel}' + (f'?before={int(before)}' if before else '')
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 NaseebEdu/1.0'})
    opener = build_opener(NoRedirects(), HTTPSHandler(context=telegram_ssl_context()))
    with opener.open(request, timeout=FETCH_TIMEOUT) as response:
        content = response.read(MAX_PAGE_BYTES + 1)
    if len(content) > MAX_PAGE_BYTES:
        raise ValueError('Oversized Telegram response')
    return content.decode('utf-8', 'replace')


def new_posts(channel, last_id, *, max_pages=MAX_BACKLOG_PAGES, fetch=None):
    """Posts newer than ``last_id``, oldest first.

    The first run (``last_id`` 0) reads the newest page only. Later runs page back
    until they reach ``last_id``, so no unseen post is skipped. Only a channel with more than
    ``max_pages`` pages of unseen posts loses its oldest ones (logged).
    """
    fetch = fetch or fetch_html
    found = {}
    before = None
    for _ in range(max_pages):
        page = parse_page(channel, fetch(channel, before))
        for post in page.posts:
            if post.id > last_id and (before is None or post.id < before):
                found[post.id] = post
        if not last_id or not page.posts:
            break
        oldest = min(post.id for post in page.posts)
        cursor = page.before if page.before and page.before <= oldest else oldest
        if oldest <= last_id + 1 or (before is not None and cursor >= before):
            break
        before = cursor
    else:
        logger.warning('telegram_import_backlog_too_long channel=%s pages=%s last_id=%s', channel, max_pages, last_id)
    return [found[key] for key in sorted(found)]
