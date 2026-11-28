"""Load researched, official-site program details (programs/programs.json) into OpportunityProgram rows.

    python manage.py import_official_programs [programs.json] [--dry-run]   (no file: the shipped research data)

Rows are matched by id. Placeholder rows and ids that do not exist are skipped and reported. A value that
is null or empty in the file never overwrites what the database already has, and running the same file twice
changes nothing.

The richer details (programs_details.json: overview, benefits, who can apply, requirements, selection and up to
five public past participants from Uzbekistan) load in the same run when no file is named, or from `--details FILE`.
A participant is kept only with a name and a public source link; a LinkedIn link only if it is a profile
(linkedin.com/in/...). Nothing else about a person is read.
"""
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.admissions.models import OpportunityProgram
from apps.admissions.program_details import LIST_LIMITS, clean_people, clean_strings, link, text

PROGRAM_TYPES = {'national', 'international'}
DELIVERY = {'onsite', 'online', 'hybrid'}
DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'catalog_data' / 'official_research' / 'programs.json'
# Aggregators, forms and social pages are never an official source.
BLOCKED_HOSTS = ('opportunitiescorners', 'scholarshipscorner', 'opportunitydesk', 'docs.google', 'forms.gle', 'airtable', 'instagram', 'facebook')
DETAILS_FILE = DEFAULT_FILE.with_name('programs_details.json')


def official(url):
    host = (urlparse(url or '').hostname or '').lower()
    return bool(host) and not any(blocked in host for blocked in BLOCKED_HOSTS)


