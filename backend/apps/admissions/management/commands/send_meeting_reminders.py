from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.admissions.meeting_mail import deliverable_address
from apps.admissions.models import Booking, MeetingEmail
from core.jobs import ScheduledJobCommand

# Bookings handled per run, soonest first; the rest wait for the next hourly run.
RUN_LIMIT = 200


class Command(ScheduledJobCommand):
    help = (
        'Queue a reminder email to both sides of each confirmed meeting that starts soon (hourly); '
        'one reminder per start time. Sending is left to send_meeting_emails.'
    )

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--limit', type=int, default=RUN_LIMIT)

    def run(self, **options):
        now = timezone.now()
        limit = max(1, options.get('limit') or RUN_LIMIT)
        due = Booking.objects.filter(
            status=Booking.Status.APPROVED, starts_at__gt=now,
            starts_at__lte=now + timedelta(hours=settings.MEETING_REMINDER_HOURS),
        ).filter(Q(reminded_for__isnull=True) | ~Q(reminded_for=F('starts_at')))
        # Claiming (reminded_for) and queueing commit together: a run killed half way leaves
        # nothing behind, and a run repeated after it finds nothing left to queue. Nothing is
        # sent here, so a slow mail server cannot stretch the run.
        with transaction.atomic():
            ids = list(
                due.select_for_update(skip_locked=True).order_by('starts_at', 'id').values_list('pk', flat=True)[:limit]
            )
            bookings = Booking.objects.filter(pk__in=ids).select_related('student__user', 'participant')
            rows = [
                MeetingEmail(
                    booking=booking, recipient=person, event='reminder', meeting_start=booking.starts_at,
                    key=f'reminder:{booking.pk}:{int(booking.starts_at.timestamp())}:{person.pk}',
                )
                for booking in bookings
                for person in (booking.student.user, booking.participant)
                if deliverable_address(person)
            ]
            MeetingEmail.objects.bulk_create(rows, ignore_conflicts=True)
            Booking.objects.filter(pk__in=ids).update(reminded_for=F('starts_at'))
        self.stdout.write(self.style.SUCCESS(f'Queued {len(rows)} meeting reminder emails for {len(ids)} meetings.'))
        return len(rows)
