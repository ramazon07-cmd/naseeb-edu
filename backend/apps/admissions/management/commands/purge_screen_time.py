from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.admissions.models import ScreenTimeDaily
from core.jobs import ScheduledJobCommand, delete_in_batches


class Command(ScheduledJobCommand):
    help = 'Delete aggregate screen-time rows older than the configured retention period (daily cron).'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--days', type=int, default=settings.SCREEN_TIME_RETENTION_DAYS)

    def run(self, *, days, batch_size, **options):
        cutoff = timezone.localdate() - timedelta(days=max(1, days))
        deleted = delete_in_batches(ScreenTimeDaily.objects.filter(date__lt=cutoff), batch_size)
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} screen-time rows older than {cutoff}.'))
