"""Shared fixture for the role-isolation tests (split from tests.py)."""
from rest_framework.test import APITestCase
from apps.users.models import User
from ..models import School, StudentProfile


class RoleIsolationBase(APITestCase):
    def setUp(self):
        self.school_a = School.objects.create(name='School A', code='school-a')
        self.school_b = School.objects.create(name='School B', code='school-b')

        self.counselor = User.objects.create_user(
            username='counselor-test',
            email='counselor-test@example.com',
            password='StrongPass123!',
            role=User.Role.COUNSELOR,
            school=self.school_a,
        )
        self.counselor_b = User.objects.create_user(
            username='counselor-b-test',
            email='counselor-b-test@example.com',
            password='StrongPass123!',
            role=User.Role.COUNSELOR,
            school=self.school_b,
        )
        self.organization = User.objects.create_user(
            username='organization-a',
            email='organization-a@example.com',
            password='StrongPass123!',
            role=User.Role.ORGANIZATION,
            school=self.school_a,
        )
        self.teacher = User.objects.create_user(
            username='teacher-a',
            email='teacher-a@example.com',
            password='StrongPass123!',
            role=User.Role.TEACHER,
            school=self.school_a,
        )
        self.student_a_user = User.objects.create_user(
            username='student-a',
            email='student-a@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_a,
        )
        self.student_b_user = User.objects.create_user(
            username='student-b',
            email='student-b@example.com',
            password='StrongPass123!',
            role=User.Role.STUDENT,
            school=self.school_b,
        )
        self.student_a = StudentProfile.objects.create(
            user=self.student_a_user,
            school=self.school_a,
            school_name=self.school_a.name,
            assigned_counselor=self.counselor,
        )
        self.student_b = StudentProfile.objects.create(
            user=self.student_b_user,
            school=self.school_b,
            school_name=self.school_b.name,
            assigned_counselor=self.counselor_b,
        )

    def results(self, response):
        return response.data.get('results', response.data)
