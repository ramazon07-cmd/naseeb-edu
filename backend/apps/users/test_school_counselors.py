from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.db import connection
from rest_framework.test import APITestCase

from apps.admissions.models import School
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

    def test_creation_deletion_and_admin_actions_are_denied(self):
        payload = {'username': 'unauthorized', 'email': 'unauthorized@example.com', 'role': 'counselor',
                   'school': self.school.pk, 'first_name': 'Bad', 'password': 'StrongPass123!'}
        for url in ['/api/users/accounts/', '/api/users/accounts/create-counselor/']:
            self.assertEqual(self.client.post(url, payload, format='json').status_code, 403)
        self.assertEqual(self.client.delete(self.url).status_code, 403)
        for action in ['temporary-credential', 'transfer-school', 'deactivate', 'support-view']:
            self.assertEqual(self.client.post(f'{self.url}{action}/', payload, format='json').status_code, 403)

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
