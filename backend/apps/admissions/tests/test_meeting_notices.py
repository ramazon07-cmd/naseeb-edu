from datetime import timedelta

from django.utils import timezone

from apps.users.models import User
from ..models import Booking, MeetingAvailability, Notification
from .base import RoleIsolationBase


class StaffMeetingNoticeTests(RoleIsolationBase):
    """A student's booking, cancel or reschedule reaches the staff participant's own bell."""

    def setUp(self):
        super().setUp()
        start = (timezone.now() + timedelta(days=7)).replace(minute=0, second=0, microsecond=0)
        self.first = MeetingAvailability.objects.create(participant=self.counselor, starts_at=start, duration_minutes=45)
        self.second = MeetingAvailability.objects.create(participant=self.counselor, starts_at=start + timedelta(days=1),
                                                         duration_minutes=30)

    def staff_notices(self, title):
        return Notification.objects.filter(recipient=self.counselor, title=title)

    def student_notices(self):
        return list(Notification.objects.filter(student=self.student_a, recipient__isnull=True)
                    .values_list('id', 'title', 'is_read'))

    def book(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post('/api/bookings/', {
            'participant': self.counselor.id, 'topic': 'Essay review', 'starts_at': self.first.starts_at.isoformat(),
            'duration_minutes': 45, 'availability_slot': self.first.id,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def test_each_student_event_is_one_staff_notice(self):
        booking_id = self.book()
        request = self.staff_notices('New meeting request').get()
        self.assertEqual((request.student_id, request.kind, request.target_id),
                         (self.student_a.id, Notification.Kind.MEETING, booking_id))
        self.assertIn('Essay review', request.message)

        moved = self.client.post(f'/api/bookings/{booking_id}/reschedule/', {
            'starts_at': self.second.starts_at.isoformat(), 'duration_minutes': 30, 'availability_slot': self.second.id,
        }, format='json')
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual(self.staff_notices('Meeting reschedule requested').count(), 1)

        for _ in range(2):  # a repeated cancel changes nothing and tells nobody twice
            self.assertEqual(self.client.post(f'/api/bookings/{booking_id}/cancel/').status_code, 200)
        self.assertEqual(self.staff_notices('Meeting cancelled').count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.counselor).count(), 3)
        # Only the participant is addressed; the student's feed keeps its own rows.
        self.assertFalse(Notification.objects.filter(recipient__isnull=False).exclude(recipient=self.counselor).exists())
        self.assertEqual({title for _, title, _ in self.student_notices()},
                         {'Meeting reschedule requested', 'Meeting cancelled'})

    def test_staff_reading_their_notices_leaves_the_students_unread(self):
        booking_id = self.book()
        self.client.post(f'/api/bookings/{booking_id}/cancel/')
        before = self.student_notices()
        self.assertTrue(before and not any(is_read for _, _, is_read in before))
        # The student never sees the staff copy.
        rows = self.results(self.client.get('/api/notifications/'))
        self.assertNotIn('New meeting request', {row['title'] for row in rows})

        self.client.force_authenticate(self.counselor)
        rows = self.results(self.client.get('/api/notifications/?mine=true'))
        self.assertEqual({row['title'] for row in rows}, {'New meeting request', 'Meeting cancelled'})
        for row in rows:
            self.assertEqual(self.client.post(f"/api/notifications/{row['id']}/read/").status_code, 200)
        self.client.post('/api/notifications/read-all/')
        self.assertFalse(Notification.objects.filter(recipient=self.counselor, is_read=False).exists())
        self.assertEqual(self.student_notices(), before)

    def test_staff_actions_add_no_staff_notice(self):
        booking = Booking.objects.create(student=self.student_a, participant=self.counselor, topic='Plan',
                                         starts_at=self.first.starts_at, duration_minutes=45)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(f'/api/bookings/{booking.pk}/cancel/').status_code, 200)
        self.assertFalse(Notification.objects.filter(recipient__isnull=False).exists())


class AddressedNoticeAccessTests(RoleIsolationBase):
    """A notice addressed to a staff member is theirs, whatever their student scope; nobody else's."""

    def setUp(self):
        super().setUp()
        # Same school, bookable, but not student A's assigned counselor.
        self.other_counselor = User.objects.create_user(
            username='counselor-a2', email='counselor-a2@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school_a,
        )
        self.start = (timezone.now() + timedelta(days=7)).replace(minute=0, second=0, microsecond=0)

    def book_with(self, staff, hours=0):
        slot = MeetingAvailability.objects.create(participant=staff, starts_at=self.start + timedelta(hours=hours))
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post('/api/bookings/', {
            'participant': staff.id, 'topic': 'Planning', 'starts_at': slot.starts_at.isoformat(),
            'duration_minutes': 45, 'availability_slot': slot.id,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return Notification.objects.get(recipient=staff, title='New meeting request')

    def assert_bell_works(self, staff, notice):
        self.client.force_authenticate(staff)
        rows = self.results(self.client.get('/api/notifications/?mine=true'))
        self.assertEqual([row['id'] for row in rows], [notice.id])
        self.assertEqual(self.client.get('/api/notifications/summary/').data['unread'], 1)
        self.assertEqual(self.client.post(f'/api/notifications/{notice.id}/read/').status_code, 200)
        self.assertEqual(self.client.get('/api/notifications/summary/').data['unread'], 0)
        Notification.objects.filter(pk=notice.pk).update(is_read=False)
        self.assertEqual(self.client.post('/api/notifications/read-all/').data['updated'], 1)
        notice.refresh_from_db()
        self.assertTrue(notice.is_read)

    def test_booked_counselor_who_is_not_assigned_sees_counts_and_reads_it(self):
        self.assert_bell_works(self.other_counselor, self.book_with(self.other_counselor))

    def test_teacher_participant_sees_counts_and_reads_it(self):
        notice = self.book_with(self.teacher)
        self.assert_bell_works(self.teacher, notice)
        # Without ?mine a teacher still gets only their own addressed notices, never a student's feed.
        Notification.objects.create(student=self.student_a, title='Student feed', message='Body')
        self.client.force_authenticate(self.teacher)
        self.assertEqual([row['id'] for row in self.results(self.client.get('/api/notifications/'))], [notice.id])
        self.assertEqual(self.client.delete(f'/api/notifications/{notice.id}/').status_code, 403)

    def test_nobody_sees_another_users_addressed_notices(self):
        teachers = self.book_with(self.teacher)
        counselors = self.book_with(self.other_counselor, hours=2)
        assigned = self.book_with(self.counselor, hours=4)
        others = {self.teacher: (counselors, assigned), self.other_counselor: (teachers, assigned),
                  self.counselor: (teachers, counselors), self.organization: (teachers, counselors, assigned),
                  self.counselor_b: (teachers, counselors, assigned), self.student_a_user: (teachers, counselors, assigned)}
        for user, hidden in others.items():
            self.client.force_authenticate(user)
            for url in ('/api/notifications/?mine=true', '/api/notifications/'):
                listed = {row['id'] for row in self.results(self.client.get(url))}
                self.assertFalse(listed & {notice.id for notice in hidden}, (user.username, url))
            for notice in hidden:
                self.assertIn(self.client.post(f'/api/notifications/{notice.id}/read/').status_code, {403, 404})
        self.client.force_authenticate(self.organization)
        self.assertEqual(self.client.get('/api/notifications/summary/').data['unread'], 0)
        self.client.post('/api/notifications/read-all/')
        self.assertFalse(Notification.objects.filter(recipient__isnull=False, is_read=True).exists())
