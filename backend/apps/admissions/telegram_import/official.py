"""Read a program's official web page (or the channel's article that links to it).

The URLs come from public posts, so every request is treated as hostile:
- https on port 443 only, no user:password in the URL;
- the host must resolve to public addresses only, and the connection goes to the
  address that was checked (no second DNS lookup an attacker could change);
- at most MAX_REDIRECTS redirects, each checked the same way;
- HTML only, size-capped, short timeout; cookies and scripts are never used.
Only visible text, the title and the links are kept.
"""
import http.client
import ipaddress
import re
import socket
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from ..telegram_feed import telegram_ssl_context

TIMEOUT = 8
MAX_BYTES = 1_500_000
MAX_REDIRECTS = 2
# The whole read (redirects and a slow body included) never takes longer than this.
TOTAL_SECONDS = TIMEOUT * 2
MAX_TEXT = 6000
MAX_LINKS = 200
SKIP_TAGS = {'script', 'style', 'noscript', 'template', 'svg', 'head', 'nav', 'footer', 'form', 'iframe', 'aside'}
BLOCK_TAGS = {'p', 'div', 'section', 'article', 'li', 'ul', 'ol', 'br', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table'}


class PageUnavailable(Exception):
    pass


def public_addresses(host):
    """The host's addresses, or PageUnavailable if any of them is not on the public internet."""
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise PageUnavailable('dns') from exc
    addresses = []
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split('%')[0])
        if not address.is_global or address.is_multicast:
            raise PageUnavailable('private_address')
        if str(address) not in addresses:
            addresses.append(str(address))
    if not addresses:
        raise PageUnavailable('dns')
    return addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS to ``address`` while checking the certificate (and SNI) for ``host``."""

    def __init__(self, host, address, **kwargs):
        super().__init__(host, 443, context=telegram_ssl_context(), timeout=TIMEOUT, **kwargs)
        self.pinned_address = address

    def connect(self):
        sock = socket.create_connection((self.pinned_address, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def check_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise PageUnavailable('not_https')
    if parts.port not in (None, 443):
        raise PageUnavailable('port')
    return parts


def _get(url, stop_at):
    parts = check_url(url)
    address = public_addresses(parts.hostname)[0]
    connection = PinnedHTTPSConnection(parts.hostname, address)
    path = (parts.path or '/') + (f'?{parts.query}' if parts.query else '')
    try:
        connection.request('GET', path, headers={
            'Host': parts.hostname, 'User-Agent': 'Mozilla/5.0 NaseebEdu/1.0 (program check)',
            'Accept': 'text/html,application/xhtml+xml', 'Accept-Language': 'en,ru;q=0.8,uz;q=0.6',
        })
        response = connection.getresponse()
        if response.status in (301, 302, 303, 307, 308):
            return response.status, response.getheader('Location') or '', b'', ''
        content_type = (response.getheader('Content-Type') or '').lower()
        body = b''
        while response.status == 200 and len(body) <= MAX_BYTES:
            if time.monotonic() > stop_at:
                raise PageUnavailable('slow')
            chunk = response.read(65536)
            if not chunk:
                break
            body += chunk
        return response.status, '', body, content_type
    finally:
        connection.close()


def fetch_page(url):
    """(final url, html text). Raises PageUnavailable for anything unexpected."""
    stop_at = time.monotonic() + TOTAL_SECONDS
    for _ in range(MAX_REDIRECTS + 1):
        if time.monotonic() > stop_at:
            raise PageUnavailable('slow')
        check_url(url)  # every hop, the first and each redirect target
        try:
            status, location, body, content_type = _get(url, stop_at)
        except PageUnavailable:
            raise
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise PageUnavailable(exc.__class__.__name__) from exc
        if location:
            url = urljoin(url, location)
            continue
        if status != 200:
            raise PageUnavailable(f'status_{status}')
        if 'html' not in content_type:
            raise PageUnavailable('not_html')
        if len(body) > MAX_BYTES:
            raise PageUnavailable('too_large')
        charset = re.search(r'charset=([\w-]+)', content_type)
        try:
            return url, body.decode(charset[1] if charset else 'utf-8', 'replace')
        except LookupError:
            return url, body.decode('utf-8', 'replace')
    raise PageUnavailable('too_many_redirects')


# Where an article's own text is, and words that mark the link to apply with.
CONTENT_CLASS = re.compile(r'entry-content|post-content|article-body|post-body|single-content|td-post-content|content-inner', re.I)
APPLY_WORDS = re.compile(
    r'apply|application|register|registration|official|website|sign ?up|enrol|'
    r'ariza|rasmiy|ro.yxat|подать|заявк|регистрац|официальн|сайт', re.I,
)
VOID_TAGS = {'br', 'img', 'input', 'meta', 'link', 'hr', 'source', 'wbr', 'area', 'base', 'col', 'embed', 'track'}


class PageParser(HTMLParser):
    """Visible text, the title, and links ranked: links in the article body and links
    whose words say "apply" or "official site" come first; menus, sidebars and
    footers matter least."""

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.stack = []  # (tag, is_content, is_skipped)
        self.parts = []
        self.title = []
        self.in_title = False
        self.links = {}  # url -> score
        self.order = []
        self.link = None  # [url, in_content, words]

    @property
    def skipping(self):
        return any(skipped for _, _, skipped in self.stack)

    @property
    def in_content(self):
        return any(content for _, content, _ in self.stack)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self.in_title = True
        if tag not in VOID_TAGS:
            content = tag in ('article', 'main') or bool(CONTENT_CLASS.search(attrs.get('class') or ''))
            self.stack.append((tag, content, tag in SKIP_TAGS or tag == 'aside'))
        if self.skipping:
            return
        if tag in BLOCK_TAGS:
            self.parts.append('\n')
        if tag == 'a':
            href = (attrs.get('href') or '').strip()
            if href and not href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
                absolute = urljoin(self.base_url, href)
                if absolute.startswith('https://'):
                    self.link = [absolute, self.in_content, [attrs.get('title') or '']]

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'a' and self.link:
            url, in_content, words = self.link
            self.link = None
            score = (2 if in_content else 0) + (3 if APPLY_WORDS.search(' '.join(words)) else 0)
            if url not in self.links:
                if len(self.order) >= MAX_LINKS:
                    return
                self.order.append(url)
            self.links[url] = max(self.links.get(url, 0), score)
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
            return
        if self.skipping:
            return
        self.parts.append(data)
        if self.link is not None:
            self.link[2].append(data)

    def ranked_links(self):
        return sorted(self.order, key=lambda url: -self.links[url])


def read_page(url, html):
    """{'url', 'title', 'text', 'links'} with the text trimmed to MAX_TEXT characters."""
    parser = PageParser(url)
    parser.feed(html)
    parser.close()
    lines = [re.sub(r'\s+', ' ', line).strip() for line in ''.join(parser.parts).split('\n')]
    text = '\n'.join(line for line in lines if len(line) > 1)
    return {
        'url': url,
        'title': re.sub(r'\s+', ' ', ''.join(parser.title)).strip()[:200],
        'text': text[:MAX_TEXT],
        'links': parser.ranked_links(),
    }


def load(url, fetch=None):
    """The parsed page at ``url``; ``fetch(url) -> (final_url, html)`` replaces the network in tests."""
    final_url, html = (fetch or fetch_page)(url)
    return read_page(final_url, html)