def day(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def whole(value):
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


GAP_WORDS = re.compile(
    r'(completed|graduated?|finished)(\s+from)?\s+(high|secondary)\s+school|(high|secondary)\s+school\s+graduates?|\bgraduates?\b|school[- ]leavers?|gap[- ]years?|not yet (entered|started|enrolled)|post[- ]secondary',
)
RANGE = re.compile(r'(\d{1,2})\s*(?:[-\u2010-\u2015]|to|through)\s*(\d{1,2})')
FIRST_GRADE, LAST_GRADE = 5, 11


def grade_codes(value):
    """Turn the research row's prose ("Grades 9-12", "High school", "Completed high school") into the
    comma-separated codes every reader expects (5..11 and "gap"). Empty string when nothing parses."""
    if not isinstance(value, str):
        return ''
    low = value.lower()
    picked = set()
    low = re.sub(r'\bgraduates?\s+(are\s+)?(in)?eligible|not\s+(yet\s+|already\s+)?graduated', ' ', low)
    if GAP_WORDS.search(low):
        picked.add('gap')
        low = GAP_WORDS.sub(' ', low)
    if re.search(r'high\s*school|secondary', low):
        picked.update(('9', '10', '11'))
    low = re.sub(r'\b(19|20)\d{2}\b', ' ', low)
    spans = [(int(a), int(b)) for a, b in RANGE.findall(low)]
    low = RANGE.sub(' ', low)
    spans += [(int(n), int(n)) for n in re.findall(r'\b(\d{1,2})\b', low)]
    for first, last in spans:
        first, last = min(first, last), max(first, last)
        if first > 12 or last < FIRST_GRADE:
            continue
        first, last = min(max(first, FIRST_GRADE), LAST_GRADE), min(last, LAST_GRADE)
        picked.update(str(n) for n in range(first, last + 1))
    order = [str(n) for n in range(FIRST_GRADE, LAST_GRADE + 1)] + ['gap']
    return ','.join(code for code in order if code in picked)


def changes_for(row):
    """The OpportunityProgram field values this row states (only the ones it actually knows)."""
    values = {
        'description': text(row.get('description'), 5000),
        'category': text(row.get('category'), 100),
        'country': text(row.get('country'), 120), 'city': text(row.get('city'), 120),
        'eligible_grades': grade_codes(row.get('eligible_grades')) or None, 'eligible_ages': text(row.get('eligible_ages'), 160),
        'deadline_text': text(row.get('deadline_text'), 2000),
        'fee_text': text(row.get('fee_text'), 300), 'aid_details': text(row.get('aid_details'), 300),
        'requirements': text(row.get('requirements'), 5000),
        'application_url': link(row.get('application_url')), 'source_url': link(row.get('official_url')),
        'deadline': day(row.get('next_deadline')), 'start_date': day(row.get('start_date')), 'end_date': day(row.get('end_date')),
        'fee_usd': whole(row.get('fee_usd')),
        'program_type': row.get('program_type') if row.get('program_type') in PROGRAM_TYPES else None,
        'delivery_mode': row.get('delivery_mode') if row.get('delivery_mode') in DELIVERY else None,
    }
    prose = text(row.get('eligible_grades'), 200)
    if values['eligible_grades'] and values['requirements'] and prose != values['eligible_grades']:
        values['requirements'] = text(f"Eligible grades: {prose}\n{values['requirements']}", 5000)
    for name in ('scholarship_available', 'open_to_international', 'open_to_uzbekistan'):
        values[name] = row[name] if isinstance(row.get(name), bool) else None
    sources = [item for item in (link(entry) for entry in row.get('sources') or [] if isinstance(entry, str)) if item and official(item)]
    values['official_sources'] = sources or None
    for name in ('application_url', 'source_url'):
        if values[name] and not official(values[name]):
            values[name] = None
    values = {name: value for name, value in values.items() if value is not None}
    if values.get('source_url') or sources:
        values['needs_verification'] = False
        values['official_verified_at'] = day(row.get('verified_at')) or date.today()
    if row.get('still_running') is False:
        values['is_active'] = False
    return values


def detail_changes_for(row):
    """The detail fields a programs_details.json row states. Empty or null values are left out."""
    values = {
        'overview': text(row.get('overview'), 1200),
        'team_format': text(row.get('team'), 160),
        'selection_process': text(row.get('selection_process'), 1500),
        'benefits': clean_strings(row.get('benefits'), LIST_LIMITS['benefits']),
        'who_can_apply': clean_strings(row.get('who_can_apply'), LIST_LIMITS['who_can_apply']),
        'requirements_list': clean_strings(row.get('requirements'), LIST_LIMITS['requirements_list']),
        'past_participants': clean_people(row.get('past_participants_uz')),
    }
    return {name: value for name, value in values.items() if value is not None}


def edition_changes_for(detail):
    """When the details describe a newer edition than programs.json, `edition_core` carries that one edition's
    place and dates. These replace the older values (an empty city or date clears a stale one), so a program
    never shows one edition's overview next to another edition's location and dates."""
    core = detail.get('edition_core')
    if not isinstance(core, dict):
        return {}
    # Only the keys the edition states are touched; a stated null clears the older edition's value.
    values = {}
    for name, convert in (('country', lambda v: text(v, 120) or ''), ('city', lambda v: text(v, 120) or ''), ('start_date', day), ('end_date', day),
                          ('deadline', day), ('deadline_text', lambda v: text(v, 2000) or '')):
        if name in core:
            values[name] = convert(core[name])
    # Price, delivery and apply page belong to the edition too (a winter online price is not the summer one).
    if 'fee_usd' in core:
        values['fee_usd'] = whole(core['fee_usd'])
    if 'fee_text' in core:
        values['fee_text'] = text(core['fee_text'], 300) or ''
    if core.get('delivery_mode') in DELIVERY:
        values['delivery_mode'] = core['delivery_mode']
    if 'application_url' in core:
        apply_url = link(core['application_url'])
        # An apply page is often a form host (Airtable, Google Forms, Typeform); only evidence sources must be official.
        values['application_url'] = apply_url if apply_url and apply_url.lower().startswith('https://') else ''
    if text(core.get('title'), 220):
        values['title'] = text(core.get('title'), 220)
    sources = [item for item in (link(entry) for entry in core.get('sources') or [] if isinstance(entry, str)) if item and official(item)]
    if sources:
        values['official_sources'] = sources
        values['source_url'] = sources[0]
    return values


class Command(BaseCommand):
    help = 'Import official-site program details into OpportunityProgram by id (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('file', nargs='?', default=str(DEFAULT_FILE), help='Default: the research file shipped in catalog_data/official_research.')
        parser.add_argument('--details', default=None, help='Details file (programs_details.json). Default: the shipped one, only when no program file is named.')
        parser.add_argument('--dry-run', action='store_true', help='Report what would change and write nothing.')

    def read_details(self, options):
        path = options['details'] or (str(DETAILS_FILE) if options['file'] == str(DEFAULT_FILE) else None)
        if not path:
            return {}
        try:
            rows = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise CommandError(f'{path}: {error}')
        if not isinstance(rows, list):
            raise CommandError('expected a JSON array in the details file')
        return {row['id']: row for row in rows if isinstance(row, dict) and isinstance(row.get('id'), int)}

    def handle(self, *args, **options):
        try:
            rows = json.loads(Path(options['file']).read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise CommandError(f"{options['file']}: {error}")
        if not isinstance(rows, list):
            raise CommandError('expected a JSON array')
        details = self.read_details(options)
        programs = OpportunityProgram.objects.in_bulk()
        totals = {'rows': 0, 'updated': 0, 'unchanged': 0, 'placeholder': 0, 'missing': 0, 'no_official_data': 0}
        missing = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('id'), int):
                continue
            totals['rows'] += 1
            if row.get('placeholder'):
                totals['placeholder'] += 1
                continue
            program = programs.get(row['id'])
            if program is None:
                totals['missing'] += 1
                missing.append(str(row['id']))
                continue
            values = changes_for(row)
            detail = details.get(row['id'], {})
            values.update(detail_changes_for(detail))
            values.update(edition_changes_for(detail))
            # A deadline the details state is used when neither the catalog row nor the edition has one.
            if 'deadline' not in values and not program.deadline and day(detail.get('deadline')):
                values['deadline'] = day(detail['deadline'])
            # Facts the catalog row lacks are filled from the details; an existing value is never replaced.
            for name, found in (('country', text(detail.get('country'), 120)), ('eligible_ages', text(detail.get('age_range'), 160))):
                if found and not values.get(name) and not getattr(program, name):
                    values[name] = found
            if not values:
                totals['no_official_data'] += 1
                continue
            diff = {name: value for name, value in values.items() if getattr(program, name) != value}
            if not diff:
                totals['unchanged'] += 1
                continue
            totals['updated'] += 1
            if options['dry_run']:
                continue
            with transaction.atomic():
                for name, value in diff.items():
                    setattr(program, name, value)
                program.save(update_fields=[*diff, 'updated_at'])
        self.stdout.write(
            f"{totals['rows']} rows: {totals['updated']} updated, {totals['unchanged']} unchanged, "
            f"{totals['placeholder']} placeholders skipped, {totals['no_official_data']} without official data, "
            f"{totals['missing']} ids not found{' [dry run]' if options['dry_run'] else ''}"
        )
        if missing:
            self.stdout.write('NOT FOUND: ' + ', '.join(missing))
