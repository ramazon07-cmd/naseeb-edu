"""The student's CV (Harvard style): a whitelist of what a résumé may show.

Every value is copied here field by field, so nothing private (family income,
guardian, budget, notes, counselor comments, essays, applications, readiness,
review states, …) can reach the page that prints it.

Records the student keeps in the portfolio (Activity, Internship, Research,
Project, Honor, Achievement) are the source of truth: they carry dates and
places. The onboarding answers (application_profile.activities / .honors)
fill in only what no record already covers, so one olympiad entered in both
places prints once: an onboarding row is dropped when a record names the same
item (see same_item), never because of another onboarding row. An Achievement
that repeats an Honor is dropped as well. Entries of one section that name the
same organization print once, with one role line per role (President, Grade 11
above Secretary, Grade 9). The frontend formats the dates (frontend/src/lib/cv.js).
"""
import math
import re

from .onboarding import CERTIFICATE_RULES

SECTION_ORDER = ('education', 'experience', 'leadership', 'honors')

CERTIFICATE_LABELS = {
    'toefl': 'TOEFL iBT',
    'duolingo': 'Duolingo English Test',
    'pte': 'PTE Academic',
    'act': 'ACT',
    'cambridge': 'Cambridge English',
}
assert CERTIFICATE_LABELS.keys() == CERTIFICATE_RULES.keys()

# Onboarding activity types that read as work or research, not leadership.
EXPERIENCE_TYPES = {'Research', 'Internship'}
HONOR_LEVELS = {'school': 'School', 'regional': 'Regional', 'national': 'National', 'international': 'International'}
GRADE_LABELS = {'8': 'Grade 8', '9': 'Grade 9', '10': 'Grade 10', '11': 'Grade 11', '12': 'Grade 12', 'gap': 'Gap year'}

_BULLET = re.compile(r'^\s*(?:[-*•●▪◦]|\d+[.)])\s*')
_NOT_WORD = re.compile(r'[^\w]+')
_NUMBER = re.compile(r'\d+')
# A shorter name is the same item as a longer one that contains it only when it
# has this many words and covers this share of the longer one's words, so
# "Volunteering" never matches "Red Crescent Volunteering" while "Regional Math
# Olympiad" matches "Regional Math Olympiad - Gold medal".
MIN_CONTAINED_WORDS = 3
MIN_CONTAINED_SHARE = 0.6


def text(value):
    return str(value).strip() if value is not None else ''


def bullets(*values):
    """Free text as bullet points: one per non-empty line, list markers dropped."""
    out = []
    for value in values:
        for line in text(value).splitlines():
            line = _BULLET.sub('', line).strip()
            if line:
                out.append(line)
    return out


def norm(value):
    return ' '.join(_NOT_WORD.sub(' ', text(value).casefold()).split())


def same_item(a, b):
    """Equal names (case, punctuation and word order aside), or one inside the other by enough words."""
    a, b = norm(a).split(), norm(b).split()
    if not a or not b:
        return False
    if sorted(a) == sorted(b):
        return True
    short, long = sorted((a, b), key=len)
    if len(short) < MIN_CONTAINED_WORDS or len(short) < MIN_CONTAINED_SHARE * len(long):
        return False
    return any(long[i:i + len(short)] == short for i in range(len(long) - len(short) + 1))


class Dedup:
    """Names of portfolio records; an onboarding answer that matches one is dropped."""

    def __init__(self):
        self.names = []

    def seen(self, *names):
        return any(same_item(name, known) for name in names if norm(name) for known in self.names)

    def add(self, *names):
        self.names.extend(name for name in names if norm(name))


def iso(value):
    return value.isoformat() if value else None


def entry(*, organization='', location='', title='', note='', link='', start=None, end=None, current=False, date=None, date_text='', items=()):
    """One CV block: line 1 organization | location, line 2 title | dates, then bullets."""
    return {
        'organization': text(organization),
        'location': text(location),
        'title': text(title),
        'note': text(note),
        'link': text(link),
        'start': iso(start),
        'end': iso(end),
        'current': bool(current),
        'date': iso(date),
        'date_text': text(date_text),
        'bullets': [item for item in items if item],
        'roles': [],
    }


ROLE_KEYS = ('title', 'note', 'start', 'end', 'current', 'date', 'date_text', 'bullets')


def grade_rank(label):
    """How recent a school-year label is: Gap year > Grade 12 > … > Grade 9; "Grades 9, 10" counts as 10."""
    words = norm(label)
    if 'gap' in words:
        return 13
    numbers = [int(n) for n in _NUMBER.findall(words) if int(n) <= 13]
    return max(numbers, default=0)


