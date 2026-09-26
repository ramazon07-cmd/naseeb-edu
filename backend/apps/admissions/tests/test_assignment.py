"""Role isolation: counselor scope and student assignment."""
from datetime import date
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from apps.users.models import User
from ..models import (
    Application,
    Document,
    StudentProfile,
    Task,
    University,
)
from .base import RoleIsolationBase


class AssignmentRoleIsolationTests(RoleIsolationBase):
    def test_counselor_sees_only_assigned_students_and_their_workspace(self):
        other_counselor = User.objects.create_user(
            username='other-counselor',
            email='other-counselor@example.com',
            password='StrongPass123!',
            role=User.Role.COUNSELOR,
            school=self.school_a,
        )
        other_user = User.objects.create_user(
            username='other-counselor-student',
            email='other-counselor-student@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        other_student = StudentProfile.objects.create(
            user=other_user,
            school=self.school_a,
            school_name=self.school_a.name,
            assigned_counselor=other_counselor,
        )
        own_task = Task.objects.create(student=self.student_a, assigned_by=self.counselor, title='Assigned task', due_date=date(2027, 12, 1))
        Task.objects.create(student=other_student, assigned_by=other_counselor, title='Private task', due_date=date(2027, 12, 1))
        own_document = Document.objects.create(student=self.student_a, title='Assigned student file')
        Document.objects.create(student=other_student, title='Other counselor file')
        university = University.objects.create(name='Workspace University', country='Testland')
        own_application = Application.objects.create(student=self.student_a, university=university, program='Computer Science')
        other_university = University.objects.create(name='Private University', country='Testland')
        Application.objects.create(student=other_student, university=other_university, program='Economics')
        self.client.force_authenticate(self.counselor)
        response = self.client.get('/api/students/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({item['id'] for item in self.results(response)}, {self.student_a.id})
        self.assertEqual({item['id'] for item in self.results(self.client.get('/api/tasks/'))}, {own_task.id})
        self.assertEqual({item['id'] for item in self.results(self.client.get('/api/documents/'))}, {own_document.id})
        self.assertEqual({item['id'] for item in self.results(self.client.get('/api/applications/'))}, {own_application.id})
        blocked_assignment = self.client.post(
            '/api/tasks/',
            {'student': other_student.id, 'title': 'Cross-counselor task', 'due_date': '2027-12-02'},
            format='json',
        )
        self.assertEqual(blocked_assignment.status_code, status.HTTP_400_BAD_REQUEST)

    def test_counselor_can_connect_only_unassigned_students_from_own_school(self):
        unassigned_user = User.objects.create_user(
            username='unassigned-school-a',
            email='unassigned-school-a@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        unassigned = StudentProfile.objects.create(
            user=unassigned_user,
            school=self.school_a,
            school_name=self.school_a.name,
        )
        other_counselor = User.objects.create_user(
            username='other-counselor-school-a',
            email='other-counselor-school-a@example.com',
            password='StrongPass123!',
            role=User.Role.COUNSELOR,
            school=self.school_a,
        )
        assigned_user = User.objects.create_user(
            username='assigned-school-a',
            email='assigned-school-a@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        assigned_elsewhere = StudentProfile.objects.create(
            user=assigned_user,
            school=self.school_a,
            school_name=self.school_a.name,
            assigned_counselor=other_counselor,
        )

        self.client.force_authenticate(self.counselor)
        candidates = self.client.get('/api/students/assignment-candidates/')
        self.assertEqual(candidates.status_code, status.HTTP_200_OK)
        self.assertEqual({item['id'] for item in candidates.data}, {unassigned.id})
        self.assertNotIn('notes', candidates.data[0])

        with CaptureQueriesContext(connection) as captured_queries:
            connected = self.client.post(
                '/api/students/assign-counselor/',
                {'students': [unassigned.id]},
                format='json',
            )
        self.assertEqual(connected.status_code, status.HTTP_200_OK)
        self.assertEqual(connected.data['assigned_count'], 1)
        assignment_reads = [
            query['sql'] for query in captured_queries.captured_queries
            if 'FROM "admissions_studentprofile"' in query['sql']
            and 'assigned_counselor_id' in query['sql']
        ]
        self.assertTrue(assignment_reads)
        self.assertNotIn('LEFT OUTER JOIN', assignment_reads[0])
        unassigned.refresh_from_db()
        self.assertEqual(unassigned.assigned_counselor, self.counselor)

        blocked = self.client.post(
            '/api/students/assign-counselor/',
            {'students': [assigned_elsewhere.id]},
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        assigned_elsewhere.refresh_from_db()
        self.assertEqual(assigned_elsewhere.assigned_counselor, other_counselor)

    def test_counselor_cannot_connect_cross_school_or_patch_assignment(self):
        same_school_counselor = User.objects.create_user(
            username='same-school-counselor',
            email='same-school-counselor@example.com',
            password='StrongPass123!',
            role=User.Role.COUNSELOR,
            school=self.school_a,
        )
        self.client.force_authenticate(self.counselor)
        cross_school = self.client.post(
            '/api/students/assign-counselor/',
            {'students': [self.student_b.id]},
            format='json',
        )
        self.assertEqual(cross_school.status_code, status.HTTP_400_BAD_REQUEST)

        # A nonexistent id and a real cross-school id must be indistinguishable to
        # the counselor — otherwise the error message leaks which StudentProfile ids
        # belong to other schools.
        missing_id = StudentProfile.objects.order_by('-id').first().id + 1000
        nonexistent = self.client.post(
            '/api/students/assign-counselor/',
            {'students': [missing_id]},
            format='json',
        )
        self.assertEqual(nonexistent.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(nonexistent.data, cross_school.data)

        direct_patch = self.client.patch(
            f'/api/students/{self.student_a.id}/',
            {'assigned_counselor': same_school_counselor.id},
            format='json',
        )
        self.assertEqual(direct_patch.status_code, status.HTTP_400_BAD_REQUEST)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.assigned_counselor, self.counselor)

    def test_admin_can_reassign_same_school_students_and_cross_school_is_blocked(self):
        admin = User.objects.create_user(
            username='product-admin-assignment',
            email='product-admin-assignment@example.com',
            password='StrongPass123!',
            role=User.Role.ADMIN,
        )
        replacement = User.objects.create_user(
            username='replacement-counselor',
            email='replacement-counselor@example.com',
            password='StrongPass123!',
            role=User.Role.COUNSELOR,
            school=self.school_a,
        )
        self.client.force_authenticate(admin)
        reassigned = self.client.post(
            '/api/students/assign-counselor/',
            {'counselor': replacement.id, 'students': [self.student_a.id]},
            format='json',
        )
        self.assertEqual(reassigned.status_code, status.HTTP_200_OK)
        self.assertEqual(reassigned.data['reassigned_count'], 1)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.assigned_counselor, replacement)

        blocked = self.client.post(
            '/api/students/assign-counselor/',
            {'counselor': replacement.id, 'students': [self.student_b.id]},
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.student_b.refresh_from_db()
        self.assertEqual(self.student_b.assigned_counselor, self.counselor_b)
