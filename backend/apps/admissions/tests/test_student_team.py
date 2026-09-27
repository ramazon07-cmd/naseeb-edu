"""My Naseeb team lists only people the student can reach."""
from rest_framework.test import APITestCase

from apps.admissions.test_audit_base import AuditBaseMixin


class StudentTeamTests(AuditBaseMixin, APITestCase):
    def team(self):
        self.client.force_authenticate(self.student_user)
        return [(member['kind'], member['id']) for member in self.client.get('/api/student-team/').data]

    def test_inactive_staff_leave_the_team(self):
        self.assertEqual(self.team(), [('counselor', self.counselor.id), ('school', self.organization.id)])
        self.organization.is_active = False
        self.organization.save(update_fields=['is_active'])
        self.counselor.is_active = False
        self.counselor.save(update_fields=['is_active'])
        self.assertEqual(self.team(), [])
