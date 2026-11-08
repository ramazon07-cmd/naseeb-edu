from datetime import date
from html import escape

from .i18n import t

PAGE_LIMIT = 3600
TELEGRAM_LIMIT = 4096
SECTIONS = ('personal', 'academics', 'tests', 'goal', 'activities', 'honors')
MONTHS = {
    'uz': ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek'],
    'ru': ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'],
    'en': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
}


def grade_label(lang, grade):
    if not grade:
        return t(lang, 'grade_unknown')
    if grade == 'gap':
        return t(lang, 'grade_gap')
    return t(lang, 'grade_name', grade=grade)


def contacts(email, phone):
    return '\n'.join(escape(value) for value in (email, phone) if value)


def render_students(data, lang):
    if not data['total']:
        return t(lang, 'no_students')
    lines = [t(lang, 'students_title', total=data['total'])]
    for group in data['groups']:
        lines.append('')
        lines.append(f"<b>{escape(t(lang, 'group_line', grade=grade_label(lang, group['grade']), count=group['count']))}</b>")
        lines.extend(escape(name) for name in group['students'])
    return '\n'.join(lines)


def _day(lang, iso):
    day = date.fromisoformat(iso)
    return f'{day.day} {MONTHS.get(lang, MONTHS["en"])[day.month - 1]}'


def render_student(item, lang, streak_available):
    lines = [t(lang, 'digest_student', name=escape(item['name']), grade=escape(grade_label(lang, item['grade'])))]
    essays = item.get('essays')
    if essays:
        line = t(lang, 'essays_line', total=essays['total'], edited=essays['edited_today'])
        if essays['words_today'] is not None:
            line += t(lang, 'words_today', words=essays['words_today'])
        lines.append('\U0001F4DD ' + line)
    streak = item.get('streak')
    if streak:
        if streak['days'] is None or not streak_available:
            lines.append('\U0001F525 ' + t(lang, 'streak_unavailable'))
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
        lines.append('\U0001F4CB ' + t(lang, 'application_line', percent=app['percent']))
        lines.append(marks)
        lines.append(t(
            lang, 'application_counts', activities=app['activities'], honors=app['honors'],
            docs_done=app['documents']['done'], docs_total=app['documents']['total'],
            apps_done=app['applications']['done'], apps_total=app['applications']['total'],
            rec_done=app['recommendations']['done'], rec_total=app['recommendations']['total'],
        ))
    return '\n'.join(lines)


def render_digest_pages(data, lang):
    """Pages of whole student blocks, each safely under Telegram's 4096 characters."""
    if not data['total_students']:
        return [t(lang, 'no_students')]
    header = t(lang, 'digest_title', date=_day(lang, data['date']), total=data['total_students'])
    pages, current = [], header
    for item in data['students']:
        block = render_student(item, lang, data['streak_available'])[:PAGE_LIMIT]
        if len(current) + len(block) + 2 > PAGE_LIMIT:
            pages.append(current)
            current = block
        else:
            current += '\n\n' + block
    pages.append(current)
    return pages