def sort_key(item):
    """Newest first: ongoing, then by end (or single) date and start, then by school year; undated last."""
    if item['roles']:
        item = item['roles'][0]
    end = item['date'] or item['end'] or item['start'] or ''
    dated = 0 if end else 1 if item['date_text'] else 2
    return (not item['current'], dated, _desc(end), _desc(item['start'] or ''), -grade_rank(item['date_text']))


def merge_organizations(items):
    """Sorted entries, those naming one organization merged into one with a role line each."""
    groups = {}
    for item in sorted(items, key=sort_key):
        groups.setdefault(norm(item['organization']) or id(item), []).append(item)
    merged = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        first = group[0]
        combined = entry(
            organization=first['organization'],
            location=next((item['location'] for item in group if item['location']), ''),
            link=next((item['link'] for item in group if item['link']), ''),
        )
        combined['roles'] = [{key: item[key] for key in ROLE_KEYS} for item in group]
        merged.append(combined)
    return sorted(merged, key=sort_key)


def _desc(value):
    return tuple(-ord(char) for char in value)


def joined(*parts, sep=' | '):
    return sep.join(text(part) for part in parts if text(part))


def location_of(answers):
    return joined(answers.get('city'), answers.get('country'), sep=', ')


def gpa_text(profile):
    if profile.gpa is None:
        return ''
    scale = profile.effective_gpa_scale
    if scale in (4, 5):
        return f'GPA: {profile.gpa:.2f}/{scale}.00'
    # A 100-point GPA keeps the student's decimals, without padding whole numbers.
    value = f'{profile.gpa:.2f}'.rstrip('0').rstrip('.') if scale == 100 else f'{profile.gpa:.2f}'
    return f'GPA: {value}/{scale}' if scale else f'GPA: {value}'


def rank_text(answers):
    rank, size = answers.get('class_rank'), answers.get('class_size')
    if not rank:
        return ''
    if size:
        top = max(1, math.ceil(int(rank) * 100 / int(size)))
        return f'Class rank: {rank} of {size} (Top {top}%)'
    return f'Class rank: {rank}'


def subjects_text(answers):
    groups = {}
    for row in answers.get('subjects') or []:
        if isinstance(row, dict) and text(row.get('subject')):
            score = f" ({row['score']})" if row.get('score') not in (None, '') else ''
            groups.setdefault(row.get('type') or 'AP', []).append(f"{text(row['subject'])}{score}")
    return [f"{kind}: {', '.join(items)}" for kind, items in groups.items()]


def education(profile, answers):
    if not text(profile.school_name):
        return []
    year = answers.get('graduation_year')
    interests = [text(item) for item in answers.get('interests') or [] if text(item)]
    grade = GRADE_LABELS.get(profile.grade, '')
    return [entry(
        organization=profile.school_name,
        location=location_of(answers),
        title=joined('High School Diploma', grade if profile.grade != 'gap' else '', sep=', '),
        note=f"Intended fields of study: {', '.join(interests)}" if interests else '',
        date_text=f'Class of {year}' if year else '',
        items=[gpa_text(profile), rank_text(answers), *subjects_text(answers)],
    )]


def experience(profile, dedup):
    items = []
    for row in profile.internships.all():
        items.append(entry(
            organization=row.organization, location=row.location, title=row.position,
            start=row.start_date, end=None if row.is_current else row.end_date, current=row.is_current,
            items=bullets(row.description),
        ))
        dedup.add(row.organization)
    for row in profile.researches.all():
        items.append(entry(
            organization=row.title, link=row.link, title=joined(row.role, row.field),
            start=row.start_date, end=row.end_date,
            items=[*bullets(row.summary), f'Outcome: {text(row.outcome)}' if text(row.outcome) else ''],
        ))
        dedup.add(row.title)
    for row in profile.projects.all():
        items.append(entry(
            organization=row.title, link=row.link, title=row.role, date=row.date,
            items=[
                *bullets(row.description),
                f'Impact: {text(row.impact)}' if text(row.impact) else '',
                f'Technologies: {text(row.technologies)}' if text(row.technologies) else '',
            ],
        ))
        dedup.add(row.title)
    return items


def leadership(profile, dedup):
    items = []
    for row in profile.activities.all():
        hours = joined(
            f'{row.hours_per_week} hours/week' if row.hours_per_week else '',
            f'{row.weeks_per_year} weeks/year' if row.weeks_per_year else '', sep=', ',
        )
        items.append(entry(
            organization=row.name, location=row.location, title=row.role,
            start=row.start_date, end=row.end_date,
            items=[*bullets(row.description), text(row.impact), hours],
        ))
        dedup.add(row.name)
    return items


