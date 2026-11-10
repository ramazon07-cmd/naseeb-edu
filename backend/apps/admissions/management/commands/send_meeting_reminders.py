from datetime import timedelta

from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from apps.admissions.meeting_mail import deliverable_address, send_meeting_email
from apps.admissions.models import Booking
from core.jobs import ScheduledJobCommand


class Command(ScheduledJobCommand):
    help = 'Email both sides of each confirmed meeting that starts soon (hourly cron); one reminder per start time.'

    def run(self, **options):
        now = timezone.now()
        due = Booking.objects.filter(
            status=Booking.Status.APPROVED, starts_at__gt=now,
            starts_at__lte=now + timedelta(hours=settings.MEETING_REMINDER_HOURS),
        ).filter(Q(reminded_for__isnull=True) | ~Q(reminded_for=F('starts_at'))).select_related('student__user', 'participant')
        sent = 0
        for booking in due:
            people = [person for person in (booking.student.user, booking.participant) if deliverable_address(person)]
            delivered = sum(send_meeting_email(booking, person, 'reminder') for person in people)
            sent += delivered
            # Done once someone got it, or when nobody has an address to send to. When every send
            # failed (mail server down), the next hourly run tries again while the meeting is ahead.
            if delivered or not people:
                Booking.objects.filter(pk=booking.pk).update(reminded_for=booking.starts_at)
        self.stdout.write(self.style.SUCCESS(f'Sent {sent} meeting reminder emails.'))
        return sent
