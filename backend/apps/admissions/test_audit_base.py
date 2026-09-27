"""Shared fixtures for the test_audit_* modules (no test cases live here).

Everything is created through public model APIs and exercised through URLs,
so these tests do not depend on how views.py / serializers.py are organised.
"""
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.admissions.models import School, StudentProfile
from apps.users.models import User


class AuditBaseMixin:
    """Two schools, one of each staff role in school A, two students (A and B)."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.school_a = School.objects.create(name='Base School A', code='base-school-a')
        self.school_b = School.objects.create(name='Base School B', code='base-school-b')
        self.admin = self.make_user('base-admin', User.Role.ADMIN, None)
        self.counselor = self.make_user('base-counselor', User.Role.COUNSELOR, self.school_a)
        self.counselor_peer = self.make_user('base-counselor-peer', User.Role.COUNSELOR, self.school_a)
        self.counselor_b = self.make_user('base-counselor-b', User.Role.COUNSELOR, self.school_b)
        self.teacher = self.make_user('base-teacher', User.Role.TEACHER, self.school_a)
        self.organization = self.make_user('base-org', User.Role.ORGANIZATION, self.school_a)
        self.parent = self.make_user('base-parent', User.Role.PARENT, None)
        self.student_user = self.make_user('base-student', User.Role.STUDENT, self.school_a)
        self.student = self.make_profile(self.student_user, self.school_a, self.counselor)
        self.student_b_user = self.make_user('base-student-b', User.Role.STUDENT, self.school_b)
        self.student_b = self.make_profile(self.student_b_user, self.school_b, self.counselor_b)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    @staticmethod
    def make_user(username, role, school, **extra):
        # No password: tests use force_authenticate, and hashing is slow.
        return User.objects.create_user(
            username=username, email=f'{username}@example.com', password=None,
            role=role, school=school, **extra,
        )

    @staticmethod
    def make_profile(user, school, counselor):
        return StudentProfile.objects.create(
            user=user, school=school, school_name=school.name if school else '', assigned_counselor=counselor,
        )

    @staticmethod
    def results(response):
        data = response.data
        return data.get('results', data) if isinstance(data, dict) else data

    def get_counted(self, url, expected_status=200):
        """GET ``url`` and return (query_count, response)."""
        with CaptureQueriesContext(connection) as context:
            response = self.client.get(url)
        self.assertEqual(response.status_code, expected_status, getattr(response, 'data', None))
        return len(context.captured_queries), response
