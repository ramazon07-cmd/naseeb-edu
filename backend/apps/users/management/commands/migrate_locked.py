"""Run ``migrate`` under a PostgreSQL advisory lock.

Meant for the deploy's pre-deploy step (Render ``preDeployCommand``), which runs
once per deploy before new instances start. The lock still serialises the
rare overlap (two deploys, or ``MIGRATE_ON_START=1`` on several instances):
later runs wait, then find nothing left to apply.

Behind PgBouncer the lock and the migrations use DIRECT_DATABASE_URL (the
``direct`` alias): DDL and a session-level lock need a real server session.
Other databases (SQLite in development) fall back to plain ``migrate``.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.db import advisory_lock, session_alias

# Arbitrary constant shared by every instance of this app ("naseeb" in ASCII).
MIGRATION_LOCK_ID = 0x6E6173656562


class Command(BaseCommand):
    help = 'Apply migrations while holding a PostgreSQL advisory lock (safe for concurrent runs).'

    def add_arguments(self, parser):
        parser.add_argument('--database', default=None,
                            help='Defaults to the direct (non-pooled) connection when DIRECT_DATABASE_URL is set.')
        parser.add_argument('--noinput', '--no-input', action='store_false', dest='interactive')

    def handle(self, *args, database, interactive, **options):
        database = database or session_alias()
        migrate_options = {
            'database': database,
            'interactive': interactive,
            'verbosity': options.get('verbosity', 1),
            'stdout': self.stdout,
            'stderr': self.stderr,
        }
        self.stdout.write('Waiting for the migration lock...')
        with advisory_lock(MIGRATION_LOCK_ID, alias=database):
            call_command('migrate', **migrate_options)
