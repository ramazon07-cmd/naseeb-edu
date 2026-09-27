"""Account settings: own password, email and dashboard layout."""
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import School, StudentProfile
from apps.users.models import CredentialAuditEvent, User, WorkspaceSubscription
from apps.users.test_throttles import rates

PASSWORD = 'StrongPass123!'
NEW_PASSWORD = 'BrandNewPass456!'


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AccountSettingsBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.school = School.objects.create(name='Settings School', code='settings-school')
        self.student = self.make_student('settings-student')
        self.other = self.make_student('settings-other')

    def make_student(self, username):
        user = User.objects.create_user(
            username=username, email=f'{username}@example.com', password=PASSWORD,
            role=User.Role.STUDENT, school=self.school,
        )
        StudentProfile.objects.create(user=user, school=self.school, school_name=self.school.name)
        return user

    def login(self, username='settings-student', password=PASSWORD):
        response = self.client.post('/api/auth/token/', {'username': username, 'password': password}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def bearer(self, access):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')


class OwnPasswordChangeTests(AccountSettingsBase):
    url = '/api/users/accounts/me/password/'

    def change(self, current=PASSWORD, new=NEW_PASSWORD, confirm=None):
        return self.client.post(self.url, {
            'current_password': current, 'new_password': new, 'confirm_password': confirm or new,
        }, format='json')

    def test_change_keeps_this_session_and_ends_the_others(self):
        first = self.login()
        other_device = self.login()
        self.bearer(first['access'])
        response = self.change()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['id'], self.student.id)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(NEW_PASSWORD))
        self.assertFalse(self.student.must_change_password)
        self.assertIsNotNone(self.student.password_changed_at)
        self.assertTrue(CredentialAuditEvent.objects.filter(
            target_user=self.student, event=CredentialAuditEvent.Event.PASSWORD_CHANGED,
        ).exists())

        # The new pair works; old access tokens (this and other devices) do not.
        self.bearer(response.data['access'])
        self.assertEqual(self.client.get('/api/users/accounts/me/').status_code, status.HTTP_200_OK)
        for access in (first['access'], other_device['access']):
            self.bearer(access)
            self.assertEqual(self.client.get('/api/users/accounts/me/').status_code, status.HTTP_401_UNAUTHORIZED)
        # A refresh of an old session hands out a token that is already revoked.
        self.client.credentials()
        refreshed = self.client.post('/api/auth/token/refresh/', {'refresh': other_device['refresh']}, format='json')
        if refreshed.status_code == status.HTTP_200_OK:
            self.bearer(refreshed.data['access'])
            self.assertEqual(self.client.get('/api/users/accounts/me/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials()
        self.login(password=NEW_PASSWORD)

    def test_wrong_current_password_is_rejected(self):
        self.client.force_authenticate(self.student)
        response = self.change(current='not-my-password')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['current_password'][0].code, 'wrong_password')
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(PASSWORD))

    def test_password_validators_and_confirmation_apply(self):
        self.client.force_authenticate(self.student)
        weak = self.change(new='12345678')
        self.assertEqual(weak.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', weak.data)
        mismatch = self.change(confirm='SomethingElse789!')
        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirm_password', mismatch.data)
        same = self.change(new=PASSWORD)
        self.assertEqual(same.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', same.data)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(PASSWORD))

    def test_requires_sign_in_and_is_throttled(self):
        self.assertEqual(self.change().status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.student)
        with rates(password_change='2/hour'):
            codes = [self.change(current='wrong').status_code for _ in range(3)]
        self.assertEqual(codes, [400, 400, 429])

    def test_pending_forced_change_must_use_the_first_login_screen(self):
        self.student.must_change_password = True
        self.student.save(update_fields=['must_change_password'])
        access = self.login_with_forced_change()
        self.bearer(access)
        response = self.change()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'password_change_required')

    def login_with_forced_change(self):
        from apps.users.auth_views import token_pair_for_user
        return token_pair_for_user(self.student)['access']

    def test_allowed_in_a_read_only_workspace(self):
        from apps.users import entitlements
        subscription = entitlements.ensure_subscription(self.school)
        subscription.status = WorkspaceSubscription.Status.EXPIRED
        subscription.save()
        self.bearer(self.login()['access'])
        # Other account changes pause with the rest of the workspace.
        email = self.client.post(
            '/api/users/accounts/me/email/', {'current_password': PASSWORD, 'email': 'x@example.com'}, format='json',
        )
        self.assertEqual(email.status_code, status.HTTP_403_FORBIDDEN)
        response = self.change()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class OwnEmailChangeTests(AccountSettingsBase):
    url = '/api/users/accounts/me/email/'

    def test_change_email_with_current_password(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(self.url, {'current_password': PASSWORD, 'email': 'New.Address@Example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['email'], 'New.Address@example.com')
        self.assertEqual(response.data['username'], 'settings-student')
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, 'New.Address@example.com')

    def test_wrong_current_password_is_rejected(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(self.url, {'current_password': 'nope', 'email': 'x@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['current_password'][0].code, 'wrong_password')
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, 'settings-student@example.com')

    def test_email_must_be_unique_and_valid(self):
        self.client.force_authenticate(self.student)
        taken = self.client.post(self.url, {'current_password': PASSWORD, 'email': 'SETTINGS-OTHER@example.com'}, format='json')
        self.assertEqual(taken.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(taken.data['email'][0].code, 'email_taken')
        invalid = self.client.post(self.url, {'current_password': PASSWORD, 'email': 'not-an-email'}, format='json')
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        # Re-saving your own address (any case) is fine.
        same = self.client.post(self.url, {'current_password': PASSWORD, 'email': 'settings-student@example.com'}, format='json')
        self.assertEqual(same.status_code, status.HTTP_200_OK)

    def test_student_cannot_change_email_through_the_generic_account_update(self):
        self.client.force_authenticate(self.student)
        response = self.client.patch(
            f'/api/users/accounts/{self.student.id}/', {'email': 'sneaky@example.com'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, 'settings-student@example.com')

    def test_throttled(self):
        self.client.force_authenticate(self.student)
        with rates(account_change='1/hour'):
            codes = [
                self.client.post(self.url, {'current_password': 'x', 'email': 'a@example.com'}, format='json').status_code
                for _ in range(2)
            ]
        self.assertEqual(codes, [400, 429])


class DashboardLayoutTests(AccountSettingsBase):
    url = '/api/users/accounts/me/dashboard-layout/'
    layout = {'order': ['tasks', 'journey', 'team'], 'hidden': ['team'], 'rail': ['journey']}

    def test_empty_until_saved_then_shared_across_sessions(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(self.url).data, {'layout': None})
        saved = self.client.put(self.url, {'layout': self.layout}, format='json')
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        self.assertEqual(saved.data['layout'], self.layout)
        self.client.force_authenticate(None)
        self.bearer(self.login()['access'])
        self.assertEqual(self.client.get(self.url).data['layout'], self.layout)

    def test_layout_is_per_user(self):
        self.client.force_authenticate(self.student)
        self.client.put(self.url, {'layout': self.layout}, format='json')
        self.client.force_authenticate(self.other)
        self.assertIsNone(self.client.get(self.url).data['layout'])

    def test_duplicates_are_dropped(self):
        self.client.force_authenticate(self.student)
        response = self.client.put(self.url, {'layout': {'order': ['tasks', 'tasks', 'team']}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['layout'], {'order': ['tasks', 'team']})

    def test_shape_and_size_are_validated(self):
        self.client.force_authenticate(self.student)
        invalid = [
            None,
            [],
            'tasks',
            {},
            {'order': 'tasks'},
            {'order': ['tasks'], 'extra': []},
            {'order': [1, 2]},
            {'order': ['Tasks!']},
            {'order': ['x' * 41]},
            {'order': [f'w{i}' for i in range(25)]},
            {'order': ['tasks'], 'hidden': {'a': 1}},
        ]
        for layout in invalid:
            response = self.client.put(self.url, {'layout': layout}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, layout)
        self.assertEqual(self.client.put(self.url, {}, format='json').status_code, status.HTTP_400_BAD_REQUEST)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.dashboard_layout)

    def test_requires_sign_in(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.put(self.url, {'layout': self.layout}, format='json').status_code, status.HTTP_401_UNAUTHORIZED)

    def test_layout_is_not_part_of_account_listings(self):
        self.client.force_authenticate(self.student)
        self.client.put(self.url, {'layout': self.layout}, format='json')
        self.assertNotIn('dashboard_layout', self.client.get('/api/users/accounts/me/').data)
