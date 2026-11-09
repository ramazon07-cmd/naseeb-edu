from datetime import date, datetime
from html import escape
from math import ceil
from zoneinfo import ZoneInfo

from .i18n import t

TELEGRAM_LIMIT = 4096
PAGE_SIZE = 8
NAME_LIMIT = 28
INACTIVE_DAYS = 7
SORT_ATTENTION, SORT_AZ = 'a', 'z'
FILTER_ALL, FILTER_INACTIVE = 'a', 'i'
SECTIONS = ('personal', 'academics', 'tests', 'goal', 'activities', 'honors')
TASHKENT = ZoneInfo('Asia/Tashkent')
MONTHS = {
    'uz': ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek'],
    'ru': ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'],
    'en': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
}
DOTS = {'today': '\U0001F7E2', 'week': '\U0001F7E1', 'inactive': '\U0001F534', 'never': '⚪'}


def grade_label(lang, grade):
    if not grade:
        return t(lang, 'grade_unknown')
    if grade == 'gap':
        return t(lang, 'grade_gap')
    return t(lang, 'grade_name', grade=grade)


def contacts(email, phone):
    return '\n'.join(escape(value) for value in (email, phone) if value)


def _day(lang, value):
    day = value if isinstance(value, date) else date.fromisoformat(value)
    return f'{day.day} {MONTHS.get(lang, MONTHS["en"])[day.month - 1]}'


def _short(name):
    name = name.strip()
    return name if len(name) <= NAME_LIMIT else name[:NAME_LIMIT - 1].rstrip() + '…'


def _bar(percent):
    filled = max(0, min(5, round(percent / 20)))
    return '▰' * filled + '▱' * (5 - filled)


def _seen(item, today):
    """(bucket, whole days since the student was last seen, local datetime); bucket is today/week/inactive/never."""
    raw = item.get('last_seen_at')
    if raw:
        seen = datetime.fromisoformat(raw.replace('Z', '+00:00')).astimezone(TASHKENT)
        days = max(0, (today - seen.date()).days)
        bucket = 'today' if days == 0 else 'week' if days < INACTIVE_DAYS else 'inactive'
        return bucket, days, seen
    return ('inactive' if item.get('last_seen_expired') else 'never'), None, None


def _seen_text(lang, item, today, detail=False):
    bucket, days, seen = _seen(item, today)
    if seen is None:
        return t(lang, 'seen_expired' if item.get('last_seen_expired') else 'seen_never')
    if days == 0:
        text = t(lang, 'seen_today')
    elif days == 1:
        text = t(lang, 'seen_yesterday')
    else:
        text = t(lang, 'seen_days', days=days)
    if not detail:
        return text
    if days <= 1:
        return f'{text} {seen:%H:%M}'
    return f'{text} ({_day(lang, seen.date())})'


def _percent(item):
    return (item.get('application') or {}).get('percent', 0)


def _attention_key(item, today):
    bucket, days, _ = _seen(item, today)
    if bucket == 'never':
        rank, age = 0, 0
    elif days is None:
        rank, age = 1, 0
    else:
        rank, age = 2, -days
    return rank, age, _percent(item), item['name'].lower()


def ordered(students, sort, flt, today):
    items = list(students)
    if flt == FILTER_INACTIVE:
        items = [item for item in items if _seen(item, today)[0] in ('inactive', 'never')]
    if sort == SORT_AZ:
        items.sort(key=lambda item: item['name'].lower())
    else:
        items.sort(key=lambda item: _attention_key(item, today))
    return items


def _now(now):
    return (now or datetime.now(TASHKENT)).astimezone(TASHKENT)


def _summary(data, lang, today):
    students = data['students']
    buckets = {'today': 0, 'week': 0, 'inactive': 0, 'never': 0}
    for item in students:
        buckets[_seen(item, today)[0]] += 1
    lines = [t(lang, 'summary_activity', **buckets)]
    extras = []
    if any('essays' in item for item in students):
        extras.append(t(lang, 'summary_essays', count=sum(i['essays']['edited_today'] for i in students if 'essays' in i)))
    if any('streak' in item for item in students):
        extras.append(t(lang, 'summary_streaks', count=sum(1 for i in students if (i.get('streak') or {}).get('days'))))
    apps = [i['application']['percent'] for i in students if 'application' in i]
    if apps:
        extras.append(t(lang, 'summary_avg', percent=round(sum(apps) / len(apps))))
    if extras:
        lines.append(' · '.join(extras))
    return lines


