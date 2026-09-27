"""Query-count regression tests.

Each test measures an endpoint with N students' worth of rows, then again with
3N, and asserts that the number of SQL queries does not grow. An absolute
upper bound catches a constant-but-large regression too. Bounds are the
counts measured on 2026-09-24 (identical on SQLite and PostgreSQL) plus 3.
"""
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions.models import (
    Application, ApplicationStatusHistory, ChannelMembership, ChannelMessage, Document, Essay, MessageChannel,
    MessageReport, RoadmapMission, Task, University, XPTransaction,
)
from apps.users.models import User

from .test_audit_base import AuditBaseMixin

N = 4


class QueryCountMixin(AuditBaseMixin):
    def setUp(self):
        super().setUp()
        self.university = University.objects.create(name='Count University', country='USA')
        self.room = MessageChannel.objects.create(
            kind=MessageChannel.Kind.COMMUNITY, name='Everyone', school=self.school_a, is_public=True,
        )
        ChannelMembership.objects.create(channel=self.room, user=self.counselor, role=ChannelMembership.Role.OWNER)
        self._serial = 0

    def add_students(self, count):
        """Create ``count`` fully-populated students assigned to self.counselor in school A."""
        today = timezone.localdate()
        for _ in range(count):
            self._serial += 1
            n = self._serial
            user = self.make_user(f'qc-student-{n}', User.Role.STUDENT, self.school_a, first_name=f'S{n:03d}')
            profile = self.make_profile(user, self.school_a, self.counselor)
            Task.objects.create(student=profile, title='Late', due_date=today - timedelta(days=1), status='todo')
            Task.objects.create(student=profile, title='Done', due_date=today, status='approved')
            RoadmapMission.objects.create(student=profile, title='M', due_date=today, status='completed')
            for status_value in ('submitted', 'applying'):
                application = Application.objects.create(
                    student=profile, university=self.university, program=f'P{status_value}', status=status_value,
                    deadline=today + timedelta(days=30),
                )
                ApplicationStatusHistory.objects.create(
                    application=application, status=status_value, changed_by=self.counselor,
                )
            Document.objects.create(student=profile, title='Doc', status='uploaded')
            Essay.objects.create(student=profile, title='Essay', status='needs_revision', shared_with_counselor=True)
            # Not shared, so it stays out of every staff count.
            Essay.objects.create(student=profile, title='Private', status='needs_revision')
            XPTransaction.objects.create(
                student=profile, source_type='task', source_id=n, amount=10, reason='x', awarded_by=self.counselor,
            )
            # Messaging: each student is in the community, shares a group with
            # the counselor, and has a reported message there.
            ChannelMembership.objects.create(channel=self.room, user=user)
            group = MessageChannel.objects.create(kind=MessageChannel.Kind.GROUP, name=f'G{n}', school=self.school_a)
            ChannelMembership.objects.create(channel=group, user=self.counselor, role=ChannelMembership.Role.OWNER)
            ChannelMembership.objects.create(channel=group, user=user)
            message = ChannelMessage.objects.create(channel=group, sender=user, body='hello')
            ChannelMessage.objects.create(channel=self.room, sender=user, body='hi all')
            MessageReport.objects.create(message=message, reporter=self.teacher, reason='spam')

    def assert_constant(self, user, url, *, bound):
        self.client.force_authenticate(user)
        self.add_students(N)
        few, _ = self.get_counted(url)
        self.add_students(2 * N)  # now 3N
        many, response = self.get_counted(url)
        self.assertEqual(few, many, f'{url} as {user.username}: {few} queries for N, {many} for 3N')
        self.assertLessEqual(many, bound, f'{url} as {user.username}: {many} queries')
        return response


class StudentListQueryCountTests(QueryCountMixin, APITestCase):
    def test_counselor(self):
        response = self.assert_constant(self.counselor, '/api/students/', bound=10)
        self.assertEqual(response.data['count'], 3 * N + 1)

    def test_admin(self):
        response = self.assert_constant(self.admin, '/api/students/', bound=10)
        self.assertEqual(response.data['count'], 3 * N + 2)

    def test_organization(self):
        response = self.assert_constant(self.organization, '/api/students/', bound=10)
        self.assertEqual(response.data['count'], 3 * N + 1)


class DashboardQueryCountTests(QueryCountMixin, APITestCase):
    URL = '/api/dashboard/stats/'

    def get_counted(self, url, expected_status=200):
        cache.clear()  # measure the uncached cost; the progress summary is cached per scope
        return super().get_counted(url, expected_status)

    def test_counselor(self):
        response = self.assert_constant(self.counselor, self.URL, bound=13)
        self.assertEqual(response.data['students_total'], 3 * N + 1)
        self.assertEqual(response.data['tasks_total'], 2 * 3 * N)
        self.assertEqual(response.data['tasks_late'], 3 * N)
        self.assertEqual(response.data['applications_total'], 2 * 3 * N)
        self.assertEqual(response.data['applications_submitted'], 3 * N)
        self.assertEqual(response.data['documents_pending_review'], 3 * N)
        self.assertEqual(response.data['essays_need_revision'], 3 * N)

    def test_admin(self):
        response = self.assert_constant(self.admin, self.URL, bound=13)
        self.assertEqual(response.data['students_total'], 3 * N + 2)

    def test_teacher(self):
        response = self.assert_constant(self.teacher, self.URL, bound=13)
        self.assertEqual(response.data['tasks_total'], 2 * 3 * N)
        self.assertNotIn('applications_total', response.data)

    def test_organization(self):
        response = self.assert_constant(self.organization, self.URL, bound=13)
        self.assertNotIn('tasks_total', response.data)


class ApplicationListQueryCountTests(QueryCountMixin, APITestCase):
    def test_counselor(self):
        response = self.assert_constant(self.counselor, '/api/applications/', bound=8)
        self.assertEqual(response.data['count'], 2 * 3 * N)

    def test_admin(self):
        self.assert_constant(self.admin, '/api/applications/', bound=8)


class MessagingQueryCountTests(QueryCountMixin, APITestCase):
    def test_overview_counselor(self):
        response = self.assert_constant(self.counselor, '/api/message-channels/overview/', bound=9)
        self.assertEqual(response.data['channel_counts']['group'], 3 * N)
        self.assertEqual(response.data['channel_counts']['community'], 1)
        self.assertEqual(response.data['unread_total'], 3 * N * 2)

    def test_overview_teacher_moderator(self):
        ChannelMembership.objects.create(
            channel=self.room, user=self.teacher, role=ChannelMembership.Role.MODERATOR,
        )
        self.assert_constant(self.teacher, '/api/message-channels/overview/', bound=9)

    def test_overview_student(self):
        self.assert_constant(self.student_user, '/api/message-channels/overview/', bound=9)

    def test_channel_list_counselor(self):
        response = self.assert_constant(self.counselor, '/api/message-channels/', bound=10)
        self.assertEqual(response.data['count'], 3 * N + 1)

    def test_contacts_counselor(self):
        self.assert_constant(self.counselor, '/api/message-channels/contacts/', bound=4)

    def test_room_messages(self):
        self.assert_constant(self.counselor, f'/api/channel-messages/?channel={self.room.id}', bound=6)

    def test_message_reports(self):
        self.assert_constant(self.counselor, '/api/message-reports/', bound=6)
