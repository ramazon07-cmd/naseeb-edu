"""The backend's scheduled jobs, run from the counselor bot's hourly call.

Production has no cron service, so the bot (which already wakes every minute)
asks for this once an hour. Each job is the same management command a cron
would run: under its own advisory lock and recorded in JobRun for the health page.
"""
import logging
import time
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from apps.users.models import JobRun

logger = logging.getLogger('naseeb.jobs')

# Every hour.
HOURLY_JOBS = ('send_meeting_reminders',)
# Once a day, from this Tashkent hour on: cleanups at night, notifications before the school day.
DAILY_JOBS = {
    'flush_expired_tokens': 3,
    'purge_screen_time': 3,
    'generate_notifications': 7,
}
# Every hour inside a Tashkent night window (start hour, end hour): the Telegram
# program import starts at 23:00 and keeps going hourly until it has caught up.
# Each run is incremental and time-boxed, so an hour with nothing new is quick.
NIGHTLY_JOBS = {
    'import_telegram_programs': (23, 7),
}


def in_window(hour, window):
    start, end = window
    return start <= hour < end if start < end else hour >= start or hour < end


def due_jobs(now=None):
    """The jobs to run now: the hourly ones, and each daily one not yet done today (Tashkent)."""
    local = timezone.localtime(now)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    done_today = set(JobRun.objects.filter(
        name__in=list(DAILY_JOBS), result='ok', started_at__gte=day_start,
    ).values_list('name', flat=True))
    daily = [name for name, hour in DAILY_JOBS.items() if local.hour >= hour and name not in done_today]
    nightly = [name for name, window in NIGHTLY_JOBS.items() if in_window(local.hour, window)]
    return [*HOURLY_JOBS, *daily, *nightly]


# The import is time-boxed; the time the jobs before it took in the same request is
# taken off its budget, so the whole call still ends well before gunicorn's timeout.
MIN_IMPORT_SECONDS = 5


def job_options(name, started):
    if name != 'import_telegram_programs':
        return {}
    spent = int(time.monotonic() - started)
    return {'time_budget': max(MIN_IMPORT_SECONDS, settings.TELEGRAM_IMPORT_TIME_BUDGET_SECONDS - spent)}


def run_due_jobs(now=None):
    """Run every due job; one failing never stops the others. Returns {name: 'ok' | 'failed'}."""
    results = {}
    started = time.monotonic()
    for name in due_jobs(now):
        try:
            call_command(name, stdout=StringIO(), **job_options(name, started))
        except Exception:  # noqa: BLE001 - recorded as failed in JobRun; tried again next hour
            logger.exception('scheduled job %s failed', name)
            results[name] = 'failed'
        else:
            results[name] = 'ok'
    return results