def _row(number, item, lang, today):
    grade = f" · {escape(grade_label(lang, item['grade']))}" if item.get('grade') else ''
    head = f"{number}. <b>{escape(_short(item['name']))}</b>{grade}"
    bucket = _seen(item, today)[0]
    parts = [f"{DOTS[bucket]} {_seen_text(lang, item, today)}"]
    app = item.get('application')
    if app:
        parts.append(f"{_bar(app['percent'])} {app['percent']}%")
    essays = item.get('essays')
    if essays and essays['edited_today']:
        parts.append(f"\U0001F4DD {essays['edited_today']}")
    streak = item.get('streak')
    if streak and streak.get('shared', True) and streak.get('days'):
        parts.append(f"\U0001F525 {streak['days']}")
    return head + '\n   ' + ' · '.join(parts)


def pages_for(count):
    return max(1, ceil(count / PAGE_SIZE))


def render_list(data, lang, page=0, sort=SORT_ATTENTION, flt=FILTER_ALL, now=None):
    """(text, page, pages, [(number, student id)]) for one page of the student list under the summary.

    The page is clamped, so a stale button after the list shrank still shows the last page.
    """
    if not data['total_students']:
        return t(lang, 'no_students'), 0, 1, []
    today = _now(now).date()
    items = ordered(data['students'], sort, flt, today)
    pages = pages_for(len(items))
    page = max(0, min(page, pages - 1))
    chunk = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    lines = [t(lang, 'digest_title', date=_day(lang, data['date']), total=data['total_students'])]
    lines.extend(_summary(data, lang, today))
    if data.get('omitted'):
        lines.append(t(lang, 'omitted_line', omitted=data['omitted']))
    mode = ' · '.join((
        t(lang, 'sort_az' if sort == SORT_AZ else 'sort_attention'),
        t(lang, 'filter_inactive' if flt == FILTER_INACTIVE else 'filter_all'),
    ))
    lines.extend(['', f'<i>{mode}</i>' + (f' · {page + 1}/{pages}' if pages > 1 else '')])
    if not chunk:
        lines.append(t(lang, 'list_empty_filter'))
    numbered = []
    for offset, item in enumerate(chunk):
        number = page * PAGE_SIZE + offset + 1
        lines.append(_row(number, item, lang, today))
        if item.get('id') is not None:
            numbered.append((number, item['id']))
    return '\n'.join(lines), page, pages, numbered


def render_detail(item, lang, now=None):
    today = _now(now).date()
    bucket = _seen(item, today)[0]
    lines = [
        t(lang, 'digest_student', name=escape(item['name']), grade=escape(grade_label(lang, item['grade']))),
        f"{DOTS[bucket]} " + t(lang, 'detail_seen', when=_seen_text(lang, item, today, detail=True)),
    ]
    essays = item.get('essays')
    if essays:
        lines.append('\U0001F4DD ' + t(lang, 'essays_line', total=essays['total'], edited=essays['edited_today']))
    streak = item.get('streak')
    if streak:
        if not streak.get('shared', True):
            lines.append('\U0001F525 ' + t(lang, 'streak_not_shared'))
        elif streak['days'] > 0:
            lines.append('\U0001F525 ' + t(lang, 'streak_days', days=streak['days']))
        else:
            lines.append('\U0001F525 ' + t(lang, 'streak_none'))
    app = item.get('application')
    if app:
        marks = ' '.join(
            ('✅' if app['sections'].get(name) else '❌') + ' ' + t(lang, f'section_{name}')
            for name in SECTIONS if name in app['sections']
        )
        lines.append('\U0001F4CB ' + t(lang, 'application_line', percent=app['percent']) + f" {_bar(app['percent'])}")
        lines.append(marks)
        lines.append(t(
            lang, 'application_counts', activities=app['activities'], honors=app['honors'],
            docs_done=app['documents']['done'], docs_total=app['documents']['total'],
            apps_done=app['applications']['done'], apps_total=app['applications']['total'],
            rec_done=app['recommendations']['done'], rec_total=app['recommendations']['total'],
        ))
    return '\n'.join(lines)
