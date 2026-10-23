from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.db import connection
from rest_framework.test import APITestCase

from apps.admissions.models import School, StudentProfile
from apps.users.models import Plan, ProductAuditEvent, User
from apps.users.test_entitlements import make_user, use_plan


class SchoolCounselorTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='School One', code='counselor-one')
        self.other = School.objects.create(name='School Two', code='counselor-two')
        self.org = make_user('school-org', User.Role.ORGANIZATION, self.school)
        self.counselor = make_user('school-counselor', User.Role.COUNSELOR, self.school)
        self.peer = make_user('school-peer', User.Role.COUNSELOR, self.school, is_active=False)
        self.foreign = make_user('foreign-counselor', User.Role.COUNSELOR, self.other)
        self.url = f'/api/users/accounts/{self.counselor.pk}/'
        self.client.force_authenticate(self.org)

    def test_roster_includes_active_and_inactive_own_school_only(self):
        response = self.client.get('/api/users/accounts/?role=counselor')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['id'] for row in response.data['results']}, {self.counselor.pk, self.peer.pk})

    def test_profile_edit_is_audited(self):
        values = {'first_name': 'Dilnoza', 'last_name': 'Karimova', 'phone': '+998901234567', 'position': 'Lead counselor'}
        response = self.client.patch(self.url, values, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.counselor.refresh_from_db()
        self.assertEqual({field: getattr(self.counselor, field) for field in values}, values)
        event = ProductAuditEvent.objects.get(action='counselor.updated', actor=self.org)
        self.assertEqual(event.school_id, self.school.pk)
        self.assertEqual(set(event.metadata['fields']), set(values))

    def test_activation_changes_are_audited(self):
        for active, action in [(False, 'account.deactivated'), (True, 'account.reactivated')]:
            response = self.client.patch(self.url, {'is_active': active}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertTrue(ProductAuditEvent.objects.filter(action=action, actor=self.org, target_id=str(self.counselor.pk)).exists())

    def assigned_student(self):
        student = make_user('handover-student', User.Role.STUDENT, self.school)
        return StudentProfile.objects.create(user=student, school=self.school, assigned_counselor=self.counselor)

    def test_school_cannot_deactivate_counselor_without_student_handover(self):
        profile = self.assigned_student()
        response = self.client.patch(self.url, {'is_active': False, 'first_name': 'Unsaved'}, format='json')
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data['code'], 'counselor_has_students')
        self.assertEqual(int(response.data['students']), 1)
        self.counselor.refresh_from_db()
        profile.refresh_from_db()
        self.assertTrue(self.counselor.is_active)
        self.assertEqual(self.counselor.first_name, '')
        self.assertEqual(profile.assigned_counselor, self.counselor)
        self.assertFalse(ProductAuditEvent.objects.filter(actor=self.org).exists())

    def test_school_can_reassign_to_active_counselor_in_own_school(self):
        profile = self.assigned_student()
        self.peer.is_active = True
        self.peer.save(update_fields=['is_active'])
        response = self.client.patch(self.url, {
            'is_active': False, 'students': 'reassign', 'reassign_to': self.peer.pk, 'first_name': 'Updated',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        profile.refresh_from_db()
        self.counselor.refresh_from_db()
        self.assertEqual(profile.assigned_counselor, self.peer)
        self.assertFalse(self.counselor.is_active)
        self.assertEqual(self.counselor.first_name, 'Updated')
        event = ProductAuditEvent.objects.get(action='account.deactivated', actor=self.org)
        self.assertEqual(event.metadata['students_handed_over'], 1)
        self.assertEqual(event.metadata['reassigned_to'], self.peer.pk)

    def test_school_handover_rejects_foreign_inactive_and_same_counselor(self):
        profile = self.assigned_student()
        for target in [self.foreign, self.peer, self.counselor]:
            with self.subTest(target=target.pk):
                response = self.client.patch(self.url, {
                    'is_active': False, 'students': 'reassign', 'reassign_to': target.pk,
                }, format='json')
                self.assertEqual(response.status_code, 400, response.data)
        self.counselor.refresh_from_db()
        profile.refresh_from_db()
        self.assertTrue(self.counselor.is_active)
        self.assertEqual(profile.assigned_counselor, self.counselor)

    def test_school_can_explicitly_leave_students_unassigned(self):
        profile = self.assigned_student()
        response = self.client.patch(self.url, {'is_active': False, 'students': 'unassign'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        profile.refresh_from_db()
        self.assertIsNone(profile.assigned_counselor)

    def test_school_cannot_use_handover_controls_to_deactivate_another_schools_counselor(self):
        response = self.client.patch(f'/api/users/accounts/{self.foreign.pk}/', {
            'is_active': False, 'students': 'unassign',
        }, format='json')
        self.assertEqual(response.status_code, 404)
        self.foreign.refresh_from_db()
        self.assertTrue(self.foreign.is_active)

    def test_audit_failure_rolls_back_student_handover_and_deactivation(self):
        profile = self.assigned_student()
        with patch('apps.users.views.audit_product_action', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.patch(self.url, {'is_active': False, 'students': 'unassign'}, format='json')
        profile.refresh_from_db()
        self.counselor.refresh_from_db()
        self.assertEqual(profile.assigned_counselor, self.counselor)
        self.assertTrue(self.counselor.is_active)

    def test_another_school_gets_404(self):
        url = f'/api/users/accounts/{self.foreign.pk}/'
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {'phone': 'bad'}, format='json').status_code, 404)

    def test_disallowed_fields_are_rejected_even_when_unchanged(self):
        for field, value in {
            'role': 'admin', 'school': self.other.pk, 'email': 'bad@example.com',
            'username': 'renamed', 'password': 'StrongPass123!', 'admin_tier': 'superadmin',
            'is_superuser': True, 'avatar': None,
        }.items():
            with self.subTest(field=field):
                response = self.client.patch(self.url, {field: value, 'first_name': 'Bad'}, format='json')
                self.assertEqual(response.status_code, 400, response.data)
        for field, value in [('role', 'counselor'), ('school', self.school.pk)]:
            self.assertEqual(self.client.patch(self.url, {field: value}, format='json').status_code, 400)
        self.counselor.refresh_from_db()
        self.assertEqual(self.counselor.first_name, '')
        self.assertFalse(ProductAuditEvent.objects.filter(actor=self.org).exists())

    def test_generic_creation_deletion_and_admin_actions_are_denied(self):
        payload = {'username': 'unauthorized', 'email': 'unauthorized@example.com', 'role': 'counselor',
                   'school': self.school.pk, 'first_name': 'Bad', 'password': 'StrongPass123!'}
        self.assertEqual(self.client.post('/api/users/accounts/', payload, format='json').status_code, 403)
        self.assertEqual(self.client.delete(self.url).status_code, 403)
        for action in ['temporary-credential', 'transfer-school', 'deactivate', 'support-view']:
            self.assertEqual(self.client.post(f'{self.url}{action}/', payload, format='json').status_code, 403)

    def provision(self, **overrides):
        return self.client.post('/api/users/accounts/create-counselor/', {
            'username': 'new-counselor', 'email': 'new-counselor@example.com',
            'first_name': 'Dilnoza', 'last_name': 'Karimova',
            'phone': '+998901234567', 'position': 'School counselor',
            'password': 'StrongPass123!', **overrides,
        }, format='json')

    def test_school_can_create_own_counselor_with_temporary_login_and_audit(self):
        # Even injected privilege fields cannot change the provisioned role/access.
        response = self.provision(role='admin', is_staff=True, is_superuser=True, admin_tier='superadmin')
        self.assertEqual(response.status_code, 201, response.data)
        account = User.objects.get(pk=response.data['id'])
        self.assertEqual((account.role, account.school_id), (User.Role.COUNSELOR, self.school.pk))
        self.assertFalse(account.is_staff)
        self.assertFalse(account.is_superuser)
        self.assertEqual(account.admin_tier, '')
        self.assertTrue(account.check_password('StrongPass123!'))
        self.assertTrue(account.must_change_password)
        self.assertTrue(account.temporary_credentials.filter(issued_by=self.org, status='issued').exists())
        event = ProductAuditEvent.objects.get(action='counselor.created', actor=self.org)
        self.assertEqual(event.school_id, self.school.pk)
        self.assertNotIn('password', response.data)

    def test_school_cannot_provision_in_another_school(self):
        response = self.provision(school=self.other.pk)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(User.objects.filter(username='new-counselor').exists())

    def test_school_can_explicitly_provision_in_own_school(self):
        response = self.provision(school=self.school.pk)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['school'], self.school.pk)

    def test_school_provisioning_obeys_seat_limits(self):
        use_plan(self.school, max_counselors=1)
        response = self.provision()
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(User.objects.filter(username='new-counselor').exists())

    def test_inactive_or_unlinked_school_account_cannot_provision(self):
        self.school.is_active = False
        self.school.save(update_fields=['is_active'])
        self.org.refresh_from_db()
        self.assertEqual(self.provision().status_code, 403)
        self.org.school = None
        self.org.save(update_fields=['school'])
        self.assertEqual(self.provision(school=self.other.pk).status_code, 403)
        self.assertFalse(User.objects.filter(username='new-counselor').exists())

    def test_other_roles_cannot_provision_counselors(self):
        for role in [User.Role.COUNSELOR, User.Role.STUDENT, User.Role.TEACHER, User.Role.PARENT]:
            school = None if role == User.Role.PARENT else self.school
            actor = make_user(f'provision-{role}', role, school)
            self.client.force_authenticate(actor)
            with self.subTest(role=role):
                self.assertEqual(self.provision(school=self.school.pk).status_code, 403)
        self.assertFalse(User.objects.filter(username='new-counselor').exists())

    def test_product_admin_still_needs_to_select_school(self):
        admin = make_user('provision-admin', User.Role.ADMIN, None)
        self.client.force_authenticate(admin)
        response = self.provision()
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('school', response.data)

    def test_provisioning_audit_failure_rolls_back_new_account(self):
        with patch('apps.users.serializers.audit_product_action', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.provision()
        self.assertFalse(User.objects.filter(username='new-counselor').exists())

    def test_counselors_still_cannot_edit_each_other(self):
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.patch(f'/api/users/accounts/{self.peer.pk}/', {'phone': 'bad'}, format='json').status_code, 403)

    def test_reactivation_checks_explicit_plan_limits(self):
        use_plan(self.school, max_counselors=1)
        response = self.client.patch(f'/api/users/accounts/{self.peer.pk}/', {'is_active': True}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.peer.refresh_from_db()
        self.assertFalse(self.peer.is_active)

    def test_audit_failure_rolls_back_profile_edit(self):
        with patch('apps.users.views.audit_product_action', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.patch(self.url, {'first_name': 'Uncommitted'}, format='json')
        self.counselor.refresh_from_db()
        self.assertEqual(self.counselor.first_name, '')

    def test_migration_changes_only_school_standard_and_reverses(self):
        migration = import_module('apps.users.migrations.0018_unlimited_school_counselors')
        standard = Plan.objects.get(code='school-standard')
        standard.max_counselors = 3
        standard.save()
        use_plan(self.other, code='limited-school', max_counselors=2)
        editor = SimpleNamespace(connection=connection)
        migration.unlimited_school_counselors(apps, editor)
        standard.refresh_from_db()
        self.assertIsNone(standard.max_counselors)
        self.assertEqual(Plan.objects.get(code='individual-counselor').max_counselors, 1)
        self.assertEqual(Plan.objects.get(code='limited-school').max_counselors, 2)
        migration.restore_school_limit(apps, editor)
        standard.refresh_from_db()
        self.assertEqual(standard.max_counselors, 3)
