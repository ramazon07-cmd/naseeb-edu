"""Checks in code, before and after the AI. Nothing here calls a model.

A post's text (and any page read for it) is untrusted. Before it is sent: invisible
characters are removed and lines addressed to an AI are dropped (with their links).
After the AI: the application link must be one of the candidate links (the post's
own, or those on the channel's article it points to) and point at an official page, the deadline must not have passed, and the program must not already exist.
"""
import re
import unicodedata
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.conf import settings

# Zero-width characters, bidi controls and the BOM: they hide text from a reader
# but not from a model.
INVISIBLE = re.compile('[­᠎​-‏‪-‮⁠-⁤⁦-⁯﻿]')
CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')
URL = re.compile(r'https?://[^\s()<>"\']+', re.IGNORECASE)
# A line that talks to the model instead of describing a program.
ADDRESSED_TO_MODEL = re.compile(
    r'\b(?:ignore|disregard|forget|override)\b.{0,40}\b(?:instruction|prompt|rule|above|previous|earlier)s?\b'
    r'|\b(?:system|developer)\s*(?:prompt|message|:)'
    r'|\byou\s+are\s+(?:now\s+)?(?:an?\s+)?(?:ai|assistant|chatgpt|gpt|language\s+model|llm)\b'
    r'|\b(?:as\s+an?\s+)?(?:ai|llm|language\s+model|chatgpt|assistant)\s*[,:]\s*(?:please\s+)?(?:set|return|output|mark|say|reply|respond)\b'
    r'|\b(?:set|return|output|mark)\s+(?:the\s+)?(?:"|\')?(?:is_program|application_url|json)\b'
    r'|</?(?:system|assistant|instructions?)>|<<<|>>>',
    re.IGNORECASE,
)

# Hosts that are never an official application page.
TELEGRAM_HOSTS = {'t.me', 'telegram.me', 'telegram.org', 'telegram.dog', 'tg.dev'}
SHORTENERS = {
    'bit.ly', 'bitly.com', 'tinyurl.com', 't.co', 'goo.gl', 'forms.gle', 'cutt.ly', 'is.gd', 'ow.ly', 'rb.gy',
    'shorturl.at', 'tiny.cc', 'rebrand.ly', 'buff.ly', 'clck.ru', 'u.to', 'v.gd', 'lnkd.in', 'surl.li', 'linktr.ee',
    'taplink.cc', 'l.facebook.com', 'lm.facebook.com', 'l.instagram.com', 'vk.cc', 'shorturl.asia', 'qr.io',
}
SOCIAL = {
    'youtube.com', 'youtu.be', 'instagram.com', 'facebook.com', 'fb.com', 'tiktok.com', 'x.com', 'twitter.com',
    'vk.com', 'wa.me', 'whatsapp.com', 'chat.whatsapp.com', 'discord.gg', 'discord.com', 'linkedin.com',
    'pinterest.com', 'reddit.com', 'threads.net', 'ok.ru',
}


def clean_text(text):
    """NFC, invisible and control characters removed, whitespace tidied, line breaks kept."""
    text = unicodedata.normalize('NFC', str(text or ''))
    text = CONTROL.sub(' ', INVISIBLE.sub('', text))
    lines = [re.sub(r'[ \t ]+', ' ', line).strip() for line in text.split('\n')]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def strip_model_directed(text):
    """Drop lines addressed to an AI; returns (text, how many lines were dropped)."""
    kept, dropped = [], 0
    for line in text.split('\n'):
        if ADDRESSED_TO_MODEL.search(line):
            dropped += 1
        else:
            kept.append(line)
    return '\n'.join(kept).strip(), dropped


def prepare_post_text(text):
    """What may be sent to the AI: (text, links in it, dropped line count)."""
    text, dropped = strip_model_directed(clean_text(text))
    text = text[:settings.TELEGRAM_IMPORT_MAX_INPUT_CHARS]
    links = []
    for match in URL.finditer(text):
        url = match.group(0).rstrip('.,;:!?')
        if url not in links:
            links.append(url)
    return text, links, dropped


def host_of(url):
    try:
        host = (urlsplit(url).hostname or '').lower().rstrip('.')
    except ValueError:
        return ''
    return host[4:] if host.startswith('www.') else host


def _matches(host, domains):
    return any(host == domain or host.endswith('.' + domain) for domain in domains)


def link_problem(url):
    """Why ``url`` cannot be the application link, or '' when it can."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return 'bad_link'
    host = host_of(url)
    if parts.scheme != 'https' or not host or '.' not in host or parts.username or parts.password:
        return 'bad_link'
    if re.fullmatch(r'[0-9.]+|\[[0-9a-f:]+\]', host):
        return 'bad_link'
    if _matches(host, TELEGRAM_HOSTS):
        return 'telegram_link'
    if _matches(host, SHORTENERS):
        return 'shortened_link'
    if _matches(host, SOCIAL):
        return 'social_link'
    blocked = [domain.strip().lower() for domain in settings.TELEGRAM_IMPORT_BLOCKED_LINK_DOMAINS if domain.strip()]
    if _matches(host, blocked):
        return 'not_official_link'
    return ''


def official_links(links):
    return [url for url in links if not link_problem(url)]


def article_links(links):
    """Links to the channels' own article sites: not official, but they usually link to the official page."""
    return [url for url in links if link_problem(url) == 'not_official_link']


def normalize_url(url):
    """Same page, same key: host without www, no fragment, no tracking parameters, no trailing slash."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return ''
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith(('utm_', 'fbclid', 'gclid', 'yclid', 'ref'))]
    path = re.sub(r'/+$', '', parts.path)
    return f'{host_of(url)}{path}' + (f'?{urlencode(sorted(query))}' if query else '')


def normalize_name(value):
    """Lowercase letters and digits only; years dropped, so a yearly program matches its last edition."""
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    value = re.sub(r'\b(?:19|20)\d{2}(?:\s*[-/–]\s*(?:19|20)?\d{2})?\b', ' ', value)
    value = re.sub(r'[\W_]+', ' ', value)
    return ' '.join(value.split())


def program_key(title, provider):
    return f'{normalize_name(title)}|{normalize_name(provider)}'


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value.strip()):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


class Catalog:
    """The programs already in the list, for duplicate checks within one run too."""

    def __init__(self, rows):
        self.keys = set()
        self.urls = set()
        for title, provider, url in rows:
            self.add(title, provider, url)

    def add(self, title, provider, url):
        self.keys.add(program_key(title, provider))
        if url:
            self.urls.add(normalize_url(url))

    def has(self, title, provider, url):
        return program_key(title, provider) in self.keys or bool(url and normalize_url(url) in self.urls)


def reject_reason(result, links, catalog, today):
    """The first rule ``result`` breaks, or ''. ``result`` is already validated by the formatter."""
    if not result['is_program']:
        return 'not_program'
    if not result['title'] or not result['provider']:
        return 'incomplete'
    url = result['application_url']
    if not url or url not in links:
        return 'no_official_link'
    problem = link_problem(url)
    if problem:
        return problem
    if result['deadline'] and result['deadline'] < today:
        return 'deadline_passed'
    if catalog.has(result['title'], result['provider'], url):
        return 'duplicate'
    return ''
