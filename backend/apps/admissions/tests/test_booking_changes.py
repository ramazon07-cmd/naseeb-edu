"""Students cancel and reschedule their meeting requests; stale requests read as expired."""
from datetime import timedelta
from unittest import mock

from django.utils import timezone
from rest_framework import status

from apps.users.models import User
from ..models import Booking, Notification, StudentProfile
from .base import RoleIsolationBase


class BookingChangeTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.soon = timezone.now() + timedelta(days=3)
        self.booking = Booking.objects.create(
            student=self.student_a, participant=self.counselor, topic='Essay review', starts_at=self.soon,
        )
        # A classmate in the same school: same role, same staff, different owner.
        classmate = User.objects.create_user(
            username='student-a2', email='a2@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school_a,
        )
        StudentProfile.objects.create(user=classmate, school=self.school_a, assigned_counselor=self.counselor)
        self.classmate = classmate

    def post(self, user, action, payload=None, booking=None):
        self.client.force_authenticate(user)
        return self.client.post(f'/api/bookings/{(booking or self.booking).pk}/{action}/', payload or {}, format='json')

    def test_student_cancels_pending_request_and_counselor_is_told(self):
        response = self.post(self.student_a_user, 'cancel')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Booking.Status.CANCELLED)
        notice = Notification.objects.get(student=self.student_a, title='Meeting cancelled')
        self.assertIn('Essay review', notice.message)
        # The counselor sees the cancelled meeting and the notice.
        self.client.force_authenticate(self.counselor)
        rows = self.results(self.client.get('/api/bookings/'))
        self.assertEqual([(row['id'], row['status']) for row in rows], [(self.booking.pk, 'cancelled')])
        self.assertIn(notice.pk, [row['id'] for row in self.results(self.client.get('/api/notifications/'))])

    def test_cancel_is_idempotent(self):
        self.post(self.student_a_user, 'cancel')
        again = self.post(self.student_a_user, 'cancel')
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(again.data['status'], Booking.Status.CANCELLED)
        self.assertEqual(Notification.objects.filter(title='Meeting cancelled').count(), 1)

    def test_approved_meeting_can_be_cancelled_by_student_or_participant(self):
        self.booking.status = Booking.Status.APPROVED
        self.booking.save()
        self.assertEqual(self.post(self.counselor, 'cancel').data['status'], Booking.Status.CANCELLED)

    def test_started_completed_or_rejected_meetings_cannot_be_cancelled(self):
        for booking_status, starts_at in [
            (Booking.Status.APPROVED, timezone.now() - timedelta(minutes=5)),
            (Booking.Status.COMPLETED, self.soon),
            (Booking.Status.REJECTED, self.soon),
        ]:
            Booking.objects.filter(pk=self.booking.pk).update(status=booking_status, starts_at=starts_at)
            self.assertEqual(self.post(self.student_a_user, 'cancel').status_code, status.HTTP_400_BAD_REQUEST)

    def test_reschedule_goes_back_to_pending_for_the_participant(self):
        self.booking.status = Booking.Status.APPROVED
        self.booking.save()
        later = (self.soon + timedelta(days=2)).replace(microsecond=0)
        response = self.post(self.student_a_user, 'reschedule', {'starts_at': later.isoformat(), 'duration_minutes': 60})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.booking.refresh_from_db()
        self.assertEqual((self.booking.status, self.booking.starts_at, self.booking.duration_minutes),
                         (Booking.Status.PENDING, later, 60))
        self.assertTrue(Notification.objects.filter(student=self.student_a, title='Meeting reschedule requested').exists())
        # Repeating the same proposal changes nothing and sends no second notice.
        self.post(self.student_a_user, 'reschedule', {'starts_at': later.isoformat(), 'duration_minutes': 60})
        self.assertEqual(Notification.objects.filter(title='Meeting reschedule requested').count(), 1)
        self.assertEqual(self.post(self.counselor, 'approve').data['status'], Booking.Status.APPROVED)

    def test_reschedule_uses_the_create_rules(self):
        past = (timezone.now() - timedelta(hours=1)).isoformat()
        self.assertEqual(self.post(self.student_a_user, 'reschedule', {'starts_at': past}).status_code, 400)
        later = (self.soon + timedelta(days=1)).isoformat()
        self.assertEqual(
            self.post(self.student_a_user, 'reschedule', {'starts_at': later, 'duration_minutes': 50}).status_code, 400)
        # A participant who left the school is no longer bookable.
        self.counselor.school = self.school_b
        self.counselor.save()
        response = self.post(self.student_a_user, 'reschedule', {'starts_at': later})
        self.assertEqual(response.status_code, 400)
        self.assertIn('participant', response.data)

    def test_staff_cannot_reschedule(self):
        later = (self.soon + timedelta(days=1)).isoformat()
        self.assertEqual(self.post(self.counselor, 'reschedule', {'starts_at': later}).status_code, 403)

    def test_other_students_and_staff_get_404(self):
        later = (self.soon + timedelta(days=1)).isoformat()
        for user in (self.classmate, self.student_b_user):
            self.assertEqual(self.post(user, 'cancel').status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(self.post(user, 'reschedule', {'starts_at': later}).status_code, status.HTTP_404_NOT_FOUND)
        for user in (self.teacher, self.counselor_b):
            self.assertEqual(self.post(user, 'cancel').status_code, status.HTTP_404_NOT_FOUND)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

    def test_unconfirmed_request_expires_at_its_start_time(self):
        self.client.force_authenticate(self.student_a_user)
        self.assertFalse(self.results(self.client.get('/api/bookings/'))[0]['is_expired'])
        with mock.patch('django.utils.timezone.now', return_value=self.soon + timedelta(minutes=1)):
            row = self.results(self.client.get('/api/bookings/'))[0]
            self.assertEqual((row['status'], row['is_expired']), ('pending', True))
            # Nobody can confirm, cancel or move it any more.
            self.assertEqual(self.post(self.counselor, 'approve').status_code, 400)
            self.assertEqual(self.post(self.student_a_user, 'cancel').status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)
