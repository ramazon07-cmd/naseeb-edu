from datetime import timedelta

from django.utils import timezone

from apps.admissions.models import Booking, MeetingAvailability, MeetingSchedule
from apps.telegram_bot.models import StudentTelegram

from .base import BotTestCase


def soon(days, hour=10):
    return (timezone.now() + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)


class MeetingsEndpointTests(BotTestCase):
    def setUp(self):
        super().setUp()
        MeetingSchedule.objects.create(
            participant=self.c1, duration_minutes=30, min_notice_hours=6, window_days=30,
            hours={str(day): [['09:00', '11:00']] for day in range(7)},
        )
        for hours in range(3):
            MeetingAvailability.objects.create(participant=self.c1, starts_at=soon(2, 14 + hours), duration_minutes=30)
        self.asked = Booking.objects.create(
            student=self.s1, participant=self.c1, topic='Essay', starts_at=soon(2, 14), duration_minutes=30, status='pending',
        )
        self.invited = Booking.objects.create(
            student=self.s2, participant=self.c1, topic='Plan', starts_at=soon(3), duration_minutes=45, status='pending',
            staff_requested=True,
        )
        self.confirmed = Booking.objects.create(
            student=self.s2, participant=self.c1, topic='Final', starts_at=soon(4), duration_minutes=60, status='approved',
        )
        Booking.objects.create(student=self.s1, participant=self.c1, topic='Old', starts_at=soon(5), status='cancelled')
        # Other counselors' and schools' meetings.
        Booking.objects.create(student=self.s3, participant=self.c2, topic='Not mine', starts_at=soon(2), status='approved')
        Booking.objects.create(student=self.s4, participant=self.cb, topic='Other school', starts_at=soon(2), status='approved')
        # A past meeting and one beyond the window do not count.
        Booking.objects.create(student=self.s1, participant=self.c1, topic='Past', starts_at=soon(-2), status='approved')
        Booking.objects.create(student=self.s1, participant=self.c1, topic='Far', starts_at=soon(45), status='approved')

    def test_a_counselor_sees_only_their_own_upcoming_meetings_with_counts_and_settings(self):
        chat = self.link(self.c1)
        response = self.post('meetings', {'chat_id': chat})
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['role'], 'staff')
        self.assertEqual(data['timezone'], 'Asia/Tashkent')
        self.assertEqual([m['topic'] for m in data['meetings']], ['Essay', 'Plan', 'Final'])
        first = data['meetings'][0]
        self.assertEqual((first['name'], first['duration_minutes'], first['status'], first['waiting_for']),
                         ('Stu1 Tester', 30, 'pending', 'staff'))
        self.assertEqual(data['meetings'][1]['waiting_for'], 'student')
        self.assertIsNone(data['meetings'][2]['waiting_for'])
        self.assertEqual(data['counts'], {'booked': 3, 'waiting_for_you': 1, 'waiting_for_student': 1, 'cancelled_week': 1})
        # Free: three slots minus the one the 14:00 request overlaps.
        self.assertEqual(data['free_slots'], 2)
        self.assertEqual(data['settings'], {
            'duration_minutes': 30, 'min_notice_hours': 6, 'window_mode': 'rolling', 'window_days': 30,
            'window_start': None, 'window_end': None,
        })

    def test_each_counselor_gets_their_own_meetings_only(self):
        other = self.link(self.c2, chat_id=2002)
        data = self.post('meetings', {'chat_id': other}).json()
        self.assertEqual([m['topic'] for m in data['meetings']], ['Not mine'])
        self.assertIsNone(data['settings'])
        self.assertEqual(data['counts']['booked'], 1)
        other_school = self.link(self.cb, chat_id=2003)
        self.assertEqual([m['topic'] for m in self.post('meetings', {'chat_id': other_school}).json()['meetings']], ['Other school'])

    def test_an_old_cancellation_is_not_counted(self):
        Booking.objects.filter(topic='Old').update(updated_at=timezone.now() - timedelta(days=9))
        chat = self.link(self.c1)
        self.assertEqual(self.post('meetings', {'chat_id': chat}).json()['counts']['cancelled_week'], 0)

    def test_a_staff_member_who_changed_school_sees_nothing(self):
        chat = self.link(self.c1)
        self.c1.school = self.school_b
        self.c1.save(update_fields=['school'])
        data = self.post('meetings', {'chat_id': chat}).json()
        self.assertEqual(data['meetings'], [])

    def test_a_student_chat_gets_only_that_students_meetings(self):
        StudentTelegram.objects.create(user=self.s2.user, chat_id=3001)
        data = self.post('meetings', {'chat_id': 3001}).json()
        self.assertEqual(data['role'], 'student')
        self.assertEqual([(m['topic'], m['name']) for m in data['meetings']], [('Plan', 'Counselor1 Tester'), ('Final', 'Counselor1 Tester')])
        self.assertNotIn('counts', data)
        StudentTelegram.objects.update(is_active=False)
        self.assertEqual(self.post('meetings', {'chat_id': 3001}).status_code, 404)

    def test_unlinked_chats_and_bad_requests_are_refused(self):
        self.assertEqual(self.post('meetings', {'chat_id': 999}).status_code, 404)
        self.assertEqual(self.post('meetings', {'chat_id': 'x'}).status_code, 400)
        self.assertEqual(self.post('meetings', {'chat_id': 999}, key='wrong').status_code, 401)
        self.assertEqual(self.post('meetings', {'chat_id': 999}, key=None).status_code, 401)
