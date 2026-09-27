from importlib import import_module

from django.apps import apps as django_apps
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import School, StudentProfile
from apps.users.auth_views import token_pair_for_user
from apps.users.models import User


def staff(username, tier):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass123!',
        role=User.Role.ADMIN, admin_tier=tier,
    )


class StaffTierTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Tier School', code='tier-school')
        self.support = staff('support', User.AdminTier.SUPPORT)
        self.ops = staff('ops', User.AdminTier.OPS)
        self.superadmin = staff('superadmin', User.AdminTier.SUPERADMIN)
        self.student = User.objects.create_user(
            username='tier-student', email='tier-student@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school,
        )
        self.profile = StudentProfile.objects.create(user=self.student, school=self.school, school_name=self.school.name)
        self.counselor_payload = {
            'username': 'tier-counselor', 'email': 'tier-counselor@example.com', 'first_name': 'Tier',
            'password': 'StrongPass123!', 'school': self.school.id,
        }

    def login(self, user):
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_pair_for_user(user)["access"]}')

    def test_admins_without_an_explicit_tier_keep_full_access(self):
        legacy = User.objects.create_user(
            username='legacy-admin', email='legacy-admin@example.com', password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.assertEqual(legacy.admin_tier, User.AdminTier.SUPERADMIN)
        User.objects.filter(pk=legacy.pk).update(admin_tier='')
        import_module('apps.users.migrations.0007_admin_staff_tiers').map_existing_admins(django_apps, None)
        legacy.refresh_from_db()
        self.assertEqual(legacy.admin_tier, User.AdminTier.SUPERADMIN)

    def test_non_staff_accounts_never_carry_a_tier(self):
        counselor = User.objects.create_user(
            username='tierless', email='tierless@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school, admin_tier=User.AdminTier.SUPERADMIN,
        )
        self.assertEqual(counselor.admin_tier, '')
        self.assertEqual(counselor.staff_tier, '')

    def test_support_reads_resets_credentials_and_views_audit(self):
        self.client.force_authenticate(self.support)
        self.assertEqual(self.client.get('/api/users/accounts/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get('/api/users/audit-events/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f'/api/students/{self.profile.id}/').status_code, status.HTTP_200_OK)
        reset = self.client.post(f'/api/users/accounts/{self.student.id}/temporary-credential/', {}, format='json')
        self.assertEqual(reset.status_code, status.HTTP_200_OK)

    def test_support_cannot_manage_workspaces_or_accounts(self):
        self.client.force_authenticate(self.support)
        denied = [
            self.client.post('/api/schools/', {'name': 'New', 'code': 'new'}, format='json'),
            self.client.post('/api/users/accounts/create-counselor/', self.counselor_payload, format='json'),
            self.client.post(f'/api/users/accounts/{self.student.id}/deactivate/'),
            self.client.patch(f'/api/users/accounts/{self.student.id}/', {'phone': '1'}, format='json'),
            self.client.delete(f'/api/users/accounts/{self.student.id}/'),
        ]
        self.assertEqual({response.status_code for response in denied}, {status.HTTP_403_FORBIDDEN})
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_support_writes_outside_its_routes_are_rejected_centrally(self):
        self.login(self.support)
        response = self.client.post('/api/tasks/', {'title': 'Staff task', 'student': self.profile.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'staff_tier_forbidden')
        reset = self.client.post(f'/api/users/accounts/{self.student.id}/temporary-credential/', {}, format='json')
        self.assertEqual(reset.status_code, status.HTTP_200_OK)

    def test_ops_manages_schools_and_counselors(self):
        self.login(self.ops)
        created = self.client.post('/api/schools/', {'name': 'Ops School', 'code': 'ops-school'}, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        counselor = self.client.post('/api/users/accounts/create-counselor/', self.counselor_payload, format='json')
        self.assertEqual(counselor.status_code, status.HTTP_201_CREATED)

    def test_ops_cannot_use_superadmin_only_routes(self):
        self.login(self.ops)
        response = self.client.post('/api/counselor-roadmap-templates/', {
            'name': 'Ops template', 'kind': 'school_management', 'missions': [],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'staff_tier_forbidden')

    def test_only_superadmin_grants_admin_role_or_changes_tiers(self):
        self.client.force_authenticate(self.ops)
        promote = self.client.patch(f'/api/users/accounts/{self.student.id}/', {'role': 'admin'}, format='json')
        self.assertEqual(promote.status_code, status.HTTP_400_BAD_REQUEST)
        raise_tier = self.client.patch(f'/api/users/accounts/{self.support.id}/', {'admin_tier': 'ops'}, format='json')
        self.assertEqual(raise_tier.status_code, status.HTTP_400_BAD_REQUEST)
        self_raise = self.client.patch(f'/api/users/accounts/{self.ops.id}/', {'admin_tier': 'superadmin'}, format='json')
        self.assertEqual(self_raise.status_code, status.HTTP_400_BAD_REQUEST)
        self.support.refresh_from_db()
        self.assertEqual(self.support.admin_tier, User.AdminTier.SUPPORT)

        self.client.force_authenticate(self.superadmin)
        changed = self.client.patch(f'/api/users/accounts/{self.support.id}/', {'admin_tier': 'ops'}, format='json')
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.support.refresh_from_db()
        self.assertEqual(self.support.admin_tier, User.AdminTier.OPS)

    def test_superadmin_writes_anywhere(self):
        self.login(self.superadmin)
        response = self.client.post('/api/counselor-roadmap-templates/', {
            'name': 'Super template', 'kind': 'school_management',
            'missions': [{'title': 'Kickoff', 'sequence': 1, 'due_days': 3, 'is_required': True}],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_non_staff_are_unaffected_by_tier_routes(self):
        counselor = User.objects.create_user(
            username='plain-counselor', email='plain-counselor@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school,
        )
        self.profile.assigned_counselor = counselor
        self.profile.save(update_fields=['assigned_counselor'])
        self.login(counselor)
        response = self.client.post('/api/tasks/', {
            'title': 'Counselor task', 'student': self.profile.id,
        }, format='json')
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SuperuserConsistencyTests(APITestCase):
    def test_createsuperuser_produces_a_product_admin(self):
        call_command(
            'createsuperuser', interactive=False, username='root', email='root@example.com', verbosity=0,
        )
        root = User.objects.get(username='root')
        self.assertEqual(root.role, User.Role.ADMIN)
        self.assertEqual(root.admin_tier, User.AdminTier.SUPERADMIN)
        self.assertTrue(root.is_product_admin)
        self.assertFalse(StudentProfile.objects.filter(user=root).exists())

    def test_me_exposes_superuser_and_tier_for_navigation(self):
        root = User.objects.create_superuser('root2', 'root2@example.com', 'StrongPass123!')
        self.client.force_authenticate(root)
        me = self.client.get('/api/users/accounts/me/').data
        self.assertTrue(me['is_superuser'])
        self.assertEqual(me['role'], User.Role.ADMIN)
        self.assertEqual(me['staff_tier'], User.AdminTier.SUPERADMIN)

    def test_superuser_with_another_role_is_still_superadmin(self):
        root = User.objects.create_superuser(
            'root3', 'root3@example.com', 'StrongPass123!', role=User.Role.STUDENT,
        )
        self.assertEqual(root.staff_tier, User.AdminTier.SUPERADMIN)
        self.assertTrue(root.is_product_admin)
