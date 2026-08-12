from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.admissions.models import ScreenTimeDaily


class Command(BaseCommand):
    help = 'Delete aggregate screen-time rows older than the configured retention period.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=settings.SCREEN_TIME_RETENTION_DAYS)

    def handle(self, *args, **options):
        days = max(1, options['days'])
        cutoff = timezone.localdate() - timedelta(days=days)
        deleted, _ = ScreenTimeDaily.objects.filter(date__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} screen-time rows older than {cutoff}.'))
