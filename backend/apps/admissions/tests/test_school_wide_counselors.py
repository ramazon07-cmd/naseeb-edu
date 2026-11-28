"""School.counselors_see_all_students: every counselor of that school sees and runs all its students."""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.models import Booking
from apps.admissions.test_audit_base import AuditBaseMixin
from apps.users.models import User


class SchoolWideCounselorTests(AuditBaseMixin, APITestCase):
    """School A: ``self.student`` belongs to ``self.counselor``; ``self.counselor_peer`` is the other counselor."""

    def setUp(self):
        super().setUp()
        self.unassigned_user = self.make_user('wide-unassigned', User.Role.STUDENT, self.school_a)
        self.unassigned = self.make_profile(self.unassigned_user, self.school_a, None)

    def student_ids(self, user):
        self.client.force_authenticate(user)
        response = self.client.get('/api/students/')
        self.assertEqual(response.status_code, 200)
        return {row['id'] for row in self.results(response)}

    def book(self, user, student):
        self.client.force_authenticate(user)
        return self.client.post('/api/bookings/', {
            'student': student.pk, 'topic': 'Plan',
            'starts_at': (timezone.now() + timedelta(days=5)).isoformat(), 'duration_minutes': 30,
            'ask_student': False,
        }, format='json')

    def test_off_by_default_peer_sees_only_own_students(self):
        self.assertNotIn(self.student.pk, self.student_ids(self.counselor_peer))
        self.assertNotIn(self.unassigned.pk, self.student_ids(self.counselor_peer))
        self.assertEqual(self.book(self.counselor_peer, self.student).status_code, 400)

    def test_on_peer_sees_and_books_every_student_of_the_school(self):
        self.school_a.counselors_see_all_students = True
        self.school_a.save(update_fields=['counselors_see_all_students'])
        ids = self.student_ids(self.counselor_peer)
        self.assertTrue({self.student.pk, self.unassigned.pk} <= ids)
        response = self.book(self.counselor_peer, self.student)
        self.assertEqual(response.status_code, 201, response.data)
        booking = Booking.objects.get(pk=response.data['id'])
        self.assertEqual((booking.student_id, booking.participant_id), (self.student.pk, self.counselor_peer.pk))

    def test_on_never_reaches_another_school(self):
        self.school_a.counselors_see_all_students = True
        self.school_a.save(update_fields=['counselors_see_all_students'])
        self.assertNotIn(self.student_b.pk, self.student_ids(self.counselor_peer))
        self.client.force_authenticate(self.counselor_peer)
        self.assertEqual(self.client.get(f'/api/students/{self.student_b.pk}/').status_code, 404)
        self.assertEqual(self.book(self.counselor_peer, self.student_b).status_code, 400)
        # School B is untouched: its counselor still sees only school B.
        self.assertNotIn(self.student.pk, self.student_ids(self.counselor_b))
