"""Building blocks for scheduled (cron) management commands.

Each job runs under its own PostgreSQL advisory lock, so an overlapping run
(a slow night, a manual run during the cron) exits at once instead of doing
the work twice. Deletes go in small batches, each in its own short
transaction, so a large purge never holds long locks or bloats one
transaction.
"""
import logging
import time
import zlib

from django.core.management.base import BaseCommand
from django.db import DatabaseError, transaction
from django.utils import timezone

from core.db import advisory_lock

logger = logging.getLogger('naseeb.jobs')
DEFAULT_BATCH_SIZE = 5000
# The cron jobs the operator health page expects to run daily (ScheduledJobCommand modules).
SCHEDULED_JOBS = ('generate_notifications', 'purge_screen_time', 'flush_expired_tokens')
JOB_LOCK_BASE = 0x6E61 << 32  # "na" in the high bits; the job's CRC32 below


def job_lock_id(name):
    return JOB_LOCK_BASE + zlib.crc32(name.encode('utf-8'))


def delete_in_batches(queryset, batch_size=DEFAULT_BATCH_SIZE):
    """Delete every row of ``queryset`` ``batch_size`` rows per transaction; return the count."""
    model = queryset.model
    deleted = 0
    while True:
        ids = list(queryset.order_by().values_list('pk', flat=True)[:batch_size])
        if not ids:
            return deleted
        with transaction.atomic():
            deleted += model.objects.filter(pk__in=ids).delete()[1].get(model._meta.label, 0)


class ScheduledJobCommand(BaseCommand):
    """A management command that is safe to run from cron: locked, batched, timed."""

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE)

    def handle(self, *args, **options):
        options['batch_size'] = max(1, options['batch_size'])
        name = self.__module__.rsplit('.', 1)[-1]
        started_at = timezone.now()
        started = time.monotonic()
        with advisory_lock(job_lock_id(name), wait=False) as acquired:
            if not acquired:
                self.stdout.write(f'{name} is already running elsewhere; skipped.')
                record_run(name, started_at, 0, 'skipped')
                return
            try:
                processed = self.run(**options)
            except Exception as exc:
                record_run(name, started_at, time.monotonic() - started, 'failed', error=exc.__class__.__name__)
                raise
        duration = time.monotonic() - started
        record_run(name, started_at, duration, 'ok', processed=processed if isinstance(processed, int) else None)
        self.stdout.write(f'{name} finished in {duration:.1f}s.')

    def run(self, **options):
        """Do the work; return how many rows were processed, when that is known."""
        raise NotImplementedError


def record_run(name, started_at, duration, result, *, processed=None, error=''):
    """Keep the run for the health page; losing that record must not fail the job."""
    from apps.users.models import JobRun

    try:
        JobRun.objects.create(
            name=name, started_at=started_at, duration_seconds=round(duration, 3), result=result,
            processed=processed, error=error[:255],
        )
    except DatabaseError as exc:
        logger.warning('job_run_not_recorded job=%s error=%s', name, exc.__class__.__name__)
