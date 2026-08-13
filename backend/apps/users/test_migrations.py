from importlib import import_module

from django.test import SimpleTestCase


class PostgreSQLMigrationSafetyTests(SimpleTestCase):
    def test_counselor_school_backfill_commits_before_constraints(self):
        migration = import_module(
            'apps.users.migrations.0004_counselor_requires_school'
        ).Migration

        self.assertFalse(migration.atomic)
