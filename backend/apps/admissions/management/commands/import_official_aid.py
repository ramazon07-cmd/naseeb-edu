"""Load researched, official-site aid data for international undergraduates (financial_aid/universities_N.json).

    python manage.py import_official_aid [file1.json ...] [--dry-run]   (no files: the shipped research data)

Rows are matched to an existing University by name and country (case-insensitive); a row without a match is
reported and never creates a university. A value that is null or "unknown" in the file never overwrites what
the database already has, and running the same file twice changes nothing.
"""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import transaction

from apps.admissions import aid_fx
from apps.admissions.models import University

AVAILABILITY = {choice.value for choice in University.IntlAidAvailability}
POLICIES = {choice.value for choice in University.IntlNeedPolicy}
DEFAULT_FILES = sorted((Path(__file__).resolve().parents[2] / 'catalog_data' / 'official_research').glob('universities_*.json'))
url_check = URLValidator(schemes=['http', 'https'])


def clean_url(value):
    value = (value or '').strip() if isinstance(value, str) else ''
    try:
        url_check(value)
    except ValidationError:
        return ''
    return value if len(value) <= 500 else ''


def on_domain(url, domain):
    """Whether ``url`` is on ``domain`` or one of its subdomains. No domain means nothing can be vouched for."""
    domain = domain.strip().lower().lstrip('.') if isinstance(domain, str) else ''
    host = (urlparse(url).hostname or '').lower()
    return bool(domain) and (host == domain or host.endswith('.' + domain))


def amount(value):
    """A whole non-negative amount, or None (booleans, text and negatives are not amounts)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(round(value))


def flag(value):
    return value if isinstance(value, bool) else None


def parse_date(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def changes_for(row):
    """The University field values this row states (only the ones it actually knows)."""
    values = {}
    availability = row.get('intl_aid_available')
    if availability in AVAILABILITY and availability != 'unknown':
        values['intl_aid_availability'] = availability
        values['offers_international_aid'] = availability in ('yes', 'limited')
    policy = row.get('intl_need_policy')
    if policy in POLICIES:
        values['intl_need_policy'] = policy
        if policy == University.IntlNeedPolicy.NEED_BLIND:
            values['need_blind'] = True
    for source, target in (
        ('need_based_for_intl', 'intl_need_based'), ('merit_for_intl', 'intl_merit_based'),
        ('full_ride_available', 'intl_full_ride'), ('meets_full_need_intl', 'intl_meets_full_need'),
    ):
        if flag(row.get(source)) is not None:
            values[target] = row[source]
    if row.get('meets_full_need_intl') is True:
        values['meets_full_need'] = True
    currency = (row.get('currency') or '').strip().upper() if isinstance(row.get('currency'), str) else ''
    if len(currency) == 3:
        values['aid_currency'] = currency
    max_award, typical = amount(row.get('max_award')), amount(row.get('typical_award'))
    min_pays = amount(row.get('min_student_pays'))
    if max_award is not None:
        values['intl_max_award'] = max_award
    if min_pays is not None:
        values['intl_min_student_pays'] = min_pays
    factor = aid_fx.rate(currency)
    if factor is not None and (max_award, typical, min_pays) != (None, None, None):
        values['aid_fx_rate'] = factor
    for name, local in (('intl_max_award_usd', max_award), ('intl_typical_award_usd', typical), ('intl_min_student_pays_usd', min_pays)):
        usd = aid_fx.to_usd(local, currency)
        if usd is not None:
            values[name] = usd
    if values.get('intl_typical_award_usd') is not None:
        values['average_aid_usd'] = values['intl_typical_award_usd']
    if isinstance(row.get('academic_year'), str) and row['academic_year'].strip():
        values['aid_academic_year'] = row['academic_year'].strip()[:20]
    url = clean_url(row.get('aid_url'))
    if url:
        values['financial_aid_url'] = url
    if isinstance(row.get('notes'), str) and row['notes'].strip():
        values['aid_application_notes'] = row['notes'].strip()
    sources = [clean_url(item) for item in row.get('sources') or [] if isinstance(item, str)]
    sources = [item for item in sources if item and on_domain(item, row.get('official_domain'))]
    if sources:
        values['aid_sources'] = sources
    verified = parse_date(row.get('verified_at'))
    if verified:
        values['aid_verified_at'] = verified
    # A row that states aid facts but was not given a date still counts as checked today.
    elif values:
        values['aid_verified_at'] = date.today()
    return values


def same(current, new):
    if isinstance(new, Decimal) and current is not None:
        return Decimal(current) == new
    return current == new


class Command(BaseCommand):
    help = 'Import official-site financial aid data for international undergraduates (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('files', nargs='*', help='Default: the research files shipped in catalog_data/official_research.')
        parser.add_argument('--dry-run', action='store_true', help='Report what would change and write nothing.')

    def handle(self, *args, **options):
        index = {}
        for university in University.objects.all():
            index[(university.name.strip().lower(), university.country.strip().lower())] = university
        totals = {'rows': 0, 'updated': 0, 'unchanged': 0, 'unmatched': 0, 'no_currency_rate': 0}
        unmatched = []
        for path in options['files'] or map(str, DEFAULT_FILES):
            try:
                rows = json.loads(Path(path).read_text(encoding='utf-8'))
            except (OSError, ValueError) as error:
                raise CommandError(f'{path}: {error}')
            if not isinstance(rows, list):
                raise CommandError(f'{path}: expected a JSON array')
            for row in rows:
                if not isinstance(row, dict):
                    continue
                totals['rows'] += 1
                key = (str(row.get('name') or '').strip().lower(), str(row.get('country') or '').strip().lower())
                university = index.get(key)
                if university is None:
                    totals['unmatched'] += 1
                    unmatched.append(f"{row.get('name')} ({row.get('country')}) in {path}")
                    continue
                values = changes_for(row)
                if values.get('aid_currency') and aid_fx.rate(values['aid_currency']) is None:
                    totals['no_currency_rate'] += 1
                diff = {name: value for name, value in values.items() if not same(getattr(university, name), value)}
                if not diff:
                    totals['unchanged'] += 1
                    continue
                totals['updated'] += 1
                if options['dry_run']:
                    continue
                with transaction.atomic():
                    for name, value in diff.items():
                        setattr(university, name, value)
                    university.save(update_fields=list(diff))
        self.stdout.write(
            f"{totals['rows']} rows: {totals['updated']} updated, {totals['unchanged']} unchanged, "
            f"{totals['unmatched']} unmatched, {totals['no_currency_rate']} in a currency without a rate "
            f"(USD fields left empty){' [dry run]' if options['dry_run'] else ''}"
        )
        for line in unmatched:
            self.stdout.write(f'UNMATCHED: {line}')
