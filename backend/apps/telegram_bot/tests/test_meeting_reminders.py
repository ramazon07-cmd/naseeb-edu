from datetime import timedelta

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from apps.admissions.models import Booking
from apps.users.models import JobRun

from .base import BotTestCase


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', FRONTEND_URL='https://app.example.com')
class MeetingRemindersEndpointTests(BotTestCase):
    def test_the_bot_runs_the_reminder_job(self):
        booking = Booking.objects.create(
            student=self.s1, participant=self.c1, topic='Essay', duration_minutes=45,
            starts_at=timezone.now() + timedelta(hours=3), status=Booking.Status.APPROVED,
        )
        response = self.post('meeting-reminders', {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})
        booking.refresh_from_db()
        self.assertEqual(booking.reminded_for, booking.starts_at)
        self.assertEqual(sorted(message.to[0] for message in mail.outbox), ['counselor1@example.com', 'stu1@example.com'])
        # Recorded like a cron run, so the health page sees the job is alive.
        self.assertEqual(JobRun.objects.filter(name='send_meeting_reminders', result='ok').count(), 1)
        # A second call (the other bot instance during a deploy) sends nothing new.
        self.post('meeting-reminders', {})
        self.assertEqual(len(mail.outbox), 2)

    def test_needs_the_service_key(self):
        self.assertEqual(self.post('meeting-reminders', {}, key=None).status_code, 401)
        self.assertEqual(self.post('meeting-reminders', {}, key='wrong').status_code, 401)
        self.assertFalse(JobRun.objects.filter(name='send_meeting_reminders').exists())
