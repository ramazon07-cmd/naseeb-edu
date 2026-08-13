from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import School, StudentProfile
from .credentials import issue_temporary_credential
from .models import CredentialAuditEvent, TemporaryCredential


User = get_user_model()


class StudentAdminCreationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin-test',
            email='admin-test@example.com',
            password='StrongAdminPass123!',
            role=User.Role.ADMIN,
        )
        self.school = School.objects.create(name='Rustam Bosimov School', code='rbis-test')
        self.client.force_login(self.admin)

    def test_admin_created_student_gets_profile_with_initial_level(self):
        response = self.client.post(reverse('admin:users_user_add'), {
            'username': 'new-student',
            'password1': 'StrongStudentPass123!',
            'password2': 'StrongStudentPass123!',
            'first_name': 'Muhammadrasul',
            'last_name': 'Kipchakov',
            'email': 'new-student@example.com',
            'role': User.Role.STUDENT,
            'school': self.school.id,
            'phone': '',
            'position': '',
            '_save': 'Save',
        })

        self.assertEqual(response.status_code, 302)
        student_user = User.objects.get(username='new-student')
        profile = StudentProfile.objects.get(user=student_user)
        self.assertEqual(profile.school, self.school)
        self.assertEqual(profile.school_name, self.school.name)
        self.assertEqual(profile.level, 1)
        self.assertEqual(profile.xp_total, 0)
        self.assertTrue(student_user.must_change_password)
        self.assertEqual(student_user.temporary_credentials.count(), 1)


class TemporaryCredentialLifecycleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(name='Credential School', code='credential-school')
        self.admin = User.objects.create_superuser(
            username='credential-admin',
            email='credential-admin@example.com',
            password='StrongAdminPass123!',
            role=User.Role.ADMIN,
        )
        self.counselor = User.objects.create_user(
            username='credential-counselor',
            email='credential-counselor@example.com',
            password='StrongCounselorPass123!',
            role=User.Role.COUNSELOR,
            school=self.school,
        )
        self.student = User.objects.create_user(
            username='credential-student',
            email='credential-student@example.com',
            password=None,
            role=User.Role.STUDENT,
            school=self.school,
        )
        self.profile = StudentProfile.objects.create(
            user=self.student,
            school=self.school,
            school_name=self.school.name,
            assigned_counselor=self.counselor,
        )
        self.temporary_password = 'TemporaryPass123!'
        self.student, self.credential, _, _ = issue_temporary_credential(
            user=self.student,
            issued_by=self.counselor,
            raw_password=self.temporary_password,
        )

    def login(self, password=None, language='en'):
        return self.client.post(
            '/api/auth/token/',
            {'username': self.student.username, 'password': password or self.temporary_password},
            format='json',
            HTTP_ACCEPT_LANGUAGE=language,
        )

    def test_temporary_password_is_hashed_used_once_and_forces_change(self):
        self.assertNotIn(self.temporary_password, self.student.password)
        self.assertFalse(hasattr(self.credential, 'password'))
        login = self.login()
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertTrue(login.data['must_change_password'])
        self.credential.refresh_from_db()
        self.assertEqual(self.credential.status, TemporaryCredential.Status.USED)
        self.assertIsNotNone(self.credential.used_at)

        second_login = self.login()
        self.assertEqual(second_login.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(second_login.data['code'], 'credential_used')

        access = login.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        self.assertEqual(self.client.get('/api/users/accounts/me/').status_code, status.HTTP_200_OK)
        blocked = self.client.get('/api/dashboard/stats/')
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(blocked.data['code'], 'password_change_required')

    def test_password_change_revokes_old_tokens_and_unlocks_account(self):
        login = self.login()
        old_access = login.data['access']
        old_refresh = login.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        changed = self.client.post(
            '/api/users/accounts/change-password/',
            {'new_password': 'PermanentPass456!', 'confirm_password': 'PermanentPass456!'},
            format='json',
        )
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertFalse(changed.data['user']['must_change_password'])
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('PermanentPass456!'))
        self.assertFalse(self.student.must_change_password)
        self.assertIsNotNone(self.student.password_changed_at)
        self.assertTrue(CredentialAuditEvent.objects.filter(
            target_user=self.student,
            event=CredentialAuditEvent.Event.PASSWORD_CHANGED,
        ).exists())

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        self.assertEqual(self.client.get('/api/users/accounts/me/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials()
        refreshed_old_session = self.client.post('/api/auth/token/refresh/', {'refresh': old_refresh}, format='json')
        self.assertEqual(refreshed_old_session.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed_old_session.data['access']}")
        self.assertEqual(self.client.get('/api/users/accounts/me/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {changed.data['access']}")
        self.assertEqual(self.client.get('/api/dashboard/stats/').status_code, status.HTTP_200_OK)

    def test_refresh_token_rotation_blacklists_the_used_token(self):
        login = self.login()
        refresh = login.data['refresh']
        first = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        replay = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_for_deleted_user_returns_401_not_500(self):
        login = self.login()
        refresh = login.data['refresh']
        self.student.delete()

        response = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'no_active_account')

    def test_expired_temporary_password_is_rejected_with_requested_locale(self):
        self.credential.expires_at = timezone.now()
        self.credential.save(update_fields=['expires_at'])
        response = self.login(language='ru')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'credential_expired')
        self.assertIn('истёк', response.data['detail'])
        self.credential.refresh_from_db()
        self.assertEqual(self.credential.status, TemporaryCredential.Status.EXPIRED)

    def test_scoped_reissue_revokes_previous_credential_and_sessions(self):
        first_login = self.login()
        self.client.force_authenticate(self.counselor)
        reissued = self.client.post(
            f'/api/users/accounts/{self.student.id}/temporary-credential/',
            {},
            format='json',
        )
        self.assertEqual(reissued.status_code, status.HTTP_200_OK)
        self.assertTrue(reissued.data['temporary_password'])
        self.assertNotIn(reissued.data['temporary_password'], User.objects.get(pk=self.student.pk).password)
        self.credential.refresh_from_db()
        self.assertEqual(self.credential.status, TemporaryCredential.Status.USED)
        self.assertTrue(CredentialAuditEvent.objects.filter(
            target_user=self.student,
            event=CredentialAuditEvent.Event.REISSUED,
        ).exists())

        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {first_login.data['access']}")
        self.assertEqual(self.client.get('/api/users/accounts/me/').status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unassigned_counselor_cannot_reissue_student_credential(self):
        other = User.objects.create_user(
            username='other-counselor',
            email='other-counselor@example.com',
            password='StrongPass123!',
            role=User.Role.COUNSELOR,
            school=self.school,
        )
        self.client.force_authenticate(other)
        response = self.client.post(
            f'/api/users/accounts/{self.student.id}/temporary-credential/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ApiErrorLocalizationTests(APITestCase):
    def test_russian_api_error_is_localized_at_response_boundary(self):
        response = self.client.post(
            '/api/auth/token/',
            {'username': 'missing-user', 'password': 'wrong-password'},
            format='json',
            HTTP_ACCEPT_LANGUAGE='ru-RU,ru;q=0.9',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('Сессия', response.data['detail'])

    def test_uzbek_api_error_is_localized_at_response_boundary(self):
        response = self.client.get(
            '/api/users/accounts/me/',
            HTTP_ACCEPT_LANGUAGE='uz-UZ,uz;q=0.9',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('Kirish', response.data['detail'])

    def test_english_api_error_keeps_original_detail(self):
        response = self.client.get(
            '/api/users/accounts/me/',
            HTTP_ACCEPT_LANGUAGE='en-GB,en;q=0.9',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('credentials', response.data['detail'].lower())
