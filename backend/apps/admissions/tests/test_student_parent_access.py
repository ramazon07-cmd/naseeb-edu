"""Students see which parents can view their information (read-only)."""
from django.utils import timezone
from rest_framework import status
from apps.users.models import User
from ..models import ParentStudentLink
from .base import RoleIsolationBase

URL = '/api/my-parents/'


class StudentParentAccessTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.mother = self.make_parent('access-mother', 'Dilnoza', 'Karimova')
        self.father = self.make_parent('access-father', 'Akmal', 'Karimov')
        self.revoked_parent = self.make_parent('access-revoked', 'Old', 'Guardian')
        self.other_parent = self.make_parent('access-other', 'Other', 'Parent')
        self.active = ParentStudentLink.objects.create(
            parent=self.mother, student=self.student_a, status=ParentStudentLink.Status.ACTIVE,
            relationship=ParentStudentLink.Relationship.MOTHER, can_view_documents=False,
            consented_at=timezone.now(),
        )
        self.pending = ParentStudentLink.objects.create(
            parent=self.father, student=self.student_a, status=ParentStudentLink.Status.PENDING,
            relationship=ParentStudentLink.Relationship.FATHER, can_view_meetings=False,
        )
        ParentStudentLink.objects.create(
            parent=self.revoked_parent, student=self.student_a, status=ParentStudentLink.Status.REVOKED,
        )
        ParentStudentLink.objects.create(
            parent=self.other_parent, student=self.student_b, status=ParentStudentLink.Status.ACTIVE,
        )

    def make_parent(self, username, first, last):
        return User.objects.create_user(
            username=username, email=f'{username}@example.com', password='StrongParent123!',
            first_name=first, last_name=last, role=User.Role.PARENT,
        )

    def test_student_sees_own_active_and_pending_links(self):
        self.client.force_authenticate(self.student_a_user)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        parents = response.data['parents']
        self.assertEqual([item['id'] for item in parents], [self.active.id, self.pending.id])
        mother, father = parents
        self.assertEqual(mother['name'], 'Dilnoza Karimova')
        self.assertEqual(mother['relationship'], 'mother')
        self.assertEqual(mother['status'], 'active')
        self.assertEqual(mother['sections'], {'applications': True, 'documents': False, 'meetings': True})
        self.assertEqual(father['status'], 'pending')
        self.assertEqual(father['sections']['meetings'], False)
        # Only what the student needs: no parent account ids or contact details.
        self.assertNotIn('email', mother)
        self.assertNotIn('parent', mother)
        self.assertIn('tasks', response.data['always_visible'])
        self.assertIn('messages', response.data['never_visible'])

    def test_student_never_sees_another_students_parents(self):
        self.client.force_authenticate(self.student_b_user)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [item['name'] for item in response.data['parents']]
        self.assertEqual(names, ['Other Parent'])
        # Query parameters cannot widen the scope.
        widened = self.client.get(URL, {'student': self.student_a.id})
        self.assertEqual([item['name'] for item in widened.data['parents']], ['Other Parent'])

    def test_other_roles_are_refused(self):
        for user in (self.counselor, self.organization, self.teacher, self.mother):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(URL).status_code, status.HTTP_403_FORBIDDEN, user.role)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_read_only(self):
        self.client.force_authenticate(self.student_a_user)
        for method in ('post', 'put', 'patch', 'delete'):
            response = getattr(self.client, method)(URL, {}, format='json')
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED, method)
