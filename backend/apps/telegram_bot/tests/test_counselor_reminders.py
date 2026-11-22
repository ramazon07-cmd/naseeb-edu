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

    # --- one reminder per meeting in a chat ---

    def deliver(self, moment, first_message_id):
        """What the bot does each minute: fetch, send (Telegram gives each message an id), acknowledge."""
        messages = student_link.pending_messages(moment)['messages']
        ids = {m['id']: first_message_id + i for i, m in enumerate(messages)}
        student_link.acknowledge(list(ids), [], ids)
        return messages

    def test_each_reminder_replaces_the_previous_one_in_the_same_chat(self):
        self.link_staff()
        self.link_student()
        self.booking()
        first = self.deliver(self.start - timedelta(minutes=24 * 60), 100)
        self.assertEqual([m['replaces'] for m in first], [None, None])
        by_chat = {m['chat_id']: 100 + i for i, m in enumerate(first)}
        second = self.deliver(self.start - timedelta(minutes=60), 200)
        # Each chat deletes its own earlier reminder, never the other person's.
        self.assertEqual({m['chat_id']: m['replaces'] for m in second}, by_chat)
        by_chat = {m['chat_id']: 200 + i for i, m in enumerate(second)}
        third = self.deliver(self.start, 300)
        self.assertEqual({m['chat_id']: m['replaces'] for m in third}, by_chat)

    def test_another_meetings_reminder_is_left_alone(self):
        self.link_staff()
        self.booking()
        self.deliver(self.start - timedelta(minutes=60), 100)
        other_start = self.start + timedelta(hours=3)
        self.booking(start=other_start)
        messages = self.deliver(other_start - timedelta(minutes=60), 200)
        self.assertEqual([m['replaces'] for m in messages], [None])

    def test_a_message_id_is_only_kept_for_meeting_rows(self):
        row = TelegramOutbox.objects.create(chat_id=STAFF_CHAT, text='Card')
        student_link.acknowledge([row.pk], [], {row.pk: 55})
        row.refresh_from_db()
        self.assertIsNone(row.message_id)
        self.assertIsNotNone(row.sent_at)

    def test_the_ack_endpoint_takes_message_ids_and_refuses_bad_ones(self):
        self.link_staff()
        self.booking()
        messages = student_link.pending_messages(self.start - timedelta(minutes=60))['messages']
        outbox_id = messages[0]['id']
        ok = self.post('student-outbox/ack', {'sent': [outbox_id], 'blocked': [], 'message_ids': {str(outbox_id): 4242}})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(TelegramOutbox.objects.get(pk=outbox_id).message_id, 4242)
        for bad in ({'x': 1}, {str(outbox_id): 0}, {str(outbox_id): True}, [1]):
            self.assertEqual(self.post('student-outbox/ack', {'sent': [], 'blocked': [], 'message_ids': bad}).status_code, 400)
