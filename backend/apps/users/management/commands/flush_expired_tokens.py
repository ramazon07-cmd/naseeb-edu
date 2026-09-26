from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from core.jobs import ScheduledJobCommand, delete_in_batches


class Command(ScheduledJobCommand):
    help = (
        'Delete expired refresh tokens and their blacklist entries in small batches (daily cron). '
        'A batched, locked replacement for simplejwt\'s flushexpiredtokens.'
    )

    def run(self, *, batch_size, **options):
        # Blacklist rows go with their token (on_delete=CASCADE).
        deleted = delete_in_batches(OutstandingToken.objects.filter(expires_at__lte=timezone.now()), batch_size)
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} expired refresh tokens.'))
