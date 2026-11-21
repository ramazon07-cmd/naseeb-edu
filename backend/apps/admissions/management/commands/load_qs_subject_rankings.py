"""Add the QS World University Rankings by Subject to the university catalogue.

    python manage.py load_qs_subject_rankings

Rows come from catalog_data/qs_subject_rankings_2026.json (rebuilt by
scripts/build_qs_subject_catalog.py). A row is stored only for a university already in the
catalogue, matched by catalog_match.university_key; no university is ever created. Running it
again adds nothing and changes only the ranks that differ. Run load_qs_rankings first so the
QS universities exist.
"""
import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.admissions.catalog_cache import bump_version
from apps.admissions.catalog_match import university_key
from apps.admissions.models import University, UniversitySubjectRank
from apps.admissions.subjects import INDICATORS

DATA_FILE = Path(__file__).resolve().parents[2] / 'catalog_data' / 'qs_subject_rankings_2026.json'
INDICATOR_FIELDS = tuple(f'{name}_score' for name in INDICATORS)
FIELDS = ('rank', 'rank_label', 'score', *INDICATOR_FIELDS)
TENTH = Decimal('0.1')


def indicator_scores(scores, weights):
    """The row's trailing scores (one per indicator the subject uses) as the five indicator fields; the
    others stay None. An older snapshot without them gives all None."""
    used = iter(scores)
    values = {}
    for field, weight in zip(INDICATOR_FIELDS, weights):
        value = next(used, None) if weight else None
        values[field] = None if value is None else Decimal(str(value)).quantize(TENTH)
    return values


class Command(BaseCommand):
    help = 'Add the QS World University Rankings by Subject to the university catalogue.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DATA_FILE), help='Snapshot to load (default: the shipped 2026 one).')

    def handle(self, *args, **options):
        snapshot = json.loads(Path(options['file']).read_text(encoding='utf-8'))
        year = snapshot['year']
        catalogue = {university_key(item.name, item.country): item.pk for item in University.objects.only('id', 'name', 'country')}
        weights = {subject['code']: subject.get('weights', ()) for subject in snapshot['subjects']}
        wanted, unmatched = {}, set()
        for code, rank, label, name, country, score, *scores in snapshot['rows']:
            pk = catalogue.get(university_key(name, country))
            if pk is None:
                unmatched.add((name, country))
                continue
            key = (pk, code)
            # Two QS spellings of one catalogue university: keep the better rank.
            if key not in wanted or rank < wanted[key]['rank']:
                wanted[key] = {'rank': rank, 'rank_label': label, 'score': score, **indicator_scores(scores, weights.get(code, ()))}
        existing = {(row.university_id, row.subject_code): row for row in UniversitySubjectRank.objects.filter(year=year)}
        created, updated = [], []
        for (pk, code), values in wanted.items():
            row = existing.get((pk, code))
            if row is None:
                created.append(UniversitySubjectRank(university_id=pk, subject_code=code, year=year, **values))
            elif any(getattr(row, field) != values[field] for field in FIELDS):
                for field in FIELDS:
                    setattr(row, field, values[field])
                updated.append(row)
        stale = [row.pk for key, row in existing.items() if key not in wanted]
        with transaction.atomic():
            UniversitySubjectRank.objects.bulk_create(created, batch_size=1000)
            UniversitySubjectRank.objects.bulk_update(updated, list(FIELDS), batch_size=1000)
            UniversitySubjectRank.objects.filter(pk__in=stale).delete()
        # Bulk writes skip the save signals that refresh the cached catalogue lists and the fit map.
        bump_version()
        institutions = {(row[3], row[4]) for row in snapshot['rows']}
        matched = len(institutions) - len(unmatched)
        self.stdout.write(self.style.SUCCESS(
            f'{snapshot["source"]}: {matched} of {len(institutions)} institutions matched the catalogue '
            f'({len(unmatched)} unmatched, none created); added {len(created)} subject ranks, '
            f'updated {len(updated)}, removed {len(stale)}.'
        ))
