"""Tenant isolation: every path that changes, reads or reaches across schools."""
from datetime import timedelta

from django.test import RequestFactory, TransactionTestCase
from django.utils import timezone
from rest_framework import viewsets

from apps.users.models import ProductAuditEvent, User

from .models import (
    ActivityLog,
    Booking,
    ChannelMembership,
    MessageChannel,
    School,
    StudentProfile,
    University,
)
from .tests.base import RoleIsolationBase
from .views.common import ScopedQuerysetMixin


class _UniversityProbeViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = University.objects.all()


class ScopedQuerysetFailClosedTests(RoleIsolationBase):
    def _filter(self, user, *, opt_in=False):
        view = _UniversityProbeViewSet()
        view.allow_unscoped_records = opt_in
        view.request = RequestFactory().get('/')
        view.request.user = user
        return view.filter_for_user(University.objects.all())

    def test_model_without_student_link_returns_nothing_by_default(self):
        University.objects.create(name='Tenantless University', country='Japan')
        admin = User.objects.create_user(
            username='fail-closed-admin', email='fail-closed-admin@example.com',
            password='StrongPass123!', role=User.Role.ADMIN,
        )
        for user in (self.counselor, self.counselor_b, self.organization, self.teacher, self.student_a_user, admin):
            self.assertEqual(list(self._filter(user)), [], user.role)

    def test_explicit_opt_in_hands_scoping_to_the_viewset(self):
        University.objects.create(name='Tenantless University', country='Japan')
        self.assertEqual(self._filter(self.counselor, opt_in=True).count(), 1)

    def test_student_linked_models_stay_scoped_to_the_tenant(self):
        ActivityLog.objects.create(actor=self.counselor, student=self.student_a, action='School A event')
        self.client.force_authenticate(self.counselor)
        self.assertEqual(len(self.results(self.client.get('/api/activity/'))), 1)
        # Wrong tenant: school B's counselor sees none of school A's records.
        self.client.force_authenticate(self.counselor_b)
        self.assertEqual(self.results(self.client.get('/api/activity/')), [])


class InactiveSchoolLockoutTests(RoleIsolationBase):
    PASSWORD = 'StrongPass123!'

    def login(self, user):
        return self.client.post(
            '/api/auth/token/', {'username': user.username, 'password': self.PASSWORD}, format='json',
        )

    def deactivate_school_a(self):
        School.objects.filter(pk=self.school_a.pk).update(is_active=False)

    def test_users_of_a_deactivated_school_cannot_sign_in(self):
        self.deactivate_school_a()
        for user in (self.counselor, self.organization, self.teacher, self.student_a_user):
            response = self.login(user)
            self.assertEqual(response.status_code, 401, user.role)
            self.assertEqual(response.data['code'], 'school_inactive')
        # Wrong tenant: school B is unaffected.
        self.assertEqual(self.login(self.counselor_b).status_code, 200)

    def test_existing_session_stops_working_when_the_school_is_deactivated(self):
        access = self.login(self.counselor).data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        self.assertEqual(self.client.get('/api/students/').status_code, 200)
        self.deactivate_school_a()
        blocked = self.client.get('/api/students/')
        self.assertEqual(blocked.status_code, 401)
        self.assertEqual(blocked.data['code'], 'school_inactive')

    def test_student_is_locked_out_by_their_profile_school(self):
        # The profile school is the tenant even when the account row lags.
        User.objects.filter(pk=self.student_a_user.pk).update(school=self.school_b)
        self.deactivate_school_a()
        self.assertEqual(self.login(self.student_a_user).data['code'], 'school_inactive')

    def test_product_admin_is_unaffected_and_scoping_hides_inactive_school_data(self):
        admin = User.objects.create_user(
            username='lockout-admin', email='lockout-admin@example.com',
            password=self.PASSWORD, role=User.Role.ADMIN, school=self.school_a,
        )
        self.deactivate_school_a()
        self.assertEqual(self.login(admin).status_code, 200)
        self.client.force_authenticate(admin)
        self.assertIn(self.student_a.id, {item['id'] for item in self.results(self.client.get('/api/students/'))})
        # Even a session that skips authentication gets no rows.
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.results(self.client.get('/api/students/')), [])
        self.client.force_authenticate(self.organization)
        self.assertEqual(self.results(self.client.get('/api/students/')), [])


def make_channel(kind, school, *members, **extra):
    channel = MessageChannel.objects.create(
        kind=kind, school=school, name=extra.pop('name', f'{kind} channel'),
        is_public=kind in {MessageChannel.Kind.COMMUNITY, MessageChannel.Kind.DISCUSSION}, **extra,
    )
    for member in members:
        ChannelMembership.objects.create(channel=channel, user=member)
    return channel


def make_direct(first, second, school):
    low, high = sorted([first.pk, second.pk])
    return make_channel(MessageChannel.Kind.DIRECT, school, first, second, direct_key=f'{low}:{high}', name='')


class UserLeftSchoolTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='left-admin', email='left-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.school_c = School.objects.create(name='School C', code='school-c')
        self.mover = User.objects.create_user(
            username='moving-counselor', email='moving-counselor@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school_a,
        )
        self.group = make_channel(MessageChannel.Kind.GROUP, self.school_a, self.mover, self.teacher)
        self.community = make_channel(MessageChannel.Kind.COMMUNITY, self.school_a, self.mover)
        self.dm_teacher = make_direct(self.mover, self.teacher, self.school_a)
        self.dm_other_school = make_direct(self.mover, self.counselor_b, self.school_b)
        self.saved = make_channel(
            MessageChannel.Kind.DIRECT, None, self.mover, direct_key=f'saved:{self.mover.pk}', name='Saved',
        )

    def transfer(self, school):
        self.client.force_authenticate(self.admin)
        return self.client.post(
            f'/api/users/accounts/{self.mover.id}/transfer-school/', {'school': school.id}, format='json',
        )

    def assert_cut_from_school_a(self):
        self.assertFalse(ChannelMembership.objects.filter(user=self.mover, channel__in=[self.group, self.community]).exists())
        self.assertTrue(ChannelMembership.objects.filter(user=self.teacher, channel=self.group).exists())
        self.dm_teacher.refresh_from_db()
        self.dm_other_school.refresh_from_db()
        self.saved.refresh_from_db()
        self.assertTrue(self.dm_teacher.is_archived)
        self.assertFalse(self.dm_other_school.is_archived)
        self.assertFalse(self.saved.is_archived)

    def test_transfer_removes_old_school_channels_and_archives_old_school_directs(self):
        response = self.transfer(self.school_c)
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_cut_from_school_a()
        event = ProductAuditEvent.objects.get(action='counselor.transferred', target_id=str(self.mover.id))
        self.assertEqual(event.metadata['memberships_removed'], 2)
        self.assertEqual(event.metadata['direct_channels_archived'], 1)

        # The old school's teacher can no longer write in the archived chat.
        self.client.force_authenticate(self.teacher)
        blocked = self.client.post('/api/channel-messages/', {'channel': self.dm_teacher.id, 'body': 'Hi'}, format='json')
        self.assertEqual(blocked.status_code, 400)
        # The moved counselor no longer sees school A's community or group.
        self.mover.refresh_from_db()
        self.client.force_authenticate(self.mover)
        visible = {item['id'] for item in self.results(self.client.get('/api/message-channels/'))}
        self.assertNotIn(self.group.id, visible)
        self.assertNotIn(self.community.id, visible)

    def test_admin_school_change_on_a_staff_account_uses_the_same_rules(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f'/api/users/accounts/{self.mover.id}/', {'school': self.school_c.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_cut_from_school_a()

    def test_wrong_role_cannot_transfer(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post(
            f'/api/users/accounts/{self.mover.id}/transfer-school/', {'school': self.school_c.id}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ChannelMembership.objects.filter(user=self.mover, channel=self.group).exists())

    def test_leaving_is_idempotent(self):
        from .tenancy import user_left_school

        self.transfer(self.school_c)
        self.mover.refresh_from_db()
        self.assertEqual(
            user_left_school(self.mover, self.school_a),
            {'memberships_removed': 0, 'direct_channels_archived': 0, 'assignments_cleared': 0},
        )

    def test_reconnecting_as_valid_contacts_reopens_an_archived_direct_chat(self):
        self.transfer(self.school_c)
        self.mover.refresh_from_db()
        self.teacher.school = self.school_c
        self.teacher.save(update_fields=['school'])
        self.client.force_authenticate(self.teacher)
        reopened = self.client.post('/api/message-channels/direct/', {'user': self.mover.id}, format='json')
        self.assertEqual(reopened.status_code, 200, reopened.data)
        self.assertEqual(reopened.data['id'], self.dm_teacher.id)
        self.dm_teacher.refresh_from_db()
        self.assertFalse(self.dm_teacher.is_archived)
        self.assertEqual(self.dm_teacher.school, self.school_c)


class BookingTenantTests(RoleIsolationBase):
    def test_bookings_follow_the_staff_members_current_school(self):
        booking = Booking.objects.create(
            student=self.student_a, participant=self.counselor, topic='Check-in',
            starts_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_authenticate(self.counselor)
        self.assertEqual([item['id'] for item in self.results(self.client.get('/api/bookings/'))], [booking.id])
        User.objects.filter(pk=self.counselor.pk).update(school=self.school_b)
        self.counselor.refresh_from_db()
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.results(self.client.get('/api/bookings/')), [])
        self.assertEqual(self.client.post(f'/api/bookings/{booking.id}/approve/').status_code, 404)

    def test_student_cannot_book_an_assigned_counselor_from_another_school(self):
        StudentProfile.objects.filter(pk=self.student_a.pk).update(assigned_counselor=self.counselor_b)
        self.client.force_authenticate(self.student_a_user)
        participants = {item['id'] for item in self.client.get('/api/bookings/participants/').data}
        self.assertNotIn(self.counselor_b.id, participants)
        self.assertIn(self.teacher.id, participants)
        response = self.client.post('/api/bookings/', {
            'participant': self.counselor_b.id, 'topic': 'Cross-school',
            'starts_at': (timezone.now() + timedelta(days=2)).isoformat(), 'duration_minutes': 45,
        }, format='json')
        self.assertEqual(response.status_code, 400)


class MoveStudentTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        from apps.users.credentials import issue_temporary_credential

        self.admin = User.objects.create_user(
            username='move-admin', email='move-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.group = make_channel(MessageChannel.Kind.GROUP, self.school_a, self.student_a_user, self.teacher)
        self.dm = make_direct(self.student_a_user, self.counselor, self.school_a)
        issue_temporary_credential(user=self.student_a_user, issued_by=self.organization, raw_password='SchoolAIssued123!')

    def assert_moved_to_b(self):
        self.student_a.refresh_from_db()
        self.student_a_user.refresh_from_db()
        self.assertEqual(self.student_a.school, self.school_b)
        self.assertEqual(self.student_a.school_name, self.school_b.name)
        self.assertEqual(self.student_a_user.school, self.school_b)
        self.assertIsNone(self.student_a.assigned_counselor)
        self.assertFalse(ChannelMembership.objects.filter(user=self.student_a_user, channel=self.group).exists())
        self.dm.refresh_from_db()
        self.assertTrue(self.dm.is_archived)
        event = ProductAuditEvent.objects.get(action='student.moved', target_id=str(self.student_a.id))
        self.assertEqual(event.metadata['from_school'], self.school_a.id)
        self.assertEqual(event.metadata['to_school'], self.school_b.id)
        self.assertTrue(event.metadata['counselor_cleared'])
        self.assertEqual(event.metadata['credentials_revoked'], 1)
        # The password school A handed out no longer signs in.
        login = self.client.post(
            '/api/auth/token/', {'username': self.student_a_user.username, 'password': 'SchoolAIssued123!'}, format='json',
        )
        self.assertEqual(login.status_code, 401)

    def assert_old_school_lost_control(self):
        for staff in (self.organization, self.counselor):
            self.client.force_authenticate(staff)
            self.assertEqual(self.client.get(f'/api/students/{self.student_a.id}/').status_code, 404)
            self.assertEqual(self.client.get(f'/api/users/accounts/{self.student_a_user.id}/').status_code, 404)
            self.assertEqual(
                self.client.post(f'/api/users/accounts/{self.student_a_user.id}/temporary-credential/', {}).status_code, 404,
            )
            listed = {item['id'] for item in self.results(self.client.get('/api/users/accounts/'))}
            self.assertNotIn(self.student_a_user.id, listed)
        # The new school's staff now manage the student.
        school_b_org = User.objects.create_user(
            username='org-b', email='org-b@example.com', password='StrongPass123!',
            role=User.Role.ORGANIZATION, school=self.school_b,
        )
        self.client.force_authenticate(school_b_org)
        self.assertEqual(self.client.get(f'/api/students/{self.student_a.id}/').status_code, 200)

    def test_admin_moves_student_through_the_profile_endpoint(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f'/api/students/{self.student_a.id}/', {'school': self.school_b.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['school'], self.school_b.id)
        self.assert_moved_to_b()
        self.assert_old_school_lost_control()

    def test_admin_moves_student_through_the_account_endpoint(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f'/api/users/accounts/{self.student_a_user.id}/', {'school': self.school_b.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_moved_to_b()
        self.assert_old_school_lost_control()

    def test_django_admin_path_moves_through_the_service(self):
        from .services import ensure_student_profile

        self.student_a_user.school = self.school_b
        self.student_a_user.save(update_fields=['school'])
        ensure_student_profile(self.student_a_user, actor=self.admin)
        self.assert_moved_to_b()

    def test_school_staff_cannot_move_a_student(self):
        for staff in (self.organization, self.counselor):
            self.client.force_authenticate(staff)
            response = self.client.patch(
                f'/api/students/{self.student_a.id}/', {'school': self.school_b.id}, format='json',
            )
            self.assertEqual(response.status_code, 400, staff.role)
            response = self.client.patch(
                f'/api/users/accounts/{self.student_a_user.id}/', {'school': self.school_b.id}, format='json',
            )
            self.assertEqual(response.status_code, 400, staff.role)
        # Wrong tenant: school B cannot reach the student at all.
        self.client.force_authenticate(self.counselor_b)
        response = self.client.patch(f'/api/students/{self.student_a.id}/', {'school': self.school_b.id}, format='json')
        self.assertEqual(response.status_code, 404)
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.school, self.school_a)

    def test_account_row_lagging_behind_the_profile_never_grants_the_old_school(self):
        StudentProfile.objects.filter(pk=self.student_a.pk).update(school=self.school_b, assigned_counselor=None)
        self.client.force_authenticate(self.organization)
        self.assertNotIn(
            self.student_a_user.id, {item['id'] for item in self.results(self.client.get('/api/users/accounts/'))},
        )
        self.assertEqual(
            self.client.post(f'/api/users/accounts/{self.student_a_user.id}/temporary-credential/', {}).status_code, 404,
        )

    def test_move_is_idempotent_clears_other_school_counselor_and_rejects_inactive_targets(self):
        from django.core.exceptions import ValidationError

        from .tenancy import move_student

        move_student(self.student_a, self.school_b, self.admin)
        move_student(self.student_a, self.school_b, self.admin)
        self.assertEqual(ProductAuditEvent.objects.filter(action='student.moved').count(), 1)
        StudentProfile.objects.filter(pk=self.student_a.pk).update(assigned_counselor=self.counselor_b)
        closed = School.objects.create(name='Closed', code='closed', is_active=False)
        with self.assertRaises(ValidationError):
            move_student(self.student_a, closed, self.admin)
        move_student(self.student_a, self.school_a, self.admin)
        self.student_a.refresh_from_db()
        self.assertIsNone(self.student_a.assigned_counselor)

    def test_data_migration_aligns_lagging_account_rows_with_the_profile(self):
        from importlib import import_module

        from django.apps import apps as registry

        User.objects.filter(pk=self.student_a_user.pk).update(school=self.school_b)
        User.objects.filter(pk=self.student_b_user.pk).update(school=None)
        import_module('apps.admissions.migrations.0046_safety_sync_student_school').sync_account_school_from_profile(
            registry, None,
        )
        self.student_a_user.refresh_from_db()
        self.student_b_user.refresh_from_db()
        self.assertEqual(self.student_a_user.school, self.school_a)
        self.assertEqual(self.student_b_user.school, self.school_b)


class CounselorReachTests(RoleIsolationBase):
    """Counselor contacts, channels and legacy messages use the canonical scope."""

    def setUp(self):
        super().setUp()
        # An inconsistent assignment: school A's counselor on a school B student.
        self.cross_user = User.objects.create_user(
            username='cross-student', email='cross-student@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school_b,
        )
        self.cross = StudentProfile.objects.create(
            user=self.cross_user, school=self.school_b, school_name=self.school_b.name, assigned_counselor=self.counselor,
        )
        self.school_b_org = User.objects.create_user(
            username='reach-org-b', email='reach-org-b@example.com', password='StrongPass123!',
            role=User.Role.ORGANIZATION, school=self.school_b,
        )
        self.community_b = make_channel(MessageChannel.Kind.COMMUNITY, self.school_b)

    def test_counselor_contacts_are_assigned_students_and_staff_of_own_school_only(self):
        self.client.force_authenticate(self.counselor)
        contact_ids = {item['id'] for item in self.client.get('/api/message-channels/contacts/').data}
        self.assertTrue({self.student_a_user.id, self.teacher.id, self.organization.id}.issubset(contact_ids))
        for outsider in (self.cross_user, self.school_b_org, self.student_b_user, self.counselor_b):
            self.assertNotIn(outsider.id, contact_ids)
        blocked = self.client.post('/api/message-channels/direct/', {'user': self.school_b_org.id}, format='json')
        self.assertEqual(blocked.status_code, 403)

    def test_cross_school_assignment_opens_no_channels(self):
        self.client.force_authenticate(self.counselor)
        visible = {item['id'] for item in self.results(self.client.get('/api/message-channels/'))}
        self.assertNotIn(self.community_b.id, visible)
        self.assertEqual(self.client.post(f'/api/message-channels/{self.community_b.id}/join/').status_code, 404)

    def test_student_contacts_exclude_an_assigned_counselor_from_another_school(self):
        self.client.force_authenticate(self.cross_user)
        contact_ids = {item['id'] for item in self.client.get('/api/message-channels/contacts/').data}
        self.assertNotIn(self.counselor.id, contact_ids)
        self.assertIn(self.school_b_org.id, contact_ids)

    def test_legacy_messages_follow_the_canonical_scope(self):
        from .models import StudentMessage

        own = StudentMessage.objects.create(
            student=self.student_a, sender=self.counselor, recipient=self.student_a_user, body='Own school',
        )
        cross = StudentMessage.objects.create(
            student=self.cross, sender=self.counselor, recipient=self.cross_user, body='Cross school',
        )
        self.client.force_authenticate(self.counselor)
        listed = {item['id'] for item in self.results(self.client.get('/api/student-messages/'))}
        self.assertEqual(listed, {own.id})
        self.assertEqual(self.client.get(f'/api/student-messages/{cross.id}/').status_code, 404)
        created = self.client.post('/api/student-messages/', {'student': self.cross.id, 'body': 'Hello'}, format='json')
        self.assertEqual(created.status_code, 400)
        created = self.client.post('/api/student-messages/', {'student': self.student_a.id, 'body': 'Hello'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        # Wrong tenant: school B's counselor sees neither thread.
        self.client.force_authenticate(self.counselor_b)
        self.assertEqual(self.results(self.client.get('/api/student-messages/')), [])


class GlobalChannelTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='global-admin', email='global-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )

    def create(self, user, payload):
        self.client.force_authenticate(user)
        return self.client.post('/api/message-channels/', payload, format='json')

    def test_schoolless_public_channel_is_members_only_unless_global(self):
        legacy = make_channel(MessageChannel.Kind.COMMUNITY, None, self.counselor_b, name='Legacy')
        for user in (self.student_a_user, self.counselor, self.organization):
            self.client.force_authenticate(user)
            visible = {item['id'] for item in self.results(self.client.get('/api/message-channels/'))}
            self.assertNotIn(legacy.id, visible)
            self.assertEqual(self.client.post(f'/api/message-channels/{legacy.id}/join/').status_code, 404)

    def test_only_a_product_admin_creates_a_global_community(self):
        created = self.create(self.admin, {'kind': 'community', 'name': 'Everyone', 'is_global': True})
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(created.data['is_global'])
        self.assertIsNone(created.data['school'])
        self.client.force_authenticate(self.student_b_user)
        self.assertEqual(self.client.post(f"/api/message-channels/{created.data['id']}/join/").status_code, 201)

        for user in (self.teacher, self.counselor, self.organization):
            denied = self.create(user, {'kind': 'community', 'name': 'Mine', 'is_global': True})
            self.assertEqual(denied.status_code, 403, user.role)
        self.assertEqual(MessageChannel.objects.filter(is_global=True).count(), 1)
        group = self.create(self.admin, {'kind': 'group', 'name': 'Global group', 'is_global': True})
        self.assertEqual(group.status_code, 400)

    def test_non_admin_channels_always_land_in_the_creators_school(self):
        created = self.create(self.teacher, {'kind': 'community', 'name': 'A community'})
        self.assertEqual(created.data['school'], self.school_a.id)
        wrong = self.create(self.teacher, {'kind': 'community', 'name': 'B community', 'school': self.school_b.id})
        self.assertEqual(wrong.status_code, 400)
        # A student's channel belongs to their profile's school.
        User.objects.filter(pk=self.student_a_user.pk).update(school=None)
        self.student_a_user.refresh_from_db()
        discussion = self.create(self.student_a_user, {'kind': 'discussion', 'name': 'Question'})
        self.assertEqual(discussion.data['school'], self.school_a.id)

    def test_users_without_a_school_cannot_create_channels(self):
        teacher = User.objects.create_user(
            username='schoolless-teacher', email='schoolless-teacher@example.com', password='StrongPass123!',
            role=User.Role.TEACHER,
        )
        parent = User.objects.create_user(
            username='channel-parent', email='channel-parent@example.com', password='StrongPass123!',
            role=User.Role.PARENT,
        )
        for user in (teacher, parent):
            response = self.create(user, {'kind': 'discussion', 'name': 'Nowhere'})
            self.assertEqual(response.status_code, 403, user.role)
        self.assertFalse(MessageChannel.objects.filter(name='Nowhere').exists())

    def test_global_flag_cannot_be_changed_after_creation(self):
        channel = make_channel(MessageChannel.Kind.COMMUNITY, self.school_a, name='Local')
        ChannelMembership.objects.filter(channel=channel).delete()
        ChannelMembership.objects.create(channel=channel, user=self.teacher, role=ChannelMembership.Role.OWNER)
        self.client.force_authenticate(self.teacher)
        response = self.client.patch(f'/api/message-channels/{channel.id}/', {'is_global': True}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_backfill_marks_only_admin_created_schoolless_public_channels(self):
        from importlib import import_module

        from django.apps import apps as registry

        admin_made = make_channel(MessageChannel.Kind.COMMUNITY, None, name='Admin made', created_by=self.admin)
        staff_made = make_channel(MessageChannel.Kind.COMMUNITY, None, name='Staff made', created_by=self.counselor)
        import_module('apps.admissions.migrations.0047_safety_channel_is_global').mark_admin_created_global_channels(
            registry, None,
        )
        admin_made.refresh_from_db()
        staff_made.refresh_from_db()
        self.assertTrue(admin_made.is_global)
        self.assertFalse(staff_made.is_global)


class ChannelModerationTenantTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='mod-admin', email='mod-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.classmate_b = User.objects.create_user(
            username='classmate-b', email='classmate-b@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school_b,
        )
        StudentProfile.objects.create(user=self.classmate_b, school=self.school_b, school_name=self.school_b.name)
        self.global_room = make_channel(
            MessageChannel.Kind.DISCUSSION, None, self.student_a_user, self.student_b_user, self.classmate_b,
            name='Global room', is_global=True, created_by=self.admin,
        )
        ChannelMembership.objects.create(
            channel=self.global_room, user=self.teacher, role=ChannelMembership.Role.MODERATOR,
        )

    def post(self, user, body, **extra):
        from .models import ChannelMessage

        return ChannelMessage.objects.create(channel=self.global_room, sender=user, body=body, **extra)

    def test_member_list_and_management_need_membership_not_staff_rank(self):
        group = make_channel(MessageChannel.Kind.GROUP, self.school_a, self.teacher, self.student_a_user)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.get(f'/api/message-channels/{group.id}/members/').status_code, 404)
        community = make_channel(MessageChannel.Kind.COMMUNITY, self.school_a, self.teacher)
        self.assertEqual(self.client.get(f'/api/message-channels/{community.id}/members/').status_code, 403)
        added = self.client.post(
            f'/api/message-channels/{community.id}/members/', {'user': self.student_a_user.id}, format='json',
        )
        self.assertEqual(added.status_code, 403)
        removed = self.client.delete(
            f'/api/message-channels/{community.id}/members/', {'user': self.teacher.id}, format='json',
        )
        self.assertEqual(removed.status_code, 403)
        self.assertTrue(ChannelMembership.objects.filter(channel=community, user=self.teacher).exists())

    def test_staff_rank_does_not_accept_answers_in_a_global_discussion(self):
        question = self.post(self.student_b_user, 'Question?')
        reply = self.post(self.classmate_b, 'Answer.', parent=question)
        ChannelMembership.objects.create(channel=self.global_room, user=self.counselor)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(f'/api/channel-messages/{reply.id}/accept/').status_code, 403)
        # The channel's moderator and its creator may.
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.post(f'/api/channel-messages/{reply.id}/accept/').status_code, 200)
        # Same-school staff still accept in their own school's discussion.
        local = make_channel(MessageChannel.Kind.DISCUSSION, self.school_a, self.student_a_user, self.counselor)
        from .models import ChannelMessage

        root = ChannelMessage.objects.create(channel=local, sender=self.student_a_user, body='Q')
        answer = ChannelMessage.objects.create(channel=local, sender=self.counselor, body='A', parent=root)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(f'/api/channel-messages/{answer.id}/accept/').status_code, 200)
        self.client.force_authenticate(self.counselor_b)
        self.assertEqual(self.client.post(f'/api/channel-messages/{answer.id}/accept/').status_code, 404)

    def test_global_moderators_never_see_other_schools_reporters_or_anonymous_authors(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from .models import MessageReport

        anonymous_b = self.post(self.student_b_user, 'Anonymous from B', is_anonymous=True)
        anonymous_a = self.post(self.student_a_user, 'Anonymous from A', is_anonymous=True)
        from_b = MessageReport.objects.create(message=anonymous_b, reporter=self.classmate_b, reason='spam')
        from_a = MessageReport.objects.create(message=anonymous_a, reporter=self.student_b_user, reason='spam')
        own = MessageReport.objects.create(message=anonymous_b, reporter=self.student_a_user, reason='spam')

        self.client.force_authenticate(self.teacher)
        reports = {item['id']: item for item in self.results(self.client.get('/api/message-reports/'))}
        self.assertIsNone(reports[from_b.id]['reporter'])
        self.assertEqual(reports[from_b.id]['reporter_name'], 'Hidden reporter')
        self.assertIsNone(reports[from_b.id]['sender_id'])
        self.assertEqual(reports[from_b.id]['sender_name'], 'Anonymous')
        self.assertNotIn('classmate-b', str(reports))
        self.assertNotIn(self.student_b_user.username, str(reports))
        self.assertEqual(reports[from_a.id]['sender_id'], self.student_a_user.id)
        self.assertEqual(reports[own.id]['reporter'], self.student_a_user.id)

        self.client.force_authenticate(self.admin)
        reports = {item['id']: item for item in self.results(self.client.get('/api/message-reports/'))}
        self.assertEqual(reports[from_b.id]['reporter'], self.classmate_b.id)
        self.assertEqual(reports[from_b.id]['sender_id'], self.student_b_user.id)

        # Masking resolves schools without a query per report.
        self.client.force_authenticate(self.teacher)
        with CaptureQueriesContext(connection) as few:
            self.client.get('/api/message-reports/')
        for index in range(3):
            MessageReport.objects.create(message=self.post(self.classmate_b, f'm{index}'), reporter=self.student_b_user, reason='spam')
        with CaptureQueriesContext(connection) as many:
            self.client.get('/api/message-reports/')
        self.assertEqual(len(few), len(many))


class ParentReachTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        from .models import ParentStudentLink

        self.Link = ParentStudentLink
        self.parent = User.objects.create_user(
            username='reach-parent', email='reach-parent@example.com', password='StrongPass123!',
            role=User.Role.PARENT,
        )
        self.link = ParentStudentLink.objects.create(
            parent=self.parent, student=self.student_a, status=ParentStudentLink.Status.ACTIVE,
            consented_at=timezone.now(),
        )
        self.pending = ParentStudentLink.objects.create(parent=self.parent, student=self.student_b)
        self.global_room = make_channel(MessageChannel.Kind.COMMUNITY, None, name='Global', is_global=True)

    def contacts(self, user):
        self.client.force_authenticate(user)
        response = self.client.get('/api/message-channels/contacts/')
        self.assertEqual(response.status_code, 200)
        return {item['id'] for item in response.data}

    def test_parent_contacts_are_only_counselors_of_accepted_children(self):
        self.assertEqual(self.contacts(self.parent), {self.counselor.id})
        # A pending invitation grants nothing.
        self.assertNotIn(self.counselor_b.id, self.contacts(self.parent))
        for target in (self.student_a_user, self.teacher, self.organization, self.counselor_b):
            response = self.client.post('/api/message-channels/direct/', {'user': target.id}, format='json')
            self.assertEqual(response.status_code, 403, target.username)
        self.assertEqual(
            self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json').status_code, 201,
        )

    def test_parent_cannot_join_create_or_list_school_resources(self):
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.results(self.client.get('/api/message-channels/')), [])
        self.assertEqual(self.client.post(f'/api/message-channels/{self.global_room.id}/join/').status_code, 404)
        created = self.client.post('/api/message-channels/', {'kind': 'discussion', 'name': 'Parents'}, format='json')
        self.assertEqual(created.status_code, 403)
        accounts = self.results(self.client.get('/api/users/accounts/'))
        self.assertEqual([item['id'] for item in accounts], [self.parent.id])
        self.assertEqual(self.results(self.client.get('/api/students/')), [])
        self.assertEqual(self.client.get('/api/bookings/').status_code, 403)
        self.assertEqual(self.client.get('/api/parent-portal/').status_code, 200)

    def test_revoking_the_link_ends_the_parents_chat(self):
        self.client.force_authenticate(self.parent)
        channel_id = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json').data['id']
        # The counselor can reach the linked parent too.
        self.assertIn(self.parent.id, self.contacts(self.counselor))
        self.assertNotIn(self.parent.id, self.contacts(self.counselor_b))
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.post(f'/api/parent-links/{self.link.id}/revoke/').status_code, 200)
        self.assertTrue(MessageChannel.objects.get(pk=channel_id).is_archived)
        self.assertEqual(self.contacts(self.parent), set())
        self.client.force_authenticate(self.counselor)
        blocked = self.client.post('/api/channel-messages/', {'channel': channel_id, 'body': 'Hello'}, format='json')
        self.assertEqual(blocked.status_code, 400)

    def test_moving_the_child_ends_the_chat_with_the_old_counselor(self):
        from .tenancy import move_student

        self.client.force_authenticate(self.parent)
        channel_id = self.client.post('/api/message-channels/direct/', {'user': self.counselor.id}, format='json').data['id']
        move_student(self.student_a, self.school_b, None)
        self.assertTrue(MessageChannel.objects.get(pk=channel_id).is_archived)
        self.assertEqual(self.contacts(self.parent), set())

    def test_parents_never_hold_a_school(self):
        from django.db import IntegrityError, transaction

        with transaction.atomic(), self.assertRaises(IntegrityError):
            User.objects.filter(pk=self.parent.pk).update(school=self.school_a)
        admin = User.objects.create_user(
            username='parent-admin', email='parent-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.client.force_authenticate(admin)
        response = self.client.patch(f'/api/users/accounts/{self.parent.id}/', {'school': self.school_a.id}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_invited_parent_gets_no_school_from_the_child(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/parent-links/invite/', {
            'student': self.student_a.id, 'email': 'fresh-parent@example.com',
            'password': 'StrongParent123!', 'relationship': 'mother',
        }, format='json')
        self.assertIn(response.status_code, {200, 201}, response.data)
        self.assertIsNone(User.objects.get(email='fresh-parent@example.com').school_id)


class ParentSchoolMigrationTests(TransactionTestCase):
    migrate_from = [('users', '0012_merge_lists_admin'), ('admissions', '0047_safety_channel_is_global')]
    migrate_to = [('users', '0013_safety_parent_has_no_school'), ('admissions', '0047_safety_channel_is_global')]

    def test_existing_parents_are_detached_before_the_constraint_lands(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldSchool = old_apps.get_model('admissions', 'School')
        OldUser = old_apps.get_model('users', 'User')
        school = OldSchool.objects.create(name='Legacy parent school', code='legacy-parent-school')
        parent = OldUser.objects.create(username='legacy-parent', email='legacy-parent@example.com', role='parent', school=school)
        staff = OldUser.objects.create(username='legacy-teacher', email='legacy-teacher@example.com', role='teacher', school=school)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        self.assertIsNone(User.objects.get(pk=parent.pk).school_id)
        self.assertEqual(User.objects.get(pk=staff.pk).school_id, school.pk)


class StudentDeactivationTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='deact-admin', email='deact-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        ActivityLog.objects.create(actor=self.counselor, student=self.student_a, action='Kept record')

    def test_only_product_admins_deactivate_and_nothing_is_deleted(self):
        for user in (self.organization, self.counselor, self.teacher, self.student_a_user):
            self.client.force_authenticate(user)
            self.assertIn(self.client.delete(f'/api/students/{self.student_a.id}/').status_code, {403}, user.role)
        # Wrong tenant: another school's staff cannot even find the student.
        self.client.force_authenticate(self.counselor_b)
        self.assertEqual(self.client.delete(f'/api/students/{self.student_a.id}/').status_code, 403)
        self.student_a_user.refresh_from_db()
        self.assertTrue(self.student_a_user.is_active)

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f'/api/students/{self.student_a.id}/').status_code, 204)
        self.assertEqual(self.client.delete(f'/api/students/{self.student_a.id}/').status_code, 204)
        self.student_a.refresh_from_db()
        self.student_a_user.refresh_from_db()
        self.assertFalse(self.student_a_user.is_active)
        self.assertIsNotNone(self.student_a.deactivated_at)
        self.assertTrue(ActivityLog.objects.filter(student=self.student_a, action='Kept record').exists())
        self.assertEqual(
            ProductAuditEvent.objects.filter(action='student.deactivated', target_id=str(self.student_a.id)).count(), 1,
        )

    def test_deactivated_students_disappear_from_lists_but_admins_can_open_them(self):
        from .tenancy import set_student_active

        set_student_active(self.student_a, False, self.admin)
        for user in (self.counselor, self.organization, self.teacher):
            self.client.force_authenticate(user)
            self.assertEqual(self.results(self.client.get('/api/students/')), [], user.role)
            self.assertEqual(self.client.get(f'/api/students/{self.student_a.id}/').status_code, 404)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.results(self.client.get('/api/activity/')), [])
        self.client.force_authenticate(self.admin)
        listed = {item['id'] for item in self.results(self.client.get('/api/students/'))}
        self.assertNotIn(self.student_a.id, listed)
        self.assertEqual(self.client.get(f'/api/students/{self.student_a.id}/').status_code, 200)

    def test_deactivated_students_drop_out_of_global_search_for_school_staff(self):
        from .tenancy import set_student_active

        for user in (self.counselor, self.organization):
            self.client.force_authenticate(user)
            found = self.client.get('/api/search/', {'q': 'student-a'}).data['results']
            self.assertIn(self.student_a.id, [row['id'] for row in found.get('students', [])], user.role)
        set_student_active(self.student_a, False, self.admin)
        for user in (self.counselor, self.organization, self.teacher):
            self.client.force_authenticate(user)
            found = self.client.get('/api/search/', {'q': 'student-a'}).data['results']
            self.assertNotIn(self.student_a.id, [row['id'] for row in found.get('students', [])], user.role)

    def test_account_endpoints_share_the_same_deactivation_and_reactivation(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f'/api/users/accounts/{self.student_a_user.id}/deactivate/').status_code, 200)
        self.student_a.refresh_from_db()
        self.assertIsNotNone(self.student_a.deactivated_at)
        response = self.client.patch(f'/api/users/accounts/{self.student_a_user.id}/', {'is_active': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.student_a.refresh_from_db()
        self.student_a_user.refresh_from_db()
        self.assertIsNone(self.student_a.deactivated_at)
        self.assertTrue(self.student_a_user.is_active)
        self.assertEqual(self.client.delete(f'/api/users/accounts/{self.student_a_user.id}/').status_code, 204)
        self.student_a.refresh_from_db()
        self.assertIsNotNone(self.student_a.deactivated_at)
        self.assertTrue(ProductAuditEvent.objects.filter(action='student.reactivated').exists())


class StudentProfileCreateTests(RoleIsolationBase):
    def make_student(self, username, school):
        return User.objects.create_user(
            username=username, email=f'{username}@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=school,
        )

    def create(self, user, payload):
        self.client.force_authenticate(user)
        return self.client.post('/api/students/', payload, format='json')

    def test_staff_create_profiles_only_in_their_own_school(self):
        own = self.make_student('own-profileless', self.school_a)
        response = self.create(self.organization, {'user': own.id, 'school': self.school_b.id})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['school'], self.school_a.id)
        own.refresh_from_db()
        self.assertEqual(own.school, self.school_a)
        self.assertEqual(own.student_profile.school_name, self.school_a.name)

    def test_unavailable_users_share_one_generic_error(self):
        other_school = self.make_student('other-profileless', self.school_b)
        staff = User.objects.create_user(
            username='not-a-student', email='not-a-student@example.com', password='StrongPass123!',
            role=User.Role.TEACHER, school=self.school_a,
        )
        errors = set()
        for target in (other_school.id, staff.id, self.student_a_user.id, 999999):
            for creator in (self.counselor, self.organization):
                response = self.create(creator, {'user': target})
                self.assertEqual(response.status_code, 400, (target, creator.role))
                error = response.data['user'][0]
                errors.add((str(error), error.code))
        self.assertEqual(len(errors), 1, errors)
        malformed = self.create(self.counselor, {'user': 'abc'})
        self.assertEqual(str(malformed.data['user'][0]), next(iter(errors))[0])
        self.assertFalse(StudentProfile.objects.filter(user=other_school).exists())

    def test_wrong_role_cannot_create_profiles(self):
        own = self.make_student('teacher-target', self.school_a)
        for user in (self.teacher, self.student_a_user):
            self.assertEqual(self.create(user, {'user': own.id}).status_code, 403, user.role)

    def test_staff_of_an_inactive_school_cannot_create_profiles(self):
        own = self.make_student('inactive-target', self.school_a)
        School.objects.filter(pk=self.school_a.pk).update(is_active=False)
        self.organization.refresh_from_db()
        response = self.create(self.organization, {'user': own.id})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StudentProfile.objects.filter(user=own).exists())

    def test_admin_places_a_schoolless_student_and_the_account_follows(self):
        admin = User.objects.create_user(
            username='profile-admin', email='profile-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        orphan = self.make_student('orphan-student', None)
        response = self.create(admin, {'user': orphan.id, 'school': self.school_b.id})
        self.assertEqual(response.status_code, 201, response.data)
        orphan.refresh_from_db()
        self.assertEqual(orphan.school, self.school_b)
        mismatch = self.make_student('mismatch-student', self.school_a)
        self.assertEqual(self.create(admin, {'user': mismatch.id, 'school': self.school_b.id}).status_code, 400)


class AccountCreationTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='create-admin', email='create-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )

    def test_students_are_created_only_through_quick_create(self):
        for creator in (self.admin, self.counselor):
            self.client.force_authenticate(creator)
            response = self.client.post('/api/users/accounts/', {
                'username': f'bypass-{creator.role}', 'email': f'bypass-{creator.role}@example.com',
                'role': User.Role.STUDENT, 'school': self.school_a.id,
            }, format='json')
            self.assertIn(response.status_code, {400, 403}, creator.role)
        self.assertFalse(User.objects.filter(username__startswith='bypass-').exists())

        self.client.force_authenticate(self.organization)
        response = self.client.post(
            '/api/students/quick-create/', {'name': 'Quick Student', 'password': 'StrongStudent123!'}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        student = User.objects.get(username='quick-student')
        self.assertEqual(student.school, self.school_a)
        self.assertEqual(student.student_profile.school, self.school_a)
        self.assertEqual(student.temporary_credentials.count(), 1)
        self.assertTrue(student.must_change_password)

    def test_counselor_without_an_active_school_cannot_create_accounts(self):
        School.objects.filter(pk=self.school_a.pk).update(is_active=False)
        self.counselor.refresh_from_db()
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/users/accounts/', {
            'username': 'inactive-made', 'email': 'inactive-made@example.com', 'role': User.Role.COUNSELOR,
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_quick_create_requires_the_creators_school_to_be_active(self):
        School.objects.filter(pk=self.school_a.pk).update(is_active=False)
        for creator in (self.organization, self.counselor):
            creator.refresh_from_db()
            self.client.force_authenticate(creator)
            response = self.client.post(
                '/api/students/quick-create/', {'name': f'Late {creator.role}', 'password': 'StrongStudent123!'},
                format='json',
            )
            self.assertEqual(response.status_code, 400, creator.role)
        self.assertFalse(User.objects.filter(first_name='Late').exists())
        # Wrong tenant: school B's counselor cannot place a student in school A.
        self.client.force_authenticate(self.counselor_b)
        response = self.client.post('/api/students/quick-create/', {
            'name': 'Wrong School', 'password': 'StrongStudent123!', 'school': self.school_a.id,
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_new_parent_gets_an_audited_single_use_credential(self):
        from apps.users.models import CredentialAuditEvent

        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/parent-links/invite/', {
            'student': self.student_a.id, 'email': 'credential-parent@example.com',
            'password': 'StrongParent123!', 'relationship': 'father',
        }, format='json')
        self.assertIn(response.status_code, {200, 201}, response.data)
        parent = User.objects.get(email='credential-parent@example.com')
        self.assertTrue(parent.must_change_password)
        self.assertEqual(parent.temporary_credentials.count(), 1)
        self.assertTrue(CredentialAuditEvent.objects.filter(target_user=parent, actor=self.counselor).exists())

    def test_django_admin_forms_require_a_school_for_students(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            User(username='formless', email='formless@example.com', role=User.Role.STUDENT).clean()
        with self.assertRaises(ValidationError):
            StudentProfile(user=self.student_a_user).clean()


class ParentInviteEnumerationTests(RoleIsolationBase):
    def invite(self, email, **extra):
        self.client.force_authenticate(self.counselor)
        payload = {
            'student': self.student_a.id, 'email': email, 'password': 'StrongParent123!',
            'relationship': 'guardian', **extra,
        }
        return self.client.post('/api/parent-links/invite/', payload, format='json')

    def test_every_outcome_returns_the_same_response(self):
        from .models import ParentStudentLink

        existing_parent = User.objects.create_user(
            username='secret-parent-name', email='existing-parent@example.com', password='StrongPass123!',
            role=User.Role.PARENT, first_name='Hidden', last_name='Identity',
        )
        active_parent = User.objects.create_user(
            username='active-parent-name', email='active-parent@example.com', password='StrongPass123!',
            role=User.Role.PARENT,
        )
        ParentStudentLink.objects.create(
            parent=active_parent, student=self.student_a, status=ParentStudentLink.Status.ACTIVE,
        )
        responses = {
            'new': self.invite('brand-new-parent@example.com'),
            'existing_parent': self.invite('existing-parent@example.com'),
            'active_link': self.invite('active-parent@example.com'),
            'teacher_address': self.invite(self.teacher.email),
            'other_school_student_address': self.invite(self.student_b_user.email),
        }
        shapes = set()
        for label, response in responses.items():
            self.assertEqual(response.status_code, 201, (label, response.data))
            shapes.add((tuple(sorted(response.data)), response.data['detail']))
            # The only echoed value is the address the requester typed.
            body = str({key: value for key, value in response.data.items() if key != 'email'})
            for secret in ('secret-parent-name', 'Hidden', 'active-parent-name', self.teacher.username):
                self.assertNotIn(secret, body)
        self.assertEqual(len(shapes), 1)

        # The existing parent's password was not touched; no account was
        # attached to the teacher's or the student's address.
        existing_parent.refresh_from_db()
        self.assertTrue(existing_parent.check_password('StrongPass123!'))
        self.assertTrue(ParentStudentLink.objects.filter(parent=existing_parent, status='pending').exists())
        self.assertEqual(ParentStudentLink.objects.get(parent=active_parent).status, 'active')
        self.assertFalse(ParentStudentLink.objects.filter(parent__in=[self.teacher, self.student_b_user]).exists())

    def test_password_is_required_whether_or_not_the_address_exists(self):
        User.objects.create_user(
            username='known-parent', email='known-parent@example.com', password='StrongPass123!', role=User.Role.PARENT,
        )
        first = self.invite('known-parent@example.com', password='')
        second = self.invite('unknown-parent@example.com', password='')
        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(first.data, second.data)

    def test_wrong_role_and_wrong_tenant_cannot_invite(self):
        self.client.force_authenticate(self.organization)
        response = self.client.post('/api/parent-links/invite/', {
            'student': self.student_a.id, 'email': 'org-parent@example.com', 'password': 'StrongParent123!',
            'relationship': 'guardian',
        }, format='json')
        self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(self.counselor_b)
        response = self.client.post('/api/parent-links/invite/', {
            'student': self.student_a.id, 'email': 'cross-parent@example.com', 'password': 'StrongParent123!',
            'relationship': 'guardian',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email__in=['org-parent@example.com', 'cross-parent@example.com']).exists())


class IndividualWorkspaceTests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username='ws-admin', email='ws-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/users/accounts/create-individual-counselor/', {
            'username': 'solo', 'email': 'solo@example.com', 'password': 'StrongSolo123!', 'first_name': 'Solo',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.owner = User.objects.get(username='solo')
        self.workspace = self.owner.school

    def account(self, role, username):
        return self.client.post('/api/users/accounts/', {
            'username': username, 'email': f'{username}@example.com', 'role': role, 'school': self.workspace.id,
        }, format='json')

    def test_workspace_type_and_owner_are_fixed_after_creation(self):
        for payload in ({'workspace_type': 'school'}, {'owner_counselor': self.counselor.id}):
            response = self.client.patch(f'/api/schools/{self.workspace.id}/', payload, format='json')
            self.assertEqual(response.status_code, 400, payload)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.workspace_type, School.WorkspaceType.INDIVIDUAL)
        self.assertEqual(self.workspace.owner_counselor, self.owner)
        renamed = self.client.patch(f'/api/schools/{self.workspace.id}/', {'contact_phone': '+998900000000'}, format='json')
        self.assertEqual(renamed.status_code, 200, renamed.data)

    def test_only_the_owner_counselor_belongs_to_the_workspace(self):
        for role in (User.Role.ORGANIZATION, User.Role.TEACHER, User.Role.COUNSELOR):
            self.assertEqual(self.account(role, f'ws-{role}').status_code, 400, role)
        moved = self.client.patch(f'/api/users/accounts/{self.counselor.id}/', {'school': self.workspace.id}, format='json')
        self.assertEqual(moved.status_code, 400)
        org = self.client.post(f'/api/schools/{self.workspace.id}/create-account/', {
            'username': 'ws-org', 'email': 'ws-org@example.com', 'password': 'StrongOrg123!',
        }, format='json')
        self.assertEqual(org.status_code, 400)
        self.assertFalse(User.objects.filter(school=self.workspace).exclude(pk=self.owner.pk).exists())
        # The owner still edits their own account.
        self.client.force_authenticate(self.owner)
        own = self.client.patch(f'/api/users/accounts/{self.owner.id}/', {'first_name': 'Solo Two'}, format='json')
        self.assertEqual(own.status_code, 200, own.data)

    def test_owner_adds_students_and_other_schools_cannot_reach_them(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            '/api/students/quick-create/', {'name': 'Solo Student', 'password': 'StrongStudent123!'}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['school'], self.workspace.id)
        # Wrong role/tenant: an organization school's staff sees nothing.
        for staff in (self.counselor, self.organization):
            self.client.force_authenticate(staff)
            self.assertEqual(self.client.get(f"/api/students/{response.data['id']}/").status_code, 404)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.patch(f'/api/schools/{self.workspace.id}/', {'name': 'Mine'}, format='json').status_code, 403)
