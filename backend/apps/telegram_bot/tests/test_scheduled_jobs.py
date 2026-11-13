from datetime import timedelta

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from apps.admissions.models import Booking
from apps.users.models import JobRun

from .base import BotTestCase


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', FRONTEND_URL='https://app.example.com')
class MeetingRemindersEndpointTests(BotTestCase):
    def test_the_bot_runs_the_reminder_job_and_sends_the_queue(self):
        booking = Booking.objects.create(
            student=self.s1, participant=self.c1, topic='Essay', duration_minutes=45,
            starts_at=timezone.now() + timedelta(hours=3), status=Booking.Status.APPROVED,
        )
        response = self.post('scheduled-jobs', {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['ran']['send_meeting_reminders'], 'ok')
        booking.refresh_from_db()
        self.assertEqual(booking.reminded_for, booking.starts_at)
        # The hourly job only queues: nothing waits on the mail server inside it.
        self.assertEqual(mail.outbox, [])
        # Recorded like a cron run, so the health page sees the job is alive.
        self.assertEqual(JobRun.objects.filter(name='send_meeting_reminders', result='ok').count(), 1)
        sent = self.post('meeting-emails', {})
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(sent.json(), {'sent': 2, 'failed': 0, 'dropped': 0, 'waiting': 0})
        self.assertEqual(sorted(message.to[0] for message in mail.outbox), ['counselor1@example.com', 'stu1@example.com'])
        # A second call (the other bot instance during a deploy) sends nothing new.
        self.post('scheduled-jobs', {})
        self.post('meeting-emails', {})
        self.assertEqual(len(mail.outbox), 2)

    def test_needs_the_service_key(self):
        self.assertEqual(self.post('scheduled-jobs', {}, key=None).status_code, 401)
        self.assertEqual(self.post('scheduled-jobs', {}, key='wrong').status_code, 401)
        self.assertEqual(self.post('meeting-emails', {}, key=None).status_code, 401)
        self.assertFalse(JobRun.objects.exists())


class DueJobsTests(BotTestCase):
    def at(self, hour):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        return datetime(2026, 11, 11, hour, 10, tzinfo=ZoneInfo('Asia/Tashkent'))

    def test_daily_jobs_run_once_a_day_from_their_hour(self):
        from apps.telegram_bot.jobs import due_jobs, run_due_jobs

        self.assertEqual(due_jobs(self.at(2)), ['send_meeting_reminders'])
        self.assertEqual(due_jobs(self.at(4)), ['send_meeting_reminders', 'flush_expired_tokens', 'purge_screen_time'])
        self.assertEqual(set(due_jobs(self.at(8))), {
            'send_meeting_reminders', 'flush_expired_tokens', 'purge_screen_time', 'generate_notifications',
        })
        ran = run_due_jobs()
        self.assertTrue(all(result == 'ok' for result in ran.values()), ran)
        # Done today: the next hour only sends reminders.
        later = timezone.localtime() + timedelta(hours=1)
        if later.date() == timezone.localdate():
            self.assertEqual(due_jobs(later), ['send_meeting_reminders'])

    def test_a_failed_daily_job_is_tried_again_next_hour(self):
        from unittest import mock

        from apps.telegram_bot.jobs import due_jobs, run_due_jobs

        now = timezone.localtime().replace(hour=9)
        with mock.patch('apps.telegram_bot.jobs.call_command', side_effect=RuntimeError('boom')):
            ran = run_due_jobs(now)
        self.assertEqual(set(ran.values()), {'failed'})
        self.assertIn('generate_notifications', due_jobs(now))
