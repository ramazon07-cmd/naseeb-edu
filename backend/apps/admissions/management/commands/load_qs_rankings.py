"""Add the QS World University Rankings to the university catalogue.

    python manage.py load_qs_rankings

Rows come from catalog_data/qs_world_university_rankings_2027.json (rebuilt by
scripts/build_qs_catalog.py). A university already in the catalogue keeps its
curated admission details and takes the QS rank, scores and classifications.
Running it again adds nothing and updates only changed QS data.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.admissions.catalog_cache import bump_version
from apps.admissions.catalog_match import university_key
from apps.admissions.catalog_v1 import CATALOG
from apps.admissions.models import University

DATA_FILE = Path(__file__).resolve().parents[2] / 'catalog_data' / 'qs_world_university_rankings_2027.json'


class Command(BaseCommand):
    help = 'Add the QS World University Rankings to the university catalogue.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DATA_FILE), help='Snapshot to load (default: the shipped 2027 one).')

    def handle(self, *args, **options):
        snapshot = json.loads(Path(options['file']).read_text(encoding='utf-8'))
        # load_university_catalog upserts by exact name, so new rows take the curated spelling.
        curated = {university_key(name, country): name for name, country, *_ in CATALOG}
        catalogue = {university_key(item.name, item.country): item for item in University.objects.all()}
        # QS leaves Status blank for some universities; an unknown type takes the model default.
        types = set(University.InstitutionType.values)
        default_type = University._meta.get_field('institution_type').default
        now = timezone.now()
        created, updated, duplicates, seen = [], [], [], set()
        for row in snapshot['universities']:
            key = university_key(row['name'], row['country'])
            if key in seen:
                duplicates.append(f"{row['name']} ({row['country']})")
                continue
            seen.add(key)
            university = catalogue.get(key)
            if university is None:
                university = catalogue[key] = University(
                    name=curated.get(key, row['name']),
                    country=row['country'],
                    market=University.market_for_country(row['country']),
                    institution_type=row['type'] if row['type'] in types else default_type,
                    ranking=row['rank'],
                    ranking_label=row['rank_label'],
                    qs_data=row.get('qs_data', {}),
                    catalog_source_url=snapshot['source_url'],
                )
                created.append(university)
            elif university.pk:
                qs_data = row.get('qs_data', university.qs_data)
                if (university.ranking, university.ranking_label, university.qs_data) != (row['rank'], row['rank_label'], qs_data):
                    university.ranking, university.ranking_label = row['rank'], row['rank_label']
                    university.qs_data, university.updated_at = qs_data, now
                    updated.append(university)
        with transaction.atomic():
            University.objects.bulk_create(created, batch_size=500)
            University.objects.bulk_update(updated, ['ranking', 'ranking_label', 'qs_data', 'updated_at'], batch_size=500)
        # Bulk writes skip the save signals that refresh the cached catalogue lists.
        bump_version()
        if duplicates:
            self.stdout.write(self.style.WARNING(
                f'Skipped {len(duplicates)} rows that match a university listed earlier in the snapshot: {"; ".join(duplicates)}'
            ))
        self.stdout.write(self.style.SUCCESS(
            f'Added {len(created)} universities and updated QS data for {len(updated)} from the {snapshot["source"]}.'
        ))
