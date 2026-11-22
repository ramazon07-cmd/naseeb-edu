"""Meeting reminders reach the counselor's Telegram as well as the student's, each independently."""
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from apps.admissions.models import Booking
from apps.telegram_bot import student_link
from apps.telegram_bot.services import fingerprint
from apps.telegram_bot.models import StudentTelegram, TelegramLink, TelegramOutbox

from .base import KEY, BotTestCase

STUDENT_CHAT = 910001
STAFF_CHAT = 910002


@override_settings(BOT_SERVICE_KEY=KEY, FRONTEND_URL='https://app.example.com')
class CounselorReminderTests(BotTestCase):
    def setUp(self):
        super().setUp()
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=2)

    def booking(self, status=Booking.Status.APPROVED, start=None):
        return Booking.objects.create(
            student=self.s1, participant=self.c1, topic='Plan', starts_at=start or self.start,
            duration_minutes=45, status=status,
        )

    def link_staff(self, language='en'):
        return TelegramLink.objects.create(
            user=self.c1, chat_id=STAFF_CHAT, language=language, auth_fingerprint=fingerprint(self.c1),
        )

    def link_student(self):
        return StudentTelegram.objects.create(user=self.s1.user, chat_id=STUDENT_CHAT, language='ru')

    def rows(self, chat):
        return TelegramOutbox.objects.filter(chat_id=chat, key__isnull=False).order_by('id')

    def test_counselor_gets_every_step_naming_the_student(self):
        self.link_staff()
        booking = self.booking()
        steps = []
        for minutes_before in (24 * 60, 300, 240, 180, 120, 60, 30, 0):
            moment = self.start - timedelta(minutes=minutes_before)
            student_link.queue_reminders(moment)
        keys = list(self.rows(STAFF_CHAT).values_list('key', flat=True))
        for key in keys:
            self.assertTrue(key.endswith(':staff'), key)
            steps.append(key.split(':')[3])
        self.assertEqual(steps, ['1440', '300', '240', '180', '120', '60', '30', '0'])
        first = self.rows(STAFF_CHAT).first().text
        self.assertIn('Stu1 Tester', first)
        self.assertNotIn('Counselor1', first)
        self.assertEqual(self.rows(STAFF_CHAT).first().booking_id, booking.pk)

    def test_counselor_without_a_link_gets_nothing(self):
        self.booking()
        self.assertEqual(student_link.queue_reminders(self.start - timedelta(minutes=60)), 0)
        self.assertFalse(TelegramOutbox.objects.exists())

    def test_inactive_staff_link_gets_nothing(self):
        TelegramLink.objects.create(user=self.c1, chat_id=STAFF_CHAT, auth_fingerprint=fingerprint(self.c1), is_active=False)
        self.booking()
        self.assertEqual(student_link.queue_reminders(self.start - timedelta(minutes=60)), 0)

    def test_the_two_sides_are_independent(self):
        self.booking()
        moment = self.start - timedelta(minutes=60)
        # Student without Telegram: the counselor still gets theirs.
        self.link_staff()
        self.assertEqual(student_link.queue_reminders(moment), 1)
        self.assertEqual(self.rows(STAFF_CHAT).count(), 1)
        # Counselor without a link: the student still gets theirs.
        TelegramOutbox.objects.all().delete()
        TelegramLink.objects.all().delete()
        self.link_student()
        self.assertEqual(student_link.queue_reminders(moment), 1)
        self.assertEqual(self.rows(STUDENT_CHAT).count(), 1)
        self.assertIn('Counselor1 Tester', self.rows(STUDENT_CHAT).first().text)
        # Both linked: one row each.
        TelegramOutbox.objects.all().delete()
        self.link_staff()
        self.assertEqual(student_link.queue_reminders(moment), 2)

    def test_a_second_run_does_not_duplicate(self):
        self.link_staff()
        self.link_student()
        self.booking()
        moment = self.start - timedelta(minutes=60)
        self.assertEqual(student_link.queue_reminders(moment), 2)
        self.assertEqual(student_link.queue_reminders(moment), 0)
        self.assertEqual(TelegramOutbox.objects.count(), 2)

    def test_pending_and_cancelled_meetings_get_nothing(self):
        self.link_staff()
        for status in (Booking.Status.PENDING, Booking.Status.CANCELLED):
            self.booking(status)
        self.assertEqual(student_link.queue_reminders(self.start - timedelta(minutes=60)), 0)

    def test_pending_messages_hands_the_counselor_row_to_the_bot(self):
        self.link_staff(language='ru')
        self.booking()
        messages = student_link.pending_messages(self.start - timedelta(minutes=60))['messages']
        self.assertEqual([m['chat_id'] for m in messages], [STAFF_CHAT])
        self.assertIn('До встречи осталось 1 ч', messages[0]['text'])

    def test_a_blocked_staff_chat_stops_getting_reminders(self):
        self.link_staff()
        self.booking()
        moment = self.start - timedelta(minutes=60)
        student_link.queue_reminders(moment)
        student_link.acknowledge([], [STAFF_CHAT])
        self.assertFalse(TelegramLink.objects.get().is_active)
        self.assertEqual(TelegramOutbox.objects.count(), 0)
        self.assertEqual(student_link.queue_reminders(moment), 0)

    def test_a_blocked_student_chat_leaves_the_counselor_link_alone(self):
        self.link_staff()
        self.link_student()
        student_link.acknowledge([], [STUDENT_CHAT])
        self.assertFalse(StudentTelegram.objects.get().is_active)
        self.assertTrue(TelegramLink.objects.get().is_active)
