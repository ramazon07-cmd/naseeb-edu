"""The backend's scheduled jobs, run from the counselor bot's hourly call.

Production has no cron service, so the bot (which already wakes every minute)
asks for this once an hour. Each job is the same management command a cron
would run: under its own advisory lock and recorded in JobRun for the health page.
"""
import logging
from io import StringIO

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


def due_jobs(now=None):
    """The jobs to run now: the hourly ones, and each daily one not yet done today (Tashkent)."""
    local = timezone.localtime(now)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    done_today = set(JobRun.objects.filter(
        name__in=list(DAILY_JOBS), result='ok', started_at__gte=day_start,
    ).values_list('name', flat=True))
    daily = [name for name, hour in DAILY_JOBS.items() if local.hour >= hour and name not in done_today]
    return [*HOURLY_JOBS, *daily]


def run_due_jobs(now=None):
    """Run every due job; one failing never stops the others. Returns {name: 'ok' | 'failed'}."""
    results = {}
    for name in due_jobs(now):
        try:
            call_command(name, stdout=StringIO())
        except Exception:  # noqa: BLE001 - recorded as failed in JobRun; tried again next hour
            logger.exception('scheduled job %s failed', name)
            results[name] = 'failed'
        else:
            results[name] = 'ok'
    return results
