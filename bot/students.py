"""Reading a new student's details out of a message a counselor pasted.

Accepts the shapes counselors actually send, for example::

    Saydazimova Sofiya
    @saidazimova.safiiya@gmail.com
    +998 91 007 68 25

or with labels ("Full Name: ...", "Email: ...", "Telefon: ..."), in any order, on
one line or several. The backend checks everything again; this only splits the text.
"""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

EMAIL = re.compile(r'@?([A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)')
# A run of digits with the usual separators, at least 9 digits in all.
PHONE = re.compile(r'\+?\(?\d[\d \t().-]{7,}\d')  # never across a line break
LABEL = re.compile(
    r'^\s*(?:full\s*name|name|f\.?\s*i\.?\s*o\.?|fio|ism(?:\s*familiya)?|familiya(?:\s*ism)?|ф\.?и\.?о\.?|имя|'
    r'e-?mail|pochta|почта|phone(?:\s*number)?|tel(?:efon)?(?:\s*raqam(?:i)?)?|телефон|номер)\s*[:\-–]\s*',
    re.IGNORECASE,
)
BULLET = re.compile(r'^[\s•*\-–—\d.)]+(?=\D)')
NAME_LIMIT = 150
TASHKENT = ZoneInfo('Asia/Tashkent')


def _digits(text):
    return sum(char.isdigit() for char in text)


def parse_student(text):
    """``{'full_name', 'email', 'phone'}`` with what was found ('' for a missing part)."""
    text = text or ''
    email_match = EMAIL.search(text)
    email = email_match.group(1) if email_match else ''
    rest = EMAIL.sub(' ', text)
    phone = ''
    for match in PHONE.finditer(rest):
        if 9 <= _digits(match.group(0)) <= 15:
            phone = match.group(0).strip()
            rest = rest.replace(match.group(0), ' ', 1)
            break
    name_parts = []
    for line in rest.splitlines():
        line = LABEL.sub('', line)
        line = BULLET.sub('', line)
        line = LABEL.sub('', line).strip(' \t:,;-–—')
        if line and any(char.isalpha() for char in line):
            name_parts.append(line)
    # Notes next to the name ("11-sinf", "2-guruh") are dropped, not the whole name.
    full_name = ' '.join(word for word in ' '.join(name_parts).split() if not _digits(word))
    if len(full_name) > NAME_LIMIT:
        full_name = ''
    return {'full_name': full_name, 'email': email, 'phone': phone}


def is_complete(details):
    return all(details.get(key) for key in ('full_name', 'email', 'phone'))


def format_expiry(iso_value):
    """'2026-11-13T16:14:20+00:00' -> '13.11.2026 21:14' (Tashkent time); '' when missing or unreadable."""
    if not iso_value:
        return ''
    try:
        moment = datetime.fromisoformat(str(iso_value).replace('Z', '+00:00'))
    except ValueError:
        return ''
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(TASHKENT).strftime('%d.%m.%Y %H:%M')
