"""Meeting emails go through a queue: requests and the reminder job only write rows, and
``deliver_queued_emails`` sends them in bounded calls, never the same email twice."""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .. import meeting_mail
from ..management.commands import send_meeting_reminders
from ..meeting_mail import deliver_queued_emails
from ..models import Booking, MeetingEmail, StudentProfile
from .base import RoleIsolationBase

MAIL = dict(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', FRONTEND_URL='https://app.example.com')


class Killed(BaseException):
    """The worker dying mid-send (gunicorn's timeout, a deploy): nothing after it runs."""


class FakeClock:
    def __init__(self, step):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


@override_settings(**MAIL)
class MeetingEmailQueueTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.student_a_user.google_email = 'student@gmail.com'
        self.student_a_user.save(update_fields=['google_email'])
        self.counselor.google_email = 'counselor@gmail.com'
        self.counselor.save(update_fields=['google_email'])
        self.start = (timezone.now() + timedelta(hours=5)).replace(second=0, microsecond=0)

    def booking(self, hours=5, **extra):
        values = dict(student=self.student_a, participant=self.counselor, topic='Essay', duration_minutes=45,
                      starts_at=self.start + timedelta(hours=hours - 5), status=Booking.Status.APPROVED)
        return Booking.objects.create(**{**values, **extra})

    def remind(self, **options):
        return call_command('send_meeting_reminders', stdout=StringIO(), **options)

    # --- no duplicates ----------------------------------------------------------------------

    def test_a_worker_killed_mid_send_never_sends_that_email_again(self):
        self.booking()
        self.remind()
        sent_before_dying = []

        def die_after_handing_over(message, *args, **kwargs):
            sent_before_dying.append(message.to)
            raise Killed

        with mock.patch('django.core.mail.EmailMessage.send', autospec=True, side_effect=die_after_handing_over):
            with self.assertRaises(Killed):
                deliver_queued_emails(budget=60)
        self.assertEqual(len(sent_before_dying), 1)
        interrupted = MeetingEmail.objects.get(sending_at__isnull=False)
        # The retry (next minute, or the other bot instance) sends only the other email.
        self.assertEqual(deliver_queued_emails(budget=60)['sent'], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotEqual(mail.outbox[0].to, sent_before_dying[0])
        # Long after, the interrupted row is dropped, never resent.
        MeetingEmail.objects.filter(pk=interrupted.pk).update(sending_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(deliver_queued_emails(budget=60), {'sent': 0, 'failed': 0, 'dropped': 1, 'waiting': 0})
        interrupted.refresh_from_db()
        self.assertIsNotNone(interrupted.dropped_at)
        self.assertIsNone(interrupted.sent_at)
        self.assertEqual(len(mail.outbox), 1)

    def test_a_reminder_run_killed_half_way_queues_nothing_and_its_retry_queues_once(self):
        booking = self.booking()
        # Dies right after queueing, before the claim is written: the transaction rolls back.
        original = MeetingEmail.objects.bulk_create

        def queue_then_die(*args, **kwargs):
            original(*args, **kwargs)
            raise Killed

        with mock.patch.object(MeetingEmail.objects, 'bulk_create', side_effect=queue_then_die):
            with self.assertRaises(Killed):
                self.remind()
        booking.refresh_from_db()
        self.assertIsNone(booking.reminded_for)
        self.assertFalse(MeetingEmail.objects.exists())
        self.remind()
        self.remind()
        self.assertEqual(MeetingEmail.objects.count(), 2)
        deliver_queued_emails(budget=60)
        deliver_queued_emails(budget=60)
        self.assertEqual(sorted(message.to[0] for message in mail.outbox), ['counselor@gmail.com', 'student@gmail.com'])

    def test_a_reminder_queued_twice_by_key_is_kept_once(self):
        booking = self.booking()
        self.remind()
        # Even if the claim were lost (a manual reset), the key keeps one row per person and start.
        Booking.objects.filter(pk=booking.pk).update(reminded_for=None)
        self.remind()
        self.assertEqual(MeetingEmail.objects.count(), 2)

    def test_a_row_another_caller_claimed_is_skipped(self):
        self.booking()
        self.remind()
        taken = MeetingEmail.objects.order_by('id').first()
        real_update = MeetingEmail.objects.filter

        def claimed_elsewhere(*args, **kwargs):
            # The other caller's claim lands between this caller's read and its own claim.
            if kwargs.get('pk') == taken.pk and 'sending_at__isnull' in kwargs:
                MeetingEmail.objects.all().filter(pk=taken.pk).update(sending_at=timezone.now())
            return real_update(*args, **kwargs)

        with mock.patch.object(MeetingEmail.objects, 'filter', side_effect=claimed_elsewhere):
            counts = deliver_queued_emails(budget=60)
        self.assertEqual(counts['sent'], 1)
        self.assertEqual(len(mail.outbox), 1)

    # --- bounded work -----------------------------------------------------------------------

    def test_each_reminder_run_is_capped_soonest_first(self):
        bookings = [self.booking(hours=hours) for hours in (9, 3, 7, 5, 1)]
        self.remind(limit=2)
        claimed = set(Booking.objects.filter(reminded_for__isnull=False).values_list('pk', flat=True))
        self.assertEqual(claimed, {bookings[4].pk, bookings[1].pk})
        self.assertEqual(MeetingEmail.objects.count(), 4)
        self.remind(limit=2)
        self.remind(limit=2)
        self.assertEqual(Booking.objects.filter(reminded_for__isnull=True).count(), 0)
        self.assertEqual(MeetingEmail.objects.count(), 10)
        self.assertEqual(send_meeting_reminders.RUN_LIMIT, 200)

    def test_sending_stops_at_its_time_budget_and_its_batch(self):
        for hours in (1, 2, 3):
            self.booking(hours=hours)
        self.remind()
        # Each clock read moves 10 s on: the 25 s budget allows two sends.
        counts = deliver_queued_emails(budget=25, clock=FakeClock(10))
        self.assertEqual((counts['sent'], counts['waiting']), (2, 4))
        counts = deliver_queued_emails(budget=60, limit=3)
        self.assertEqual((counts['sent'], counts['waiting']), (3, 1))
        self.assertEqual(deliver_queued_emails(budget=60)['sent'], 1)
        self.assertEqual(len(mail.outbox), 6)

    def test_reminder_run_queries_do_not_grow_with_meetings(self):
        def measure(count):
            Booking.objects.all().delete()
            MeetingEmail.objects.all().delete()
            for index in range(count):
                self.booking(hours=1 + index % 20)
            with CaptureQueriesContext(connection) as context:
                self.remind()
            self.assertEqual(MeetingEmail.objects.count(), 2 * count)
            return len(context.captured_queries)

        self.assertEqual(measure(2), measure(12))

    def test_send_queries_are_a_fixed_few_per_email(self):
        def measure(count):
            Booking.objects.all().delete()
            for index in range(count):
                self.booking(hours=1 + index)
            self.remind()
            with CaptureQueriesContext(connection) as context:
                self.assertEqual(deliver_queued_emails(budget=60)['sent'], 2 * count)
            return len(context.captured_queries)

        few, many = measure(1), measure(4)
        # A claim and an outcome per email (6 more emails); reading the queue is one query whatever its size.
        self.assertEqual(many - few, 6 * 2)

    # --- what is sent -----------------------------------------------------------------------

    def test_a_reminder_for_a_cancelled_or_moved_meeting_is_dropped(self):
        kept, cancelled, moved = (self.booking(hours=hours, topic=topic) for hours, topic in ((1, 'K'), (2, 'C'), (3, 'M')))
        self.remind()
        Booking.objects.filter(pk=cancelled.pk).update(status=Booking.Status.CANCELLED)
        Booking.objects.filter(pk=moved.pk).update(starts_at=moved.starts_at + timedelta(days=2))
        counts = deliver_queued_emails(budget=60)
        self.assertEqual((counts['sent'], counts['dropped']), (2, 4))
        self.assertEqual(set(MeetingEmail.objects.filter(sent_at__isnull=False).values_list('booking_id', flat=True)), {kept.pk})
        self.assertEqual(len(mail.outbox), 2)

    def test_repeated_failures_end_in_a_drop(self):
        self.booking()
        self.remind()
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=OSError('down')):
            for _ in range(meeting_mail.MAX_ATTEMPTS):
                MeetingEmail.objects.filter(dropped_at__isnull=True).update(send_after=timezone.now())
                deliver_queued_emails(budget=60)
        self.assertEqual(MeetingEmail.objects.filter(dropped_at__isnull=False, attempts=meeting_mail.MAX_ATTEMPTS).count(), 2)
        MeetingEmail.objects.update(send_after=timezone.now())
        self.assertEqual(deliver_queued_emails(budget=60)['sent'], 0)

    def test_a_rolled_back_change_queues_no_email(self):
        from django.db import transaction

        from rest_framework.test import APIRequestFactory

        booking = self.booking(status=Booking.Status.PENDING)
        request = APIRequestFactory().post('/')
        request.user = self.student_a_user
        try:
            with transaction.atomic():
                meeting_mail.queue_meeting_email(booking, self.counselor, 'New meeting request', request)
                self.assertEqual(MeetingEmail.objects.count(), 1)
                raise RuntimeError('the change failed')
        except RuntimeError:
            pass
        self.assertFalse(MeetingEmail.objects.exists())

    def test_old_rows_are_cleared(self):
        booking = self.booking()
        long_ago = timezone.now() - timedelta(days=8)
        old = MeetingEmail.objects.create(booking=booking, recipient=self.counselor, event='confirmed',
                                          meeting_start=booking.starts_at, sent_at=long_ago)
        stale = MeetingEmail.objects.create(booking=booking, recipient=self.counselor, event='confirmed',
                                            meeting_start=booking.starts_at)
        MeetingEmail.objects.filter(pk=old.pk).update(created_at=long_ago)
        # Unsent for two days: no longer news, dropped (and kept a while for support questions).
        MeetingEmail.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(days=2))
        deliver_queued_emails(budget=60)
        self.assertFalse(MeetingEmail.objects.filter(pk=old.pk).exists())
        stale.refresh_from_db()
        self.assertIsNotNone(stale.dropped_at)
        self.assertEqual(mail.outbox, [])

    def test_the_command_sends_the_queue(self):
        self.booking()
        self.remind()
        out = StringIO()
        call_command('send_meeting_emails', stdout=out)
        self.assertIn('2 sent', out.getvalue())
        self.assertEqual(len(mail.outbox), 2)


@override_settings(**MAIL)
class MeetingWriteThrottleTests(RoleIsolationBase):
    def rates(self, **overrides):
        from django.conf import settings

        rates = {**settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'], **overrides}
        return override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': rates})

    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()

    def test_booking_writes_are_limited_per_user_but_reads_are_not(self):
        start = timezone.now() + timedelta(days=2)
        bookings = [
            Booking.objects.create(student=self.student_a, participant=self.counselor, topic=f'T{index}',
                                   starts_at=start + timedelta(hours=index), duration_minutes=45)
            for index in range(3)
        ]
        other_school = Booking.objects.create(student=self.student_b, participant=self.counselor_b, topic='B',
                                              starts_at=start, duration_minutes=45)
        self.client.force_authenticate(self.counselor)
        with self.rates(booking_write='2/hour'):
            # Refused writes (another school's meeting) are not counted.
            refused = [self.client.post(f'/api/bookings/{other_school.pk}/approve/').status_code for _ in range(3)]
            self.assertEqual(refused, [404, 404, 404])
            codes = [self.client.post(f'/api/bookings/{booking.pk}/approve/').status_code for booking in bookings]
            self.assertEqual(codes, [200, 200, 429])
            self.assertEqual(self.client.get('/api/bookings/').status_code, 200)

    def test_chat_posts_are_limited_per_user(self):
        self.client.force_authenticate(self.counselor)
        with self.rates(chat_post='2/minute'):
            codes = [
                self.client.post('/api/student-messages/', {'student': self.student_a.pk, 'body': f'hi {index}'},
                                 format='json').status_code
                for index in range(3)
            ]
            self.assertEqual(codes[:2], [201, 201])
            self.assertEqual(codes[2], 429)
            self.assertEqual(self.client.get('/api/student-messages/').status_code, 200)


class CompositeIndexTests(RoleIsolationBase):
    def test_scale_indexes_exist(self):
        def indexed(model):
            return {tuple(index.fields) for index in model._meta.indexes}

        self.assertIn(('assigned_counselor', 'school'), indexed(StudentProfile))
        self.assertIn(('participant', 'status', 'starts_at'), indexed(Booking))
