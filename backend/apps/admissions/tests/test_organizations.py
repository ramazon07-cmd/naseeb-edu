"""Role isolation: school organization accounts and quick-create."""
from datetime import date
from rest_framework import status
from apps.users.models import User
from ..models import StudentProfile, Task
from .base import RoleIsolationBase


class OrganizationRoleIsolationTests(RoleIsolationBase):
    def test_organization_only_lists_its_school_students(self):
        self.client.force_authenticate(self.organization)
        response = self.client.get('/api/students/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in self.results(response)], [self.student_a.id])

    def test_organization_can_read_only_its_school_admissions_modules(self):
        own_task = Task.objects.create(
            student=self.student_a,
            assigned_by=self.counselor,
            title='School A task',
            due_date=date(2027, 12, 1),
        )
        Task.objects.create(
            student=self.student_b,
            assigned_by=self.counselor,
            title='School B private task',
            due_date=date(2027, 12, 1),
        )
        self.client.force_authenticate(self.organization)
        for path in (
            'tasks', 'applications', 'documents', 'essays', 'achievements',
            'researches', 'projects', 'internships', 'activities', 'honors', 'recommendations',
        ):
            with self.subTest(path=path):
                response = self.client.get(f'/api/{path}/')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
        tasks = self.results(self.client.get('/api/tasks/'))
        self.assertEqual([item['id'] for item in tasks], [own_task.id])
        self.assertEqual(
            self.client.get('/api/meetings/').status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_organization_cannot_write_student_admissions_records(self):
        self.client.force_authenticate(self.organization)
        response = self.client.post(
            '/api/tasks/',
            {
                'student': self.student_a.id,
                'title': 'Organization must not assign tasks',
                'due_date': date(2027, 12, 1),
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Task.objects.filter(title='Organization must not assign tasks').exists())

    def test_organization_quick_create_stays_in_own_school(self):
        self.client.force_authenticate(self.organization)
        response = self.client.post(
            '/api/students/quick-create/',
            {
                'name': 'New School Student',
                'email': 'new-school-student@example.com',
                'grade': '11',
                'password': 'NewStudentPass123!',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = StudentProfile.objects.get(id=response.data['id'])
        self.assertEqual(created.school, self.school_a)
        self.assertEqual(created.user.school, self.school_a)
        self.assertTrue(created.user.must_change_password)
        self.assertTrue(created.user.check_password('NewStudentPass123!'))
        self.assertEqual(created.user.temporary_credentials.get().status, 'issued')

    def test_quick_create_requires_a_strong_initial_password(self):
        self.client.force_authenticate(self.organization)
        missing = self.client.post(
            '/api/students/quick-create/',
            {'name': 'No Password Student', 'email': 'no-password@example.com'},
            format='json',
        )
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        weak = self.client.post(
            '/api/students/quick-create/',
            {'name': 'Weak Password Student', 'email': 'weak-password@example.com', 'password': '12345'},
            format='json',
        )
        self.assertEqual(weak.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quick_create_rejects_overlong_target_countries_cleanly(self):
        self.client.force_authenticate(self.organization)
        response = self.client.post(
            '/api/students/quick-create/',
            {
                'name': 'Long Country List Student',
                'email': 'long-country-list@example.com',
                'password': 'NewStudentPass123!',
                'countries': 'A' * 256,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('target_countries', response.data)
        self.assertFalse(User.objects.filter(email='long-country-list@example.com').exists())

    def test_organization_can_only_read_its_school(self):
        self.client.force_authenticate(self.organization)
        response = self.client.get('/api/schools/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in self.results(response)], [self.school_a.id])
        denied = self.client.get(f'/api/schools/{self.school_b.id}/')
        self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)

    def test_organization_cannot_assign_students_to_counselors(self):
        self.client.force_authenticate(self.organization)
        response = self.client.post(
            '/api/students/assign-counselor/',
            {'counselor': self.counselor.id, 'students': [self.student_a.id]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
