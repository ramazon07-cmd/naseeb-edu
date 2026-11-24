from datetime import timedelta

from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from apps.users.models import RefreshRotation, RevokedRefreshSession
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
        sessions = delete_in_batches(RevokedRefreshSession.objects.filter(expires_at__lte=timezone.now()), batch_size)
        self.stdout.write(self.style.SUCCESS(f'Deleted {sessions} expired signed-out sessions.'))
        # Only needed for the few seconds of the reuse grace; a day is generous.
        rotations = delete_in_batches(
            RefreshRotation.objects.filter(rotated_at__lte=timezone.now() - timedelta(days=1)), batch_size,
        )
        self.stdout.write(self.style.SUCCESS(f'Deleted {rotations} old refresh rotation records.'))
        return deleted + sessions + rotations
