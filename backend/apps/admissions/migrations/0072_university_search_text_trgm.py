"""A pg_trgm GIN index on University.search_text for the folded ``contains`` search (listing.py).

``contains`` compiles to ``search_text::text LIKE '%term%'`` on PostgreSQL, which only a trigram
index can serve. PostgreSQL only (built CONCURRENTLY, so not atomic); a no-op on SQLite.
"""
from django.db import migrations

from core.migration_ops import _trigram_available

INDEX = 'admissions_university_search_text_trgm'


def create_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        if _trigram_available(cursor):
            cursor.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} ON admissions_university USING gin (search_text gin_trgm_ops)'
            )


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {INDEX}')


class Migration(migrations.Migration):
    atomic = False
    dependencies = [('admissions', '0071_fill_intl_cost')]

    operations = [migrations.RunPython(create_index, drop_index, elidable=False)]
