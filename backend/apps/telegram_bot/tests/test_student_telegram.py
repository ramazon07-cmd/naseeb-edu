from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from apps.admissions.models import Booking, MeetingAvailability
from apps.admissions.tests.base import RoleIsolationBase
from apps.telegram_bot import student_link
from apps.telegram_bot.models import StudentLinkToken, StudentTelegram, TelegramOutbox

from .base import KEY

CHAT = 555001


@override_settings(BOT_SERVICE_KEY=KEY, TELEGRAM_BOT_USERNAME='naseeb_test_bot', FRONTEND_URL='https://app.example.com')
class StudentTelegramTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def bot(self, path, data=None):
        self.client.force_authenticate(None)
        return self.client.post(f'/api/bot/{path}/', data or {}, format='json', HTTP_X_BOT_SERVICE_KEY=KEY)

    def issue(self, user=None):
        self.client.force_authenticate(user or self.student_a_user)
        return self.client.post('/api/telegram/student/link/', {}, format='json')

    def token(self, user=None):
        response = self.issue(user)
        self.assertEqual(response.status_code, 200, response.content)
        url = response.json()['url']
        self.assertTrue(url.startswith('https://t.me/naseeb_test_bot?start=s_'), url)
        return url.split('start=s_', 1)[1]

    def consume(self, token, chat=CHAT, language='ru'):
        return self.bot('student-link', {'chat_id': chat, 'token': token, 'language': language})

    def link(self, user=None, chat=CHAT, language='ru'):
        response = self.consume(self.token(user), chat, language)
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def outbox(self):
        return self.bot('student-outbox').json()['messages']

    def request_meeting(self):
        start = (timezone.now() + timedelta(days=3)).replace(minute=0, second=0, microsecond=0)
        slot, _ = MeetingAvailability.objects.get_or_create(participant=self.counselor, starts_at=start, defaults={'duration_minutes': 45})
        self.client.force_authenticate(self.student_a_user)
        return self.client.post('/api/bookings/', {
            'participant': self.counselor.id, 'topic': 'Essay', 'starts_at': start.isoformat(),
            'duration_minutes': 45, 'availability_slot': slot.id,
        }, format='json')

    # --- linking ---------------------------------------------------------------------------

    def test_one_click_link_end_to_end(self):
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.get('/api/telegram/student/').json(), {'enabled': True, 'linked': False})
        self.assertEqual(self.client.get('/api/users/accounts/me/').json()['telegram']['linked'], False)

        issued = self.issue().json()
        self.assertEqual(issued['expires_in'], 900)
        payload = issued['url'].split('start=', 1)[1]
        self.assertRegex(payload, r'^s_[A-Za-z0-9_-]+$')
        self.assertLessEqual(len(payload), 64)

        response = self.consume(payload[2:])
        self.assertEqual(response.status_code, 200, response.content)
        name = self.student_a_user.get_full_name().strip() or self.student_a_user.username
        self.assertEqual(response.json(), {'full_name': name, 'language': 'ru'})
        link = StudentTelegram.objects.get(user=self.student_a_user)
        self.assertEqual((link.chat_id, link.language, link.is_active), (CHAT, 'ru', True))
        # The bot answers directly: no duplicate message is queued.
        self.assertEqual(self.outbox(), [])
        self.assertFalse(StudentLinkToken.objects.exists())
        self.client.force_authenticate(self.student_a_user)
        self.assertTrue(self.client.get('/api/telegram/student/').json()['linked'])
        self.assertTrue(self.client.get('/api/users/accounts/me/').json()['telegram']['linked'])

    def test_the_token_is_stored_hashed_only(self):
        token = self.token()
        row = StudentLinkToken.objects.get()
        self.assertNotIn(token, row.token_hash)
        self.assertEqual(len(row.token_hash), 64)
        self.assertEqual(row.user, self.student_a_user)

    def test_a_token_works_only_once(self):
        token = self.token()
        self.assertEqual(self.consume(token).status_code, 200)
        again = self.consume(token, chat=CHAT + 1)
        self.assertEqual((again.status_code, again.json()['code']), (400, 'invalid_token'))
        self.assertEqual(again.json()['site_url'], 'https://app.example.com/meetings')
        self.assertEqual(StudentTelegram.objects.get().chat_id, CHAT)

    def test_unknown_malformed_and_expired_tokens_are_refused(self):
        token = self.token()
        for bad in ('x' * 43, 'short', 'a b' * 10, 'é' * 30, token[:-1] + ('A' if token[-1] != 'A' else 'B')):
            response = self.consume(bad)
            self.assertEqual((response.status_code, response.json()['code']), (400, 'invalid_token'), bad)
        StudentLinkToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.consume(token).json()['code'], 'invalid_token')
        self.assertFalse(StudentTelegram.objects.exists())

    def test_the_newest_token_replaces_the_older_one(self):
        first, second = self.token(), self.token()
        self.assertEqual(StudentLinkToken.objects.count(), 1)
        self.assertEqual(self.consume(first).json()['code'], 'invalid_token')
        self.assertEqual(self.consume(second).status_code, 200)

    def test_a_deactivated_student_cannot_link(self):
        token = self.token()
        type(self.student_a_user).objects.filter(pk=self.student_a_user.pk).update(is_active=False)
        self.assertEqual(self.consume(token).json()['code'], 'invalid_token')

    def test_only_signed_in_students_get_a_link_and_it_is_throttled(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post('/api/telegram/student/link/', {}, format='json').status_code, 401)
        self.assertEqual(self.issue(self.counselor).status_code, 403)
        statuses = [self.issue(self.student_b_user).status_code for _ in range(12)]
        self.assertIn(429, statuses)

    def test_polling_the_status_is_not_throttled(self):
        self.client.force_authenticate(self.student_a_user)
        self.assertTrue(all(self.client.get('/api/telegram/student/').status_code == 200 for _ in range(30)))

    @override_settings(TELEGRAM_BOT_USERNAME='')
    def test_no_link_without_a_bot_username(self):
        self.assertEqual(self.issue().status_code, 404)

    def test_a_chat_moves_to_the_student_who_linked_it_last(self):
        self.link(self.student_a_user)
        self.link(self.student_b_user)
        self.assertEqual(list(StudentTelegram.objects.values_list('user_id', flat=True)), [self.student_b_user.pk])

    def test_a_student_moves_to_the_newest_chat(self):
        self.link(self.student_a_user, chat=CHAT)
        self.link(self.student_a_user, chat=CHAT + 5, language='en')
        link = StudentTelegram.objects.get()
        self.assertEqual((link.chat_id, link.language), (CHAT + 5, 'en'))

    def test_unlink(self):
        self.link()
        self.client.force_authenticate(self.student_a_user)
        self.assertFalse(self.client.delete('/api/telegram/student/').json()['linked'])
        self.assertFalse(StudentTelegram.objects.exists())

    def test_the_code_flow_is_gone(self):
        self.assertEqual(self.bot('student-code', {'chat_id': CHAT}).status_code, 404)
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.post('/api/telegram/student/', {'code': '123456'}, format='json').status_code, 405)
        self.assertFalse(hasattr(student_link, 'issue_code') or hasattr(student_link, 'link_code'))

    def test_the_student_link_endpoint_needs_the_service_key(self):
        self.client.force_authenticate(None)
        response = self.client.post('/api/bot/student-link/', {'chat_id': CHAT, 'token': 'x' * 43}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_a_chat_guessing_tokens_is_slowed_down(self):
        statuses = [self.consume('z' * 43).status_code for _ in range(35)]
        self.assertEqual(statuses[-1], 429)

    # --- meetings gate ---------------------------------------------------------------------

    def test_a_student_needs_telegram_to_request_a_meeting(self):
        refused = self.request_meeting()
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()['code'], 'telegram_required')
        self.client.force_authenticate(self.student_a_user)
        self.assertEqual(self.client.get('/api/bookings/').status_code, 200)
        self.link()
        self.assertEqual(self.request_meeting().status_code, 201)

    @override_settings(TELEGRAM_BOT_USERNAME='')
    def test_without_a_bot_username_meetings_work_as_before(self):
        self.assertEqual(self.request_meeting().status_code, 201)
        self.client.force_authenticate(self.student_a_user)
        self.assertFalse(self.client.get('/api/telegram/student/').json()['enabled'])

    def test_counselors_are_not_gated(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.put(
            '/api/bookings/availability/weekly/', {'duration_minutes': 45, 'hours': {}}, format='json',
        )
        self.assertNotEqual(response.status_code, 403)

    # --- meeting messages ------------------------------------------------------------------

    def test_confirmation_reaches_the_students_telegram(self):
        self.link()
        self.outbox()
        booked = self.request_meeting()
        self.client.force_authenticate(self.counselor)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/api/bookings/{booked.json()['id']}/approve/")
        messages = self.outbox()
        self.assertEqual(len(messages), 1)
        self.assertIn('Essay', messages[0]['text'])
        self.assertIn('https://app.example.com/meetings', messages[0]['text'])
        # Handed out once: a second bot instance asking within the lease gets nothing.
        self.assertEqual(self.outbox(), [])
        ack = self.bot('student-outbox/ack', {'sent': [messages[0]['id']], 'blocked': []})
        self.assertEqual(ack.json()['sent'], 1)

    def test_reminder_steps_from_a_day_before_to_the_start(self):
        self.link()
        self.outbox()
        start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=2)
        booking = Booking.objects.create(
            student=self.student_a, participant=self.counselor, topic='Plan', starts_at=start,
            duration_minutes=45, status=Booking.Status.APPROVED,
        )
        sent = []
        for minutes_before in (24 * 60, 24 * 60 - 1, 300, 240, 180, 120, 60, 30, 10, 0, -5, -30):
            moment = start - timedelta(minutes=minutes_before)
            sent += [TelegramOutbox.objects.get(pk=m['id']).key.rsplit(':', 1)[1]
                     for m in student_link.pending_messages(moment)['messages']]
            TelegramOutbox.objects.update(sent_at=moment)
        self.assertEqual(sent, ['1440', '300', '240', '180', '120', '60', '30', '0'])
        texts = list(TelegramOutbox.objects.filter(booking=booking).order_by('id').values_list('text', flat=True))
        self.assertIn('завтра', texts[0])  # the chat linked in Russian
        self.assertIn('5 ч', texts[1])
        self.assertIn('30 мин', texts[6])
        self.assertIn('началась', texts[7])

    def test_late_booking_gets_only_the_latest_step_and_moved_meetings_are_reminded_again(self):
        self.link()
        self.outbox()
        now = timezone.now().replace(second=0, microsecond=0)
        booking = Booking.objects.create(
            student=self.student_a, participant=self.counselor, topic='Plan', starts_at=now + timedelta(minutes=55),
            duration_minutes=45, status=Booking.Status.APPROVED,
        )
        # 55 minutes ahead: the 1-hour step passed 5 minutes ago and is sent; nothing earlier.
        self.assertEqual(len(student_link.pending_messages(now)['messages']), 1)
        TelegramOutbox.objects.update(sent_at=now)
        self.assertEqual(student_link.pending_messages(now + timedelta(minutes=1))['messages'], [])
        booking.starts_at = now + timedelta(minutes=30)
        booking.save(update_fields=['starts_at'])
        self.assertEqual(len(student_link.pending_messages(now + timedelta(minutes=1))['messages']), 1)

    def test_pending_and_cancelled_meetings_and_blocked_chats_get_no_reminders(self):
        self.link()
        self.outbox()
        now = timezone.now()
        for status in (Booking.Status.PENDING, Booking.Status.CANCELLED):
            Booking.objects.create(student=self.student_a, participant=self.counselor, topic='X',
                                   starts_at=now + timedelta(minutes=59), status=status)
        self.assertEqual(student_link.pending_messages(now)['messages'], [])
        Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Y',
                               starts_at=now + timedelta(minutes=59), status=Booking.Status.APPROVED)
        self.bot('student-outbox/ack', {'sent': [], 'blocked': [CHAT]})
        self.assertFalse(StudentTelegram.objects.get().is_active)
        self.assertEqual(student_link.pending_messages(now)['messages'], [])

    def test_a_waiting_reminder_is_dropped_when_its_meeting_is_cancelled_or_moved(self):
        self.link()
        self.outbox()
        now = timezone.now().replace(second=0, microsecond=0)
        kept, cancelled, moved = (
            Booking.objects.create(student=self.student_a, participant=self.counselor, topic=topic,
                                   starts_at=now + timedelta(minutes=55), status=Booking.Status.APPROVED)
            for topic in ('Kept', 'Cancelled', 'Moved')
        )
        student_link.queue_reminders(now)
        self.assertEqual(TelegramOutbox.objects.filter(key__isnull=False).count(), 3)
        Booking.objects.filter(pk=cancelled.pk).update(status=Booking.Status.CANCELLED)
        Booking.objects.filter(pk=moved.pk).update(starts_at=now + timedelta(days=3))
        messages = student_link.pending_messages(now)['messages']
        self.assertEqual([TelegramOutbox.objects.get(pk=m['id']).booking_id for m in messages], [kept.pk])
        self.assertEqual(TelegramOutbox.objects.filter(key__isnull=False).count(), 1)

    def test_queueing_reminders_takes_the_same_queries_for_any_number_of_meetings(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.link()
        now = timezone.now().replace(second=0, microsecond=0)

        def measure(count):
            Booking.objects.all().delete()
            for index in range(count):
                Booking.objects.create(student=self.student_a, participant=self.counselor, topic=f'T{index}',
                                       starts_at=now + timedelta(minutes=55), status=Booking.Status.APPROVED)
            with CaptureQueriesContext(connection) as context:
                queued = student_link.queue_reminders(now)
            self.assertEqual(queued, count)
            return len(context.captured_queries)

        self.assertEqual(measure(2), measure(10))
        # Already queued: nothing new, still no query per meeting.
        with CaptureQueriesContext(connection) as context:
            self.assertEqual(student_link.queue_reminders(now), 0)
        self.assertLessEqual(len(context.captured_queries), 3)

    def test_bot_endpoints_need_the_service_key_and_valid_lists(self):
        self.assertEqual(self.client.post('/api/bot/student-outbox/', {}, format='json').status_code, 401)
        self.assertEqual(self.bot('student-outbox/ack', {'sent': ['x']}).status_code, 400)
        self.assertEqual(self.bot('student-link', {'chat_id': 'x', 'token': 'y'}).status_code, 400)
        self.assertEqual(self.bot('whoami', {'chat_id': 'x'}).status_code, 400)
