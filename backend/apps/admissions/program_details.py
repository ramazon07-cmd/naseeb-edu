"""One set of rules for the researched program details, used by the importer and the admin catalogue API.

past_participants: at most five {name, role, year, linkedin_url, source_url}; the name is a string, the source
is an http(s) link, a LinkedIn link is only a public profile (https://linkedin.com/in/...).
benefits / who_can_apply / requirements_list: lists of short strings. Nothing is ever dropped silently to make a
list fit: the limits are well above what the official pages list.
"""
import re

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

LINKEDIN_PROFILE = re.compile(r'^https://([a-z]{2,3}\.|www\.)?linkedin\.com/in/[^/?#\s]+/?$', re.I)
MAX_PEOPLE = 5
LIST_LIMITS = {'benefits': 20, 'who_can_apply': 20, 'requirements_list': 20}
ITEM_SIZE = 300
url_check = URLValidator(schemes=['http', 'https'])


def text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def link(value, limit=1000):
    value = text(value, limit + 1)
    if not value or len(value) > limit:
        return None
    try:
        url_check(value)
    except ValidationError:
        return None
    return value


def clean_person(entry):
    """The stored form of one person, or None when the entry is unusable (no string name, no working source link)."""
    if not isinstance(entry, dict):
        return None
    name, source = text(entry.get('name'), 120), link(entry.get('source_url'))
    if not name or not source:
        return None
    profile = link(entry.get('linkedin_url'), 300)
    year = entry.get('year')
    return {
        'name': name, 'role': text(entry.get('role'), 60) or '',
        'year': year if isinstance(year, int) and not isinstance(year, bool) and 1990 <= year <= 2100 else None,
        'linkedin_url': profile if profile and LINKEDIN_PROFILE.match(profile) else None,
        'source_url': source,
    }


def clean_people(value):
    """Lenient (importer): keep the good entries, de-duplicate by name, at most five. None when nothing is left."""
    if not isinstance(value, list):
        return None
    kept, seen = [], set()
    for entry in value:
        person = clean_person(entry)
        if person and person['name'].lower() not in seen:
            seen.add(person['name'].lower())
            kept.append(person)
    return kept[:MAX_PEOPLE] or None


def clean_strings(value, limit):
    """Lenient (importer): the non-empty strings of a list, at most `limit`. None when nothing is left."""
    if not isinstance(value, list):
        return None
    items = [item for item in (text(entry, ITEM_SIZE) for entry in value if isinstance(entry, str)) if item]
    return items[:limit] or None


def check_people(value):
    """Strict (API): the cleaned list, or a ValidationError naming what is wrong."""
    if not isinstance(value, list):
        raise ValidationError('Expected a list of people.')
    if len(value) > MAX_PEOPLE:
        raise ValidationError(f'At most {MAX_PEOPLE} people.')
    cleaned = []
    for number, entry in enumerate(value, 1):
        person = clean_person(entry)
        if person is None:
            raise ValidationError(f'Person {number}: a text name and a valid http(s) source_url are required.')
        raw = entry.get('linkedin_url')
        if raw not in (None, '') and person['linkedin_url'] is None:
            raise ValidationError(f'Person {number}: linkedin_url must be a public profile (https://www.linkedin.com/in/...).')
        cleaned.append(person)
    return cleaned


def check_strings(value, limit):
    if not isinstance(value, list):
        raise ValidationError('Expected a list of text items.')
    if len(value) > limit:
        raise ValidationError(f'At most {limit} items.')
    cleaned = []
    for number, entry in enumerate(value, 1):
        item = text(entry, ITEM_SIZE + 1)
        if item is None or len(item) > ITEM_SIZE:
            raise ValidationError(f'Item {number}: must be non-empty text of at most {ITEM_SIZE} characters.')
        cleaned.append(item)
    return cleaned
