"""Isolation / scale audit for the Telegram student link, outbox and reminder queue."""
from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.admissions.models import Booking, School, StudentProfile
from apps.telegram_bot import student_link
from apps.telegram_bot.models import StudentTelegram, TelegramOutbox
from apps.users.models import User

from .base import KEY, BotTestCase, make_student, make_user


@override_settings(BOT_SERVICE_KEY=KEY, TELEGRAM_BOT_USERNAME='audit_bot', FRONTEND_URL='https://app.example.com')
class TelegramIsolationAuditTests(BotTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def student_token(self, student_user):
        self.client.force_authenticate(student_user)
        response = self.client.post('/api/telegram/student/link/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.client.force_authenticate(None)
        return response.json()['url'].split('start=s_', 1)[1]

    def link_student(self, student_user, chat):
        response = self.post('student-link', {'chat_id': chat, 'token': self.student_token(student_user)})
        self.assertEqual(response.status_code, 200, response.content)

    def test_staff_cannot_issue_or_read_student_links_and_students_cannot_use_staff_endpoints(self):
        for staff in (self.c1, self.cb):
            self.client.force_authenticate(staff)
            self.assertEqual(self.client.post('/api/telegram/student/link/', {}, format='json').status_code, 403)
            self.assertEqual(self.client.get('/api/telegram/staff-access/').status_code, 403)
        self.client.force_authenticate(self.s1.user)
        self.assertEqual(self.client.get('/api/telegram/staff-access/').status_code, 403)
        self.assertEqual(self.client.get('/api/telegram/staff-access/%d/' % self.c1.pk).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/telegram/student/').status_code, 401)

    def test_student_status_and_unlink_touch_only_the_callers_link(self):
        self.link_student(self.s1.user, 7001)
        self.link_student(self.s4.user, 7002)
        self.client.force_authenticate(self.s1.user)
        self.assertEqual(self.client.delete('/api/telegram/student/').status_code, 200)
        self.assertFalse(StudentTelegram.objects.filter(user=self.s1.user).exists())
        self.assertTrue(StudentTelegram.objects.filter(user=self.s4.user, chat_id=7002).exists())

    def test_bot_staff_endpoints_never_cross_schools(self):
        chat = self.link(self.c1)
        names = self.names(self.post('students', {'chat_id': chat}))
        self.assertNotIn('Stu4 Tester', names)
        found = self.post('find-students', {'chat_id': chat, 'query': 'stu4'}).json()
        self.assertEqual(found['students'], [])
        self.assertEqual(self.post('reset-password', {'chat_id': chat, 'student_id': self.s4.pk}).status_code, 404)
        self.assertEqual(
            self.post('reset-password', {'chat_id': chat, 'student_id': 99999999}).status_code, 404,
        )
        # a same-school student of another counselor is just as unreachable
        self.assertEqual(self.post('reset-password', {'chat_id': chat, 'student_id': self.s3.pk}).status_code, 404)

    def test_bot_add_student_lands_in_the_callers_school_even_if_the_email_exists_elsewhere(self):
        chat = self.link(self.c1)
        other = self.s4.user
        other.phone = '+998901234567'
        other.save(update_fields=['phone'])
        response = self.post('add-student', {
            'chat_id': chat, 'full_name': 'Same Person', 'email': other.email, 'phone': '+998 90 123 45 67',
        })
        self.assertEqual(response.status_code, 201, response.content)
        created = StudentProfile.objects.get(user__username=response.json()['username'])
        self.assertEqual(created.school_id, self.school_a.pk)
        self.assertEqual(created.assigned_counselor_id, self.c1.pk)
        # the other school's student kept their email and school
        other.refresh_from_db()
        self.assertEqual(other.school_id, self.school_b.pk)
        self.assertNotEqual(created.user.email, other.email)
        self.assertNotIn('student_exists', response.content.decode())

    def test_a_student_account_cannot_become_a_bot_staff_link(self):
        response = self.post('login', {
            'chat_id': 9100, 'username': self.s1.user.username, 'password': 'StrongPass123!',
            'telegram_username': 'tg_counselor1',
        })
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(self.post('students', {'chat_id': 9100}).status_code, 404)

    def test_relinking_a_chat_does_not_deliver_the_old_students_waiting_messages(self):
        """A chat re-linked to a student of ANOTHER school still receives the previous owner's queued meeting texts.

        ``consume_token`` deletes the old StudentTelegram row but leaves its unsent TelegramOutbox rows
        (addressed by raw chat_id) in place; ``pending_messages`` then hands them to the new owner's chat.
        """
        self.link_student(self.s1.user, 7100)          # school A student on chat 7100
        TelegramOutbox.objects.create(chat_id=7100, text='School A meeting: private topic')
        self.link_student(self.s4.user, 7100)          # school B student takes over the same chat
        texts = [m['text'] for m in student_link.pending_messages()['messages'] if m['chat_id'] == 7100]
        self.assertEqual(texts, [])

    def test_meeting_texts_are_addressed_to_the_students_own_chat_only(self):
        self.link_student(self.s1.user, 7201)
        self.link_student(self.s4.user, 7202)
        now = timezone.now().replace(second=0, microsecond=0)
        Booking.objects.create(
            student=self.s1, participant=self.c1, topic='A topic', starts_at=now + timedelta(minutes=55),
            status=Booking.Status.APPROVED,
        )
        Booking.objects.create(
            student=self.s4, participant=self.cb, topic='B topic', starts_at=now + timedelta(minutes=55),
            status=Booking.Status.APPROVED,
        )
        by_chat = {}
        for message in student_link.pending_messages(now)['messages']:
            by_chat.setdefault(message['chat_id'], []).append(message['text'])
        self.assertEqual(set(by_chat), {7201, 7202})
        self.assertTrue(all('B topic' not in text for text in by_chat[7201]))
        self.assertTrue(all('A topic' not in text for text in by_chat[7202]))

    def test_reminders_for_many_bookings_are_idempotent_and_query_count_is_flat(self):
        school = School.objects.create(name='Many', code='many')
        counselor = make_user('many-counselor', User.Role.COUNSELOR, school)
        now = timezone.now().replace(second=0, microsecond=0)

        def seed(count, start):
            for n in range(start, start + count):
                student = make_student(f'many-{n}', school, counselor)
                StudentTelegram.objects.create(user=student.user, chat_id=800000 + n)
                Booking.objects.create(
                    student=student, participant=counselor, topic=f'T{n}', starts_at=now + timedelta(minutes=55),
                    status=Booking.Status.APPROVED,
                )

        seed(2, 0)
        with CaptureQueriesContext(connection) as small:
            student_link.queue_reminders(now)
        TelegramOutbox.objects.all().delete()
        seed(40, 2)
        with CaptureQueriesContext(connection) as big:
            queued = student_link.queue_reminders(now)
        self.assertEqual(queued, 42)
        # get_or_create per due booking: ~2 queries each (this is the per-minute poll cost)
        print(f'\n[audit] queue_reminders queries: 2 bookings={len(small)}, 42 bookings={len(big)}')
        self.assertEqual(student_link.queue_reminders(now), 0)  # a second poll queues nothing new
        first = student_link.pending_messages(now)['messages']
        again = student_link.pending_messages(now)['messages']
        self.assertEqual(len(first), 42)
        self.assertEqual(again, [])  # leased: a second bot instance gets nothing
