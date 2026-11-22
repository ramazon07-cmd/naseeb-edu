"""Checks in code, before and after the AI. Nothing here calls a model.

A post's text (and any page read for it) is untrusted. Before it is sent: invisible
characters are removed and lines addressed to an AI are dropped (with their links).
After the AI: every deadline, date, fee and age the AI returns must be written in
the text it was given (otherwise it is cleared); the application link must be one
of the candidate links (the post's own, or those on the channel's article it points
to) and point at an official page; the program must not have ended; and it must not
already exist, except as a past edition whose next edition this post announces.
"""
import re
import unicodedata
from datetime import date, timedelta
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
# OpportunityProgram.application_url is a URLField(max_length=1000).
MAX_URL_CHARS = 1000
# Query keys that only track where a click came from.
TRACKING_KEYS = {'ref', 'ref_src', 'referrer', 'fbclid', 'gclid', 'yclid', 'igshid', 'mc_cid', 'mc_eid'}
# A post with no deadline older than this is about something that is most likely over.
STALE_POST_DAYS = 120


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
    if len(url) > MAX_URL_CHARS:
        return 'bad_link'
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
             if not (key.lower() in TRACKING_KEYS or key.lower().startswith('utm_'))]
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


def is_homepage(url):
    """A site's front page: shared by every program of one organiser, so not a duplicate key."""
    try:
        return not urlsplit(url).path.strip('/')
    except ValueError:
        return True


class Catalog:
    """The programs already in the list, for duplicate checks within one run too.

    Each key (title + provider, or the application page) remembers the row's pk and
    deadline, so a new edition of a yearly program can renew its old row.
    """

    def __init__(self, rows):
        self.keys = {}
        self.urls = {}
        for pk, title, provider, url, deadline in rows:
            self.add(pk, title, provider, url, deadline)

    def add(self, pk, title, provider, url, deadline=None):
        entry = (pk, deadline)
        self.keys[program_key(title, provider)] = entry
        if url and not is_homepage(url):
            self.urls[normalize_url(url)] = entry

    def match(self, title, provider, url):
        """(pk, deadline) of the existing program this one duplicates, or None."""
        found = self.keys.get(program_key(title, provider))
        if found is None and url and not is_homepage(url):
            found = self.urls.get(normalize_url(url))
        return found

    def has(self, title, provider, url):
        return self.match(title, provider, url) is not None


def renews(existing, result, today):
    """Whether ``result`` is the next edition of ``existing`` (a row whose deadline is past or unknown)."""
    _, old_deadline = existing
    new_deadline = result['deadline']
    return bool(new_deadline and new_deadline >= today and (old_deadline is None or old_deadline < today))


# ---------------------------------------------------------------- grounding
# Month names as they are written in the channels: English, Uzbek (Latin and
# Cyrillic) and Russian. Stems, so that "марта" and "martgacha" match.
MONTHS = {
    1: ('jan', 'yanvar', 'январ'), 2: ('feb', 'fevral', 'феврал'), 3: ('mar', 'март'),
    4: ('apr', 'aprel', 'апрел'), 5: ('may', 'ма[йя]'), 6: ('jun', 'iyun', 'июн'),
    7: ('jul', 'iyul', 'июл'), 8: ('aug', 'avgust', 'август'), 9: ('sep', 'sentyabr', 'сентябр'),
    10: ('oct', 'okt', 'октябр'), 11: ('nov', 'noyabr', 'ноябр'), 12: ('dec', 'dekabr', 'декабр'),
}
FREE_WORDS = re.compile(
    r'\b(?:free|free of charge|no (?:application |participation )?fee|bepul|tekin|бесплатн\w*|бепул|текин)\b',
    re.IGNORECASE,
)
NUMBER = r'\d{1,3}(?:[ ,\u00a0\u202f]\d{3})+|\d+'
USD_AMOUNT = re.compile(
    rf'(?:\$|US\$|USD|US dollars?)\s*({NUMBER})(?:[.,]\d{{1,2}})?(?!\d)'
    rf'|(?<![\d.,])({NUMBER})(?:[.,]\d{{1,2}})?\s*(?:\$|USD|US dollars?|dollars?|долл\w*|dollar\w*)',
    re.IGNORECASE,
)


