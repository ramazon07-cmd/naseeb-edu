"""Frozen catalog snapshot from the counselor spreadsheet. Runs on each environment's own database."""
import json
from pathlib import Path

from django.db import migrations

SNAPSHOT = Path(__file__).parent / 'catalog_data' / 'portal_catalog_20260920.json'


def load_catalog(apps, schema_editor):
    snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    alias = schema_editor.connection.alias
    programs = apps.get_model('admissions', 'OpportunityProgram').objects.using(alias)
    services = apps.get_model('admissions', 'StoreItem').objects.using(alias)
    for values in snapshot['programs']:
        values = dict(values)
        key = values.pop('source_key')
        if programs.filter(source_key=key).exists():
            continue
        # A hand-curated record for the same program wins; never import a duplicate over it.
        if programs.filter(source_key__isnull=True, title=values['title']).exists():
            continue
        programs.create(source_key=key, **values)
    for values in snapshot['sample_services']:
        values = dict(values)
        key = values.pop('catalog_key')
        if services.filter(catalog_key=key).exists():
            continue
        # Preserve real offers. Only enrich the matching legacy demo descriptions.
        legacy = services.filter(catalog_key__isnull=True, title=values['title'],
                                 price_label__in=['Included', 'Consultation'], provider_name='')
        if legacy.count() == 1:
            legacy.update(catalog_key=key, **values)
        else:
            services.get_or_create(catalog_key=key, defaults=values)


class Migration(migrations.Migration):
    dependencies = [('admissions', '0034_program_sources_store_details')]
    operations = [migrations.RunPython(load_catalog, migrations.RunPython.noop)]
