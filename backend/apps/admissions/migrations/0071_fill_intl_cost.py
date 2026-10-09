"""Fill the international cost of attendance (0069) from the shipped Scorecard snapshot.

Deploys only run ``migrate``, so without this every US price is empty until someone runs
``load_college_scorecard``. Rows are matched like that command (``catalog_match.university_key``)
and only empty values are filled: ``intl_cost_usd`` and the city, with ``search_text``
refreshed where the city changes.
"""
import json
from pathlib import Path

from django.db import migrations

from apps.admissions.catalog_match import university_key
from apps.admissions.search_text import university_search_text

# load_college_scorecard.DATA_FILE, without importing the command (it imports the current models).
DATA_FILE = Path(__file__).resolve().parents[1] / 'catalog_data' / 'college_scorecard_2026.json'


def fill_intl_cost(apps, schema_editor):
    University = apps.get_model('admissions', 'University')
    snapshot = json.loads(DATA_FILE.read_text(encoding='utf-8'))
    catalogue = {university_key(row.name, row.country): row for row in University.objects.filter(market='us')}
    changed, fields = [], set()
    for entry in snapshot['universities']:
        university = catalogue.get(university_key(entry['name'], 'United States'))
        if university is None:
            continue
        written = []
        if university.intl_cost_usd is None and entry.get('intl_cost_usd') is not None:
            university.intl_cost_usd = entry['intl_cost_usd']
            written.append('intl_cost_usd')
        if not university.city and entry.get('city'):
            university.city = entry['city']
            university.search_text = university_search_text(university.name, university.city, university.country)
            written += ['city', 'search_text']
        if written:
            changed.append(university)
            fields.update(written)
    if changed:
        University.objects.bulk_update(changed, sorted(fields), batch_size=200)
        from apps.admissions.catalog_cache import bump_version

        bump_version()


class Migration(migrations.Migration):
    dependencies = [('admissions', '0070_university_search_text')]

    operations = [migrations.RunPython(fill_intl_cost, migrations.RunPython.noop)]
