"""/api/activity/ (ActivityLogViewSet) and /api/students/{id}/xp-history/."""
from datetime import timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import ActivityLog, LevelApproval, XPTransaction
from apps.users.models import User

from .test_audit_base import AuditBaseMixin

ACTIVITY = '/api/activity/'


class ActivityLogTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.own = ActivityLog.objects.create(actor=self.counselor, student=self.student, action='Task approved')
        self.other = ActivityLog.objects.create(actor=self.counselor_b, student=self.student_b, action='B event')
        self.global_log = ActivityLog.objects.create(actor=self.admin, student=None, action='System event')

    def ids(self, user, url=ACTIVITY):
        self.client.force_authenticate(user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, user.username)
        return {row['id'] for row in self.results(response)}

    def test_admin_sees_everything_including_logs_without_a_student(self):
        self.assertEqual(self.ids(self.admin), {self.own.id, self.other.id, self.global_log.id})

    def test_counselor_sees_only_assigned_students_in_own_school(self):
        self.assertEqual(self.ids(self.counselor), {self.own.id})
        self.assertEqual(self.ids(self.counselor_peer), set())
        self.assertEqual(self.ids(self.counselor_b), {self.other.id})
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(f'{ACTIVITY}{self.other.id}/').status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(f'{ACTIVITY}{self.global_log.id}/').status_code, status.HTTP_404_NOT_FOUND)

    def test_student_sees_own_timeline_only(self):
        self.assertEqual(self.ids(self.student_user), {self.own.id})
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.get(f'{ACTIVITY}{self.other.id}/').status_code, status.HTTP_404_NOT_FOUND)

    def test_parent_without_links_sees_nothing(self):
        self.assertEqual(self.ids(self.parent), set())

    def test_teacher_and_organization_are_forbidden(self):
        for user in (self.teacher, self.organization):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(ACTIVITY).status_code, status.HTTP_403_FORBIDDEN, user.username)

    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get(ACTIVITY).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_payload_names_and_ordering(self):
        self.counselor.first_name, self.counselor.last_name = 'Cara', 'Counsel'
        self.counselor.save()
        newer = ActivityLog.objects.create(actor=None, student=self.student, action='Newest')
        # created_at is the only ordering key; make the order unambiguous.
        ActivityLog.objects.filter(pk=newer.pk).update(created_at=self.own.created_at + timedelta(seconds=1))
        self.client.force_authenticate(self.counselor)
        rows = self.results(self.client.get(ACTIVITY))
        self.assertEqual([row['id'] for row in rows], [newer.id, self.own.id])
        self.assertIsNone(rows[0]['actor_name'])
        self.assertEqual(rows[1]['actor_name'], 'Cara Counsel')
        self.assertEqual(rows[1]['student_name'], 'base-student')
        self.assertEqual(rows[1]['action'], 'Task approved')

    def test_read_only(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.post(ACTIVITY, {'action': 'forged'}, format='json').status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(f'{ACTIVITY}{self.own.id}/').status_code, status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertTrue(ActivityLog.objects.filter(pk=self.own.id).exists())

    def test_list_query_count_does_not_grow_with_rows(self):
        def add(n):
            for index in range(n):
                user = self.make_user(f'act-{ActivityLog.objects.count()}-{index}', User.Role.STUDENT, self.school_a)
                profile = self.make_profile(user, self.school_a, self.counselor)
                ActivityLog.objects.create(actor=self.teacher, student=profile, action='x')

        self.client.force_authenticate(self.counselor)
        add(3)
        few, _ = self.get_counted(ACTIVITY)
        add(9)
        many, response = self.get_counted(ACTIVITY)
        self.assertEqual(len(self.results(response)), 13)
        self.assertEqual(few, many)


class XpHistoryTests(AuditBaseMixin, APITestCase):
    def url(self, student):
        return f'/api/students/{student.id}/xp-history/'

    def setUp(self):
        super().setUp()
        self.first = XPTransaction.objects.create(
            student=self.student, source_type='task', source_id=1, amount=60, reason='Task one',
            awarded_by=self.teacher,
        )
        self.second = XPTransaction.objects.create(
            student=self.student, source_type='roadmap', source_id=1, amount=75, reason='Mission',
            awarded_by=None,
        )
        XPTransaction.objects.create(
            student=self.student_b, source_type='task', source_id=2, amount=10, reason='B only',
        )
        self.student.xp_total = 135
        self.student.save(update_fields=['xp_total'])

    def test_staff_with_access_read_history_newest_first(self):
        for user in (self.counselor, self.admin, self.teacher, self.organization):
            self.client.force_authenticate(user)
            response = self.client.get(self.url(self.student))
            self.assertEqual(response.status_code, status.HTTP_200_OK, user.username)
            rows = response.data['xp_transactions']
            self.assertEqual([row['id'] for row in rows], [self.second.id, self.first.id], user.username)
            self.assertIsNone(rows[0]['awarded_by_name'])
            self.assertEqual(rows[1]['awarded_by_name'], 'base-teacher')
            self.assertEqual(response.data['level_approvals'], [])

    def test_level_approval_shows_up_in_history(self):
        self.client.force_authenticate(self.teacher)
        approved = self.client.post(f'/api/students/{self.student.id}/approve-level/')
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.data)
        self.assertEqual(approved.data['approved_from_level'], 1)
        response = self.client.get(self.url(self.student))
        approvals = response.data['level_approvals']
        self.assertEqual(len(approvals), 1)
        self.assertEqual((approvals[0]['from_level'], approvals[0]['to_level']), (1, 2))
        self.assertEqual(approvals[0]['approved_by_name'], 'base-teacher')
        self.assertEqual(LevelApproval.objects.filter(student=self.student).count(), 1)

    def test_out_of_scope_users_get_404(self):
        for user in (self.counselor_b, self.counselor_peer, self.student_b_user):
            self.client.force_authenticate(user)
            self.assertEqual(
                self.client.get(self.url(self.student)).status_code, status.HTTP_404_NOT_FOUND, user.username,
            )
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(self.url(self.student)).status_code, status.HTTP_404_NOT_FOUND)

    def test_history_is_capped_at_fifty_rows(self):
        XPTransaction.objects.bulk_create([
            XPTransaction(student=self.student, source_type='task', source_id=1000 + index, amount=1, reason='bulk')
            for index in range(60)
        ])
        self.client.force_authenticate(self.counselor)
        response = self.client.get(self.url(self.student))
        self.assertEqual(len(response.data['xp_transactions']), 50)

    def test_query_count_does_not_grow_with_history(self):
        self.client.force_authenticate(self.counselor)
        few, _ = self.get_counted(self.url(self.student))
        XPTransaction.objects.bulk_create([
            XPTransaction(
                student=self.student, source_type='task', source_id=2000 + index, amount=1, reason='bulk',
                awarded_by=self.teacher if index % 2 else self.counselor,
            )
            for index in range(20)
        ])
        for level in range(2, 8):
            LevelApproval.objects.create(
                student=self.student, from_level=level - 1, to_level=level, approved_by=self.counselor,
            )
        many, _ = self.get_counted(self.url(self.student))
        self.assertEqual(few, many)
