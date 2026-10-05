"""Fill the catalogue's US universities from the College Scorecard snapshot.

    python manage.py load_college_scorecard

Rows come from catalog_data/college_scorecard_2026.json (rebuilt by
scripts/build_scorecard_catalog.py) and are matched by their QS name, so run
load_qs_rankings first. Only empty fields are filled: curated values stay, and
running it again changes nothing. The price is the full yearly cost of
attendance, what a student without aid pays.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.admissions.catalog_cache import bump_version
from apps.admissions.catalog_match import university_key
from apps.admissions.models import University

DATA_FILE = Path(__file__).resolve().parents[2] / 'catalog_data' / 'college_scorecard_2026.json'
# Snapshot field -> University field.
FIELDS = {
    'acceptance_rate': 'acceptance_rate', 'sat_min': 'sat_min', 'sat_max': 'sat_max', 'act_min': 'act_min',
    'act_max': 'act_max', 'cost_usd': 'net_price_usd', 'tuition_usd': 'tuition_usd',
    'undergrad_enrollment': 'undergrad_enrollment', 'city': 'city', 'website': 'website',
    'campus_setting': 'campus_setting',
}


class Command(BaseCommand):
    help = 'Fill US universities in the catalogue from the College Scorecard snapshot.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DATA_FILE), help='Snapshot to load (default: the shipped 2026 one).')

    def handle(self, *args, **options):
        snapshot = json.loads(Path(options['file']).read_text(encoding='utf-8'))
        catalogue = {
            university_key(item.name, item.country): item
            for item in University.objects.filter(market=University.Market.US)
        }
        now = timezone.now()
        changed, written, missing = [], {'updated_at'}, []
        for row in snapshot['universities']:
            university = catalogue.get(university_key(row['name'], 'United States'))
            if university is None:
                missing.append(row['name'])
                continue
            fields = [field for source, field in FIELDS.items() if row.get(source) is not None and getattr(university, field) in (None, '')]
            for source, field in FIELDS.items():
                if field in fields:
                    setattr(university, field, row[source])
            # A flag has no blank: take Scorecard's word only where it says test-optional.
            if row.get('test_optional') and not university.test_optional:
                university.test_optional = True
                fields.append('test_optional')
            if fields:
                university.updated_at = now
                changed.append(university)
                written.update(fields)
        with transaction.atomic():
            University.objects.bulk_update(changed, sorted(written), batch_size=200)
        # Bulk writes skip the save signals that refresh the cached catalogue lists.
        bump_version()
        note = f' {len(missing)} are not in the catalogue yet: run load_qs_rankings first.' if missing else ''
        self.stdout.write(self.style.SUCCESS(f'Filled {len(changed)} universities from the {snapshot["source"]}.{note}'))