def onboarding_activities(answers, dedup, awards, experience_items, leadership_items):
    for row in answers.get('activities') or []:
        if not isinstance(row, dict):
            continue
        name = text(row.get('organization')) or text(row.get('position'))
        keys = (row.get('organization'), joined(row.get('position'), row.get('organization'), sep=' '))
        if not name or dedup.seen(*keys) or awards.seen(*keys):
            continue
        hours = joined(
            f"{row['hours']} hours/week" if row.get('hours') else '',
            f"{row['weeks']} weeks/year" if row.get('weeks') else '', sep=', ',
        )
        grades = text(row.get('grades'))
        item = entry(
            organization=name, title=row.get('position') if text(row.get('organization')) else '',
            date_text=(f'Grade {grades}' if grades.isdigit() else f'Grades {grades}') if grades[:1].isdigit() else grades,
            items=[*bullets(row.get('description')), hours],
        )
        (experience_items if row.get('type') in EXPERIENCE_TYPES else leadership_items).append(item)


def honors(profile, answers, awards):
    items = []
    for row in profile.honors.all():
        items.append(entry(
            organization=row.title, location=HONOR_LEVELS.get(row.level, ''), title=row.issuer,
            date=row.award_date, items=bullets(row.description),
        ))
        awards.add(row.title)
    for row in profile.achievements.all():
        if awards.seen(row.title):
            continue
        items.append(entry(
            organization=row.title, title=row.get_category_display() if row.category != 'other' else '',
            date=row.date, items=[*bullets(row.description), text(row.impact)],
        ))
        awards.add(row.title)
    for row in answers.get('honors') or []:
        if not isinstance(row, dict):
            continue
        name = text(row.get('project')) or text(row.get('role'))
        if not name or awards.seen(row.get('project'), joined(row.get('role'), row.get('project'), sep=' ')):
            continue
        grade = text(row.get('grade'))
        items.append(entry(
            organization=name, location=row.get('recognition'),
            title=row.get('role') if text(row.get('project')) else '',
            date_text=GRADE_LABELS.get(grade, grade),
            items=bullets(row.get('description')),
        ))
    return items


def test_scores(profile, answers):
    scores = []
    if profile.sat_status == 'taken' and profile.sat_score:
        sections = joined(
            f'Reading and Writing {profile.sat_superscore_reading or profile.sat_reading}' if profile.sat_reading else '',
            f'Math {profile.sat_superscore_math or profile.sat_math}' if profile.sat_math else '', sep=', ',
        )
        scores.append(f'SAT {profile.sat_score}' + (f' ({sections})' if sections else ''))
    if profile.ielts_status == 'taken' and profile.ielts_score is not None:
        scores.append(f'IELTS {profile.ielts_score:.1f}')
    for row in answers.get('certificates') or []:
        if not isinstance(row, dict) or text(row.get('score')) == '':
            continue
        label = CERTIFICATE_LABELS.get(row.get('type')) or text(row.get('name'))
        if label:
            scores.append(f"{label} {text(row['score'])}")
    return scores


def additional(profile, answers):
    languages = [
        f"{text(row.get('name'))} ({text(row.get('level'))})" if text(row.get('level')) else text(row.get('name'))
        for row in answers.get('languages') or [] if isinstance(row, dict) and text(row.get('name'))
    ]
    rows = [
        ('languages', ', '.join(languages)),
        ('test_scores', ', '.join(test_scores(profile, answers))),
        ('skills', ', '.join(text(item) for item in answers.get('skills') or [] if text(item))),
        ('interests', ', '.join(text(item) for item in answers.get('hobbies') or [] if text(item))),
    ]
    return [{'key': key, 'value': value} for key, value in rows if value]


def build_cv(profile):
    """The CV of one student, as plain JSON."""
    answers = profile.application_profile or {}
    user = profile.user
    dedup = Dedup()
    awards = Dedup()
    experience_items = experience(profile, dedup)
    leadership_items = leadership(profile, dedup)
    honor_items = honors(profile, answers, awards)
    onboarding_activities(answers, dedup, awards, experience_items, leadership_items)
    sections = {
        'education': education(profile, answers),
        'experience': merge_organizations(experience_items),
        'leadership': merge_organizations(leadership_items),
        'honors': merge_organizations(honor_items),
    }
    name = ' '.join(part for part in (text(user.first_name), text(answers.get('middle_name')), text(user.last_name)) if part)
    return {
        'header': {
            'name': name or user.username,
            'email': text(user.email),
            'phone': text(user.phone),
            'location': location_of(answers),
            'links': [link for link in (text(answers.get('linkedin_url')), text(answers.get('website_url'))) if link],
        },
        'sections': [{'key': key, 'entries': sections[key]} for key in SECTION_ORDER if sections[key]],
        'additional': additional(profile, answers),
    }
