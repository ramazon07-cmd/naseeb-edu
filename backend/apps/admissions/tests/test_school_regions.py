"""SchoolRegionWritePermissionTests (split from tests.py)."""
from rest_framework import status
from rest_framework.test import APITestCase
from apps.users.models import User
from ..models import School


class SchoolRegionWritePermissionTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='Region Write School', code='region-write', region=School.Region.BUKHARA,
        )
        self.admin = User.objects.create_user(
            username='region-admin', email='region-admin@example.com',
            password='StrongPass123!', role=User.Role.ADMIN,
        )
        self.organization = User.objects.create_user(
            username='region-org', email='region-org@example.com',
            password='StrongPass123!', role=User.Role.ORGANIZATION, school=self.school,
        )

    def test_product_admin_can_set_region(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f'/api/schools/{self.school.id}/', {'region': School.Region.NAVOIY}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['region'], School.Region.NAVOIY)

    def test_organization_cannot_change_its_region(self):
        self.client.force_authenticate(self.organization)
        response = self.client.patch(
            f'/api/schools/{self.school.id}/', {'region': School.Region.NAVOIY}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.school.refresh_from_db()
        self.assertEqual(self.school.region, School.Region.BUKHARA)

    def test_region_is_readable_on_school_serializer(self):
        self.client.force_authenticate(self.organization)
        response = self.client.get(f'/api/schools/{self.school.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['region'], School.Region.BUKHARA)
