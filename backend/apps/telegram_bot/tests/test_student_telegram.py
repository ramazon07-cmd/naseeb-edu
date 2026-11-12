from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from apps.admissions.models import Booking, MeetingAvailability
from apps.admissions.tests.base import RoleIsolationBase
from apps.telegram_bot import student_link
from apps.telegram_bot.models import StudentLinkCode, StudentTelegram, TelegramOutbox

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

    def code(self, chat=CHAT, language='ru'):
        response = self.bot('student-code', {'chat_id': chat, 'language': language})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['code']

    def enter(self, user, code):
        self.client.force_authenticate(user)
        return self.client.post('/api/telegram/student/', {'code': code}, format='json')

    def link(self, user=None, chat=CHAT):
        response = self.enter(user or self.student_a_user, self.code(chat))
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

    def test_code_from_the_bot_links_the_chat_end_to_end(self):
        self.client.force_authenticate(self.student_a_user)
        status = self.client.get('/api/telegram/student/').json()
        self.assertEqual(status, {'enabled': True, 'linked': False, 'bot_url': 'https://t.me/naseeb_test_bot?start=student'})
        me = self.client.get('/api/users/accounts/me/').json()
        self.assertEqual(me['telegram']['linked'], False)

        code = self.code()
        self.assertRegex(code, r'^\d{6}$')
        response = self.enter(self.student_a_user, f' {code[:3]} {code[3:]} ')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['linked'])
        link = StudentTelegram.objects.get(user=self.student_a_user)
        self.assertEqual((link.chat_id, link.language), (CHAT, 'ru'))
        # The chat is told, and the code cannot be used twice.
        messages = self.outbox()
        self.assertEqual([m['chat_id'] for m in messages], [CHAT])
        self.assertIn('Telegram', messages[0]['text'])
        self.assertFalse(StudentLinkCode.objects.exists())
        self.assertEqual(self.enter(self.student_b_user, code).json()['code'], 'invalid_code')

    def test_wrong_or_expired_code_is_refused(self):
        code = self.code()
        wrong = '000000' if code != '000000' else '111111'
        self.assertEqual(self.enter(self.student_a_user, wrong).json()['code'], 'invalid_code')
        self.assertEqual(self.enter(self.student_a_user, '12').json()['code'], 'invalid_code')
        StudentLinkCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.enter(self.student_a_user, code).json()['code'], 'invalid_code')
        self.assertFalse(StudentTelegram.objects.exists())

    def test_only_students_link_and_guessing_is_throttled(self):
        code = self.code()
        self.assertEqual(self.enter(self.counselor, code).status_code, 403)
        statuses = [self.enter(self.student_b_user, '999999').status_code for _ in range(12)]
        self.assertIn(429, statuses)

    def test_a_chat_moves_to_the_student_who_typed_its_newest_code(self):
        self.link(self.student_a_user)
        self.link(self.student_b_user)
        self.assertEqual(list(StudentTelegram.objects.values_list('user_id', flat=True)), [self.student_b_user.pk])

    def test_unlink(self):
        self.link()
        self.client.force_authenticate(self.student_a_user)
        self.assertFalse(self.client.delete('/api/telegram/student/').json()['linked'])
        self.assertFalse(StudentTelegram.objects.exists())

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

    def test_bot_endpoints_need_the_service_key_and_valid_lists(self):
        self.assertEqual(self.client.post('/api/bot/student-outbox/', {}, format='json').status_code, 401)
        self.assertEqual(self.bot('student-outbox/ack', {'sent': ['x']}).status_code, 400)
        self.assertEqual(self.bot('student-code', {'chat_id': 'x'}).status_code, 400)
