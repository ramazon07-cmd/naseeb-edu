"""School cards in the admin portal (/api/schools/): the student count."""
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.models import StudentProfile
from apps.admissions.test_audit_base import AuditBaseMixin
from apps.users.models import User


class SchoolCardCountTests(AuditBaseMixin, APITestCase):
    def school_card(self, school):
        self.client.force_authenticate(self.admin)
        rows = self.results(self.client.get('/api/schools/?search=Base School A'))
        return next(row for row in rows if row['id'] == school.id)

    def test_only_active_students_are_counted(self):
        self.assertEqual(self.school_card(self.school_a)['students_count'], 1)
        # A deactivated student keeps their profile (and data) in the school.
        gone = self.make_user('base-student-gone', User.Role.STUDENT, self.school_a, is_active=False)
        StudentProfile.objects.filter(pk=self.make_profile(gone, self.school_a, self.counselor).pk).update(deactivated_at=timezone.now())
        card = self.school_card(self.school_a)
        self.assertEqual(card['students_count'], 1)
        self.assertEqual(card['seat_usage']['max_students'], 1)
