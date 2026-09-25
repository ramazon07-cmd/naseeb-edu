"""Migration operations that stay safe on large PostgreSQL tables.

Index builds on tables with hundreds of thousands of rows must not block
writes, so on PostgreSQL they use CREATE INDEX CONCURRENTLY (the migration
must set ``atomic = False``). SQLite (development and the default test run)
gets the plain equivalent.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


class AddIndexOnline(migrations.AddIndex):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        if schema_editor.connection.vendor == 'postgresql':
            schema_editor.add_index(model, self.index, concurrently=True)
        else:
            schema_editor.add_index(model, self.index)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        if not self.allow_migrate_model(schema_editor.connection.alias, model):
            return
        if schema_editor.connection.vendor == 'postgresql':
            schema_editor.remove_index(model, self.index, concurrently=True)
        else:
            schema_editor.remove_index(model, self.index)


def _trigram_available(cursor):
    try:
        cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    except Exception as exc:  # e.g. the role may not create extensions
        logger.warning('pg_trgm unavailable (%s); search stays correct but unindexed', exc.__class__.__name__)
        return False
    cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
    return cursor.fetchone() is not None


class TrigramSearchIndexes(migrations.RunPython):
    """GIN trigram indexes matching Django's ``icontains`` SQL on PostgreSQL.

    ``icontains`` compiles to ``UPPER(col::text) LIKE UPPER(%s)``, so the index
    is on that exact expression. No model state changes; a no-op elsewhere.
    ``targets`` is ``[(app_label, model_name, field_name), ...]``.
    """

    def __init__(self, targets):
        self.targets = tuple(targets)
        super().__init__(self._forwards, self._backwards, elidable=False)

    def deconstruct(self):
        return self.__class__.__name__, [list(self.targets)], {}

    @staticmethod
    def index_name(table, column):
        return f'{table}_{column}_trgm'[:63]

    def _statements(self, apps, schema_editor, create):
        for app_label, model_name, field_name in self.targets:
            model = apps.get_model(app_label, model_name)
            table = model._meta.db_table
            column = model._meta.get_field(field_name).column
            name = schema_editor.quote_name(self.index_name(table, column))
            if create:
                yield (
                    f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {schema_editor.quote_name(table)} '
                    f'USING gin ((UPPER({schema_editor.quote_name(column)}::text)) gin_trgm_ops)'
                )
            else:
                yield f'DROP INDEX CONCURRENTLY IF EXISTS {name}'

    def _forwards(self, apps, schema_editor):
        if schema_editor.connection.vendor != 'postgresql':
            return
        with schema_editor.connection.cursor() as cursor:
            if not _trigram_available(cursor):
                return
            for statement in self._statements(apps, schema_editor, create=True):
                cursor.execute(statement)

    def _backwards(self, apps, schema_editor):
        if schema_editor.connection.vendor != 'postgresql':
            return
        with schema_editor.connection.cursor() as cursor:
            for statement in self._statements(apps, schema_editor, create=False):
                cursor.execute(statement)
