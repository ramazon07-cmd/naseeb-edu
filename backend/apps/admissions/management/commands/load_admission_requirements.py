"""Load entry requirements for students from Uzbekistan into the university catalogue.

    python manage.py load_admission_requirements

Rows come from catalog_data/admission_requirements.json: a credential route, an IELTS
minimum, an admit rate for students from abroad or an entrance exam, each with the
university page it comes from. Only the fields a row gives are written, so running it
again changes nothing. Universities not in the catalogue are listed and skipped.
"""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.admissions.catalog_cache import bump_version
from apps.admissions.catalog_match import university_key
from apps.admissions.models import University

DATA_FILE = Path(__file__).resolve().parents[2] / 'catalog_data' / 'admission_requirements.json'
# JSON key -> (University field, parser).
FIELDS = {
    'credential_route': ('credential_route', str),
    'ielts_min': ('ielts_min', Decimal),
    'intl_acceptance_rate': ('intl_acceptance_rate', Decimal),
    'intl_need_policy': ('intl_need_policy', str),
    'entrance_exam': ('entrance_exam', str),
    'source': ('requirements_source_url', str),
    'verified': ('requirements_verified_at', date.fromisoformat),
}
CHOICES = {
    'credential_route': set(University.CredentialRoute.values),
    'intl_need_policy': set(University.IntlNeedPolicy.values),
}


class Command(BaseCommand):
    help = 'Load entry requirements for students from Uzbekistan into the university catalogue.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DATA_FILE), help='Requirements file to load.')

    def handle(self, *args, **options):
        rows = json.loads(Path(options['file']).read_text(encoding='utf-8'))['universities']
        catalogue = {university_key(item.name, item.country): item for item in University.objects.all()}
        updated, missing = 0, []
        with transaction.atomic():
            for row in rows:
                if not row.get('source'):
                    raise ValueError(f'{row["name"]}: every requirement needs its source page.')
                university = catalogue.get(university_key(row['name'], row['country']))
                if university is None:
                    missing.append(row['name'])
                    continue
                changed = []
                for key, (field, parse) in FIELDS.items():
                    if key not in row:
                        continue
                    value = parse(row[key])
                    if key in CHOICES and value not in CHOICES[key]:
                        raise ValueError(f'{row["name"]}: unknown {key} {value!r}.')
                    if getattr(university, field) != value:
                        setattr(university, field, value)
                        changed.append(field)
                if changed:
                    university.save(update_fields=changed)
                    updated += 1
        if updated:
            bump_version()
        self.stdout.write(f'Updated {updated} universities; {len(rows) - updated - len(missing)} already current.')
        for name in missing:
            self.stdout.write(f'Not in the catalogue, skipped: {name}')