def _flat(text):
    return ' '.join(unicodedata.normalize('NFKC', str(text or '')).casefold().split())


def _number_in(number, text):
    return bool(re.search(rf'(?<!\d)0?{int(number)}(?!\d)', text))


def date_in_text(value, text):
    """Whether ``text`` writes the date ``value``: day with month name, or a numeric date."""
    text = _flat(text)
    day, month, year = value.day, value.month, value.year
    numeric = (
        rf'(?<!\d){year}[-./]0?{month}[-./]0?{day}(?!\d)',
        rf'(?<!\d)0?{day}[-./]0?{month}[-./](?:{year}|{year % 100:02d})(?!\d)',
        rf'(?<!\d)0?{month}/0?{day}/{year}(?!\d)',
    )
    if any(re.search(pattern, text) for pattern in numeric):
        return True
    names = '|'.join(MONTHS[month])
    day_pattern = rf'(?<!\d)0?{day}(?:st|nd|rd|th|-?(?:go|го))?(?!\d)'
    return bool(
        re.search(rf'{day_pattern}[\s.,/-]*(?:of\s+)?(?:{names})', text)
        or re.search(rf'\b(?:{names})\w*[\s.,/-]*{day_pattern}', text)
    )


def usd_amounts(text):
    amounts = set()
    for match in USD_AMOUNT.finditer(str(text or '')):
        raw = match.group(1) or match.group(2)
        amounts.add(int(re.sub(r'\D', '', raw)))
    return amounts


def ground(result, source):
    """Clear every date, fee and age in ``result`` that ``source`` (the exact text the AI was
    given) does not state, and note it in ``result['problems']``. Returns ``result``."""
    flat = _flat(source)
    problems = result['problems']

    deadline = result['deadline']
    if deadline:
        written = _flat(result['deadline_text'])
        year = rf'(?<!\d)(?:{deadline.year}|{deadline.year % 100:02d})(?!\d)'
        if not (written and written in flat and date_in_text(deadline, written) and re.search(year, written)):
            result['deadline'] = None
            problems.append('deadline not confirmed in source')
    if result['deadline_text'] and _flat(result['deadline_text']) not in flat:
        result['deadline_text'] = ''
    for key in ('start_date', 'end_date'):
        if result[key] and not date_in_text(result[key], flat):
            result[key] = None
            problems.append(f'{key.replace("_", " ")} not confirmed in source')

    fee = result['fee_usd']
    if fee is not None:
        confirmed = FREE_WORDS.search(flat) if fee == 0 else fee in usd_amounts(source)
        if not confirmed:
            result['fee_usd'] = None
            problems.append('fee not confirmed in source')

    ages = result['eligible_ages']
    if ages:
        numbers = re.findall(r'\d+', ages)
        if not numbers or not all(_number_in(number, flat) for number in numbers):
            result['eligible_ages'] = ''
            problems.append('ages not confirmed in source')
    grades = [grade for grade in result['eligible_grades'].split(',') if grade]
    if grades:
        numeric = [int(grade) for grade in grades if grade.isdigit()]
        ends = {min(numeric), max(numeric)} if numeric else set()
        if not all(_number_in(number, flat) for number in ends) or ('gap' in grades and 'gap' not in flat):
            result['eligible_grades'] = ''
            problems.append('grades not confirmed in source')
    return result


def reject_reason(result, links, today, posted_at=''):
    """The first rule ``result`` breaks, or ''. ``result`` is validated and grounded.
    Duplicates are checked by the importer (a past edition may be renewed instead)."""
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
    if result['end_date'] and result['end_date'] < today:
        return 'deadline_passed'
    if not result['deadline']:
        if result['start_date'] and result['start_date'] < today:
            return 'deadline_passed'
        posted = parse_date((posted_at or '')[:10])
        if posted and posted < today - timedelta(days=STALE_POST_DAYS):
            return 'stale_post'
    return ''
