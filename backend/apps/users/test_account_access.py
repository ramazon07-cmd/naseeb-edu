from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import School, StudentProfile
from apps.users.models import ProductAuditEvent


User = get_user_model()


class AccountWriteScopeTests(APITestCase):
    """Counselors and schools must not edit or delete arbitrary students."""

    def setUp(self):
        self.school = School.objects.create(name='Scope School', code='scope-school')
        self.admin = User.objects.create_user(
            username='scope-admin', email='scope-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.counselor = self.make_user('scope-counselor', User.Role.COUNSELOR)
        self.other_counselor = self.make_user('scope-other-counselor', User.Role.COUNSELOR)
        self.organization = self.make_user('scope-org', User.Role.ORGANIZATION)
        self.assigned = self.make_student('scope-assigned', self.counselor)
        self.unassigned = self.make_student('scope-unassigned', self.other_counselor)

    def make_user(self, username, role):
        return User.objects.create_user(
            username=username, email=f'{username}@example.com', password='StrongPass123!',
            role=role, school=self.school,
        )

    def make_student(self, username, counselor):
        user = self.make_user(username, User.Role.STUDENT)
        StudentProfile.objects.create(
            user=user, school=self.school, school_name=self.school.name, assigned_counselor=counselor,
        )
        return user

    def url(self, user):
        return f'/api/users/accounts/{user.id}/'

    def test_counselor_cannot_edit_or_delete_unassigned_student(self):
        self.client.force_authenticate(self.counselor)
        patch = self.client.patch(self.url(self.unassigned), {'email': 'evil@example.com'}, format='json')
        self.assertEqual(patch.status_code, status.HTTP_404_NOT_FOUND)
        delete = self.client.delete(self.url(self.unassigned))
        self.assertIn(delete.status_code, {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND})
        self.unassigned.refresh_from_db()
        self.assertEqual(self.unassigned.email, 'scope-unassigned@example.com')
        self.assertTrue(User.objects.filter(pk=self.unassigned.pk).exists())

    def test_counselor_account_list_hides_unassigned_students(self):
        self.client.force_authenticate(self.counselor)
        ids = {row['id'] for row in self.client.get('/api/users/accounts/').data['results']}
        self.assertIn(self.assigned.id, ids)
        self.assertNotIn(self.unassigned.id, ids)

    def test_counselor_can_edit_assigned_student_but_not_delete_or_deactivate(self):
        self.client.force_authenticate(self.counselor)
        patch = self.client.patch(self.url(self.assigned), {'phone': '+998900000000'}, format='json')
        self.assertEqual(patch.status_code, status.HTTP_200_OK, patch.data)
        deactivate = self.client.patch(self.url(self.assigned), {'is_active': False}, format='json')
        self.assertEqual(deactivate.status_code, status.HTTP_400_BAD_REQUEST)
        delete = self.client.delete(self.url(self.assigned))
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)
        self.assigned.refresh_from_db()
        self.assertTrue(self.assigned.is_active)

    def test_organization_cannot_delete_or_deactivate_students(self):
        self.client.force_authenticate(self.organization)
        self.assertEqual(self.client.delete(self.url(self.assigned)).status_code, status.HTTP_403_FORBIDDEN)
        deactivate = self.client.patch(self.url(self.assigned), {'is_active': False}, format='json')
        self.assertEqual(deactivate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(User.objects.get(pk=self.assigned.pk).is_active)

    def test_student_cannot_deactivate_or_delete_self(self):
        self.client.force_authenticate(self.assigned)
        deactivate = self.client.patch(self.url(self.assigned), {'is_active': False}, format='json')
        self.assertEqual(deactivate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.delete(self.url(self.assigned)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.get(pk=self.assigned.pk).is_active)

    def test_admin_delete_is_a_soft_deactivation_with_audit(self):
        self.client.force_authenticate(self.admin)
        response = self.client.delete(self.url(self.assigned))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assigned.refresh_from_db()
        self.assertFalse(self.assigned.is_active)
        self.assertTrue(StudentProfile.objects.filter(user=self.assigned).exists())
        self.assertEqual(ProductAuditEvent.objects.filter(action='student.deactivated').count(), 1)
        self.assertFalse(ProductAuditEvent.objects.filter(action='account.deactivated').exists())
        self.assertEqual(self.client.delete(self.url(self.admin)).status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class LoginBruteForceTests(APITestCase):
    """Spoofed X-Forwarded-For must not reset the login limits."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(
            username='lockout-user', email='lockout@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def attempt(self, password, forwarded):
        return self.client.post(
            '/api/auth/token/', {'username': 'lockout-user', 'password': password},
            format='json', HTTP_X_FORWARDED_FOR=forwarded,
        )

    def test_spoofed_forwarded_for_does_not_bypass_ip_throttle(self):
        codes = [self.attempt('wrong-password', f'10.0.0.{i}').status_code for i in range(15)]
        self.assertIn(status.HTTP_429_TOO_MANY_REQUESTS, codes)

    def test_account_is_locked_after_repeated_failures(self):
        from django.core.cache import cache
        with override_settings(LOGIN_LOCKOUT_THRESHOLD=3):
            for _ in range(3):
                self.assertEqual(self.attempt('wrong', '1.1.1.1').status_code, status.HTTP_401_UNAUTHORIZED)
            # Even the correct password is refused while the account is locked.
            self.assertEqual(self.attempt('StrongPass123!', '1.1.1.1').status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            cache.clear()
            self.assertEqual(self.attempt('StrongPass123!', '1.1.1.1').status_code, status.HTTP_200_OK)

    def test_attacker_cannot_lock_victim_out_from_another_ip(self):
        with override_settings(LOGIN_LOCKOUT_THRESHOLD=3):
            for _ in range(3):
                attacker = self.client.post(
                    '/api/auth/token/', {'username': 'lockout-user', 'password': 'wrong'},
                    format='json', REMOTE_ADDR='198.51.100.66',
                )
                self.assertEqual(attacker.status_code, status.HTTP_401_UNAUTHORIZED)
            # The attacker's address is now locked for this account, even with the right password...
            locked = self.client.post(
                '/api/auth/token/', {'username': 'lockout-user', 'password': 'StrongPass123!'},
                format='json', REMOTE_ADDR='198.51.100.66',
            )
            self.assertEqual(locked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            # ...but the real owner still signs in from their own address.
            victim = self.client.post(
                '/api/auth/token/', {'username': 'lockout-user', 'password': 'StrongPass123!'},
                format='json', REMOTE_ADDR='203.0.113.10',
            )
            self.assertEqual(victim.status_code, status.HTTP_200_OK)

    def test_failures_spread_across_ips_raise_a_security_warning(self):
        with override_settings(LOGIN_LOCKOUT_THRESHOLD=100, LOGIN_ACCOUNT_ALERT_THRESHOLD=3), \
                self.assertLogs('naseeb.security', level='WARNING') as logs:
            for index in range(3):
                self.client.post(
                    '/api/auth/token/', {'username': 'lockout-user', 'password': 'wrong'},
                    format='json', REMOTE_ADDR=f'198.51.100.{index + 1}',
                )
        self.assertEqual(len(logs.records), 1)
        self.assertIn('login_failures_spread_across_ips', logs.output[0])
        # Detection only: the owner still signs in.
        response = self.client.post(
            '/api/auth/token/', {'username': 'lockout-user', 'password': 'StrongPass123!'},
            format='json', REMOTE_ADDR='203.0.113.10',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_lockout_is_per_ip(self):
        with override_settings(LOGIN_LOCKOUT_THRESHOLD=2):
            for _ in range(2):
                self.client.post('/admin/login/', {'username': 'lockout-user', 'password': 'nope'}, REMOTE_ADDR='198.51.100.66')
            self.assertEqual(
                self.client.post('/admin/login/', {'username': 'lockout-user', 'password': 'nope'}, REMOTE_ADDR='198.51.100.66').status_code,
                429,
            )
            other = self.client.post('/admin/login/', {'username': 'lockout-user', 'password': 'nope'}, REMOTE_ADDR='203.0.113.10')
            self.assertEqual(other.status_code, 200)

    def test_client_ip_honours_num_proxies(self):
        from django.test import RequestFactory
        from django.conf import settings
        from .security import client_ip
        request = RequestFactory().get('/', HTTP_X_FORWARDED_FOR='6.6.6.6, 203.0.113.9', REMOTE_ADDR='10.0.0.1')
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'NUM_PROXIES': 0}):
            self.assertEqual(client_ip(request), '10.0.0.1')
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'NUM_PROXIES': 1}):
            self.assertEqual(client_ip(request), '203.0.113.9')

    def test_admin_login_is_locked_after_repeated_failures(self):
        with override_settings(LOGIN_LOCKOUT_THRESHOLD=2):
            for _ in range(2):
                response = self.client.post('/admin/login/', {'username': 'lockout-user', 'password': 'nope'})
                self.assertEqual(response.status_code, 200)
            response = self.client.post('/admin/login/', {'username': 'lockout-user', 'password': 'nope'})
            self.assertEqual(response.status_code, 429)

    def test_admin_ip_allowlist_hides_admin(self):
        with override_settings(ADMIN_ALLOWED_IPS=['192.0.2.1']):
            self.assertEqual(self.client.get('/admin/login/').status_code, 404)
        self.assertEqual(self.client.get('/admin/login/').status_code, 200)


class StudentProfileProvisioningTests(APITestCase):
    """Every way of creating a student account yields a StudentProfile."""

    def setUp(self):
        self.school = School.objects.create(name='Provision School', code='provision-school')
        self.admin = User.objects.create_user(
            username='prov-admin', email='prov-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.counselor = User.objects.create_user(
            username='prov-counselor', email='prov-counselor@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school,
        )

    def test_admin_created_student_account_gets_profile_and_can_onboard(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/students/quick-create/', {
            'name': 'Prov Student', 'password': 'StrongStudent123!', 'school': self.school.id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        student = User.objects.get(username='prov-student')
        self.assertEqual(student.student_profile.school, self.school)
        self.assertTrue(student.must_change_password)
        student.must_change_password = False
        student.save(update_fields=['must_change_password'])
        self.client.force_authenticate(student)
        self.assertEqual(self.client.get('/api/students/onboarding/').status_code, status.HTTP_200_OK)

    def test_counselor_created_student_is_assigned_to_them(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post('/api/students/quick-create/', {
            'name': 'Prov Student Two', 'password': 'StrongStudent123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        profile = StudentProfile.objects.get(user__username='prov-student-two')
        self.assertEqual(profile.assigned_counselor, self.counselor)
        self.assertEqual(profile.school, self.school)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class AdminScalingTests(APITestCase):
    """Admin change lists/forms use joins and raw id widgets."""

    def test_admin_pages_render_with_raw_id_fields(self):
        from django.contrib import admin
        from apps.admissions.models import Task
        superuser = User.objects.create_superuser(username='adm', email='adm@example.com', password='StrongPass123!')
        task_admin = admin.site._registry[Task]
        self.assertIn('student', task_admin.raw_id_fields)
        self.assertEqual(task_admin.list_select_related, ('student__user',))
        self.client.force_login(superuser)
        for url in ('/admin/admissions/task/', '/admin/admissions/task/add/', '/admin/admissions/notification/add/',
                    '/admin/admissions/studentprofile/', '/admin/admissions/channelmessage/add/'):
            self.assertEqual(self.client.get(url).status_code, 200, url)


BROKEN_REDIS = {'default': {
    'BACKEND': 'django.core.cache.backends.redis.RedisCache',
    'LOCATION': 'redis://127.0.0.1:1/0',  # nothing listens here: connection refused
}}


@override_settings(CACHES=BROKEN_REDIS)
class CacheOutageTests(APITestCase):
    """A Redis outage must not turn throttled endpoints, login or the assistant into 500s."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='outage-user', email='outage@example.com', password='StrongPass123!', role=User.Role.STUDENT,
        )

    def test_login_throttle_and_lockout_fail_open(self):
        with self.assertLogs('naseeb.cache', level='WARNING'):
            ok = self.client.post('/api/auth/token/', {'username': 'outage-user', 'password': 'StrongPass123!'}, format='json')
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        bad = self.client.post('/api/auth/token/', {'username': 'outage-user', 'password': 'wrong'}, format='json')
        self.assertEqual(bad.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_api_and_assistant_fail_open(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get('/api/users/accounts/me/').status_code, status.HTTP_200_OK)
        response = self.client.post(
            '/api/assistant/chat/', {'messages': [{'role': 'user', 'content': 'Help with tasks'}]}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(b''.join(response.streaming_content))
