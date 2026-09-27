from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import School, StudentProfile
from apps.users.auth_views import token_pair_for_user
from apps.users.models import ProductAuditEvent, User


class SupportViewTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name='Help School', code='help-school')
        self.support = User.objects.create_user(
            username='helper', email='helper@example.com', password='StrongPass123!',
            role=User.Role.ADMIN, admin_tier=User.AdminTier.SUPPORT,
        )
        self.student = User.objects.create_user(
            username='helped', email='helped@example.com', password='StrongPass123!',
            role=User.Role.STUDENT, school=self.school,
        )
        StudentProfile.objects.create(user=self.student, school=self.school, school_name=self.school.name, grade='10')
        self.url = f'/api/users/accounts/{self.student.id}/support-view/'

    def login(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_pair_for_user(user)["access"]}')

    def test_support_view_requires_a_reason(self):
        self.login(self.support)
        response = self.client.post(self.url, {'reason': 'short'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProductAuditEvent.objects.exists())

    def test_support_view_is_audited_read_only_and_holds_no_private_content(self):
        self.login(self.support)
        reason = 'Ticket 42: student cannot sign in after reset'
        response = self.client.post(self.url, {'reason': reason}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['account']['username'], 'helped')
        self.assertEqual(response.data['student']['grade'], '10')
        self.assertEqual(response.data['workspace']['plan'], 'school-standard')
        self.assertEqual(set(response.data), {'account', 'workspace', 'student', 'credential_events'})
        self.assertNotIn('access', response.data)
        event = ProductAuditEvent.objects.get(action='support.profile_viewed')
        self.assertEqual(event.actor, self.support)
        self.assertEqual(event.school_id, self.school.id)
        self.assertEqual(event.metadata['reason'], reason)
        self.student.refresh_from_db()
        self.assertEqual(self.student.password_version, 1)

    def test_only_product_staff_open_support_views(self):
        counselor = User.objects.create_user(
            username='help-counselor', email='help-counselor@example.com', password='StrongPass123!',
            role=User.Role.COUNSELOR, school=self.school,
        )
        self.login(counselor)
        response = self.client.post(
            f'/api/users/accounts/{counselor.id}/support-view/', {'reason': 'Looking at my own account'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
