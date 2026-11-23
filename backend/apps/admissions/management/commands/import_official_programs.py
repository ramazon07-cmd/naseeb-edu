"""Load researched, official-site program details (programs/programs.json) into OpportunityProgram rows.

    python manage.py import_official_programs programs.json [--dry-run]

Rows are matched by id. Placeholder rows and ids that do not exist are skipped and reported. A value that
is null or empty in the file never overwrites what the database already has, and running the same file twice
changes nothing. No participant or winner names are read: only the fields below.
"""
import json
from datetime import date
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import transaction

from apps.admissions.models import OpportunityProgram

PROGRAM_TYPES = {'national', 'international'}
DELIVERY = {'onsite', 'online', 'hybrid'}
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


def day(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def whole(value):
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def changes_for(row):
    """The OpportunityProgram field values this row states (only the ones it actually knows)."""
    values = {
        'title': text(row.get('title'), 220), 'provider': text(row.get('provider'), 180),
        'description': text(row.get('description'), 5000),
        'category': text(row.get('category'), 100),
        'country': text(row.get('country'), 120), 'city': text(row.get('city'), 120),
        'eligible_grades': text(row.get('eligible_grades'), 120), 'eligible_ages': text(row.get('eligible_ages'), 160),
        'deadline_text': text(row.get('deadline_text'), 2000),
        'fee_text': text(row.get('fee_text'), 300), 'aid_details': text(row.get('aid_details'), 300),
        'requirements': text(row.get('requirements'), 5000),
        'application_url': link(row.get('application_url')), 'source_url': link(row.get('official_url')),
        'deadline': day(row.get('next_deadline')), 'start_date': day(row.get('start_date')), 'end_date': day(row.get('end_date')),
        'fee_usd': whole(row.get('fee_usd')),
        'program_type': row.get('program_type') if row.get('program_type') in PROGRAM_TYPES else None,
        'delivery_mode': row.get('delivery_mode') if row.get('delivery_mode') in DELIVERY else None,
    }
    for name in ('scholarship_available', 'open_to_international', 'open_to_uzbekistan'):
        values[name] = row[name] if isinstance(row.get(name), bool) else None
    sources = [item for item in (link(entry) for entry in row.get('sources') or [] if isinstance(entry, str)) if item]
    values['official_sources'] = sources or None
    values = {name: value for name, value in values.items() if value is not None}
    if values.get('source_url') or sources:
        values['needs_verification'] = False
        values['official_verified_at'] = day(row.get('verified_at')) or date.today()
    if row.get('still_running') is False:
        values['is_active'] = False
    return values


class Command(BaseCommand):
    help = 'Import official-site program details into OpportunityProgram by id (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--dry-run', action='store_true', help='Report what would change and write nothing.')

    def handle(self, *args, **options):
        try:
            rows = json.loads(Path(options['file']).read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise CommandError(f"{options['file']}: {error}")
        if not isinstance(rows, list):
            raise CommandError('expected a JSON array')
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
