"""PublicReachTests (split from tests.py)."""
import json
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase
from apps.users.models import User
from ..models import School, StudentProfile


class PublicReachTests(APITestCase):
    URL = '/api/public/reach/'

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.samarkand = School.objects.create(
            name='Reach School Alpha', code='reach-alpha', region=School.Region.SAMARKAND,
        )
        self.tashkent_city = School.objects.create(
            name='Reach School Beta', code='reach-beta', region=School.Region.TASHKENT_CITY,
        )
        self.unassigned = School.objects.create(name='Reach School Gamma', code='reach-gamma')

        self.students = {}
        for username, school in (
            ('reach-sam-1', self.samarkand),
            ('reach-sam-2', self.samarkand),
            ('reach-tas-1', self.tashkent_city),
            ('reach-none-1', self.unassigned),
        ):
            user = User.objects.create_user(
                username=username,
                email=f'{username}@example.com',
                password='StrongPass123!',
                first_name='Zuhra',
                last_name='Reachtest',
                role=User.Role.STUDENT,
                school=school,
            )
            self.students[username] = StudentProfile.objects.create(
                user=user, school=school, school_name=school.name,
            )

    @staticmethod
    def regions_by_value(response):
        return {item['region']: item for item in response.data['regions']}

    def test_public_reach_is_available_without_credentials(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_public_reach_has_no_personally_identifying_data(self):
        response = self.client.get(self.URL)
        self.assertEqual(set(response.data), {'total', 'regions'})
        for item in response.data['regions']:
            self.assertEqual(set(item), {'region', 'label', 'students', 'active'})

        payload = json.dumps(response.data)
        for school in (self.samarkand, self.tashkent_city, self.unassigned):
            self.assertNotIn(school.name, payload)
            self.assertNotIn(school.code, payload)
        for profile in self.students.values():
            self.assertNotIn(profile.user.username, payload)
            self.assertNotIn(profile.user.email, payload)

    @override_settings(PUBLIC_REACH_MIN_CELL=0)
    def test_public_reach_counts_are_correct(self):
        response = self.client.get(self.URL)
        regions = self.regions_by_value(response)
        self.assertEqual(len(regions), 14)
        self.assertEqual(set(regions), set(School.Region.values))
        self.assertEqual(regions['samarkand']['students'], 2)
        self.assertTrue(regions['samarkand']['active'])
        self.assertEqual(regions['tashkent_city']['students'], 1)
        self.assertTrue(regions['tashkent_city']['active'])
        self.assertEqual(regions['khorezm']['students'], 0)
        self.assertFalse(regions['khorezm']['active'])
        self.assertEqual(sum(item['students'] for item in response.data['regions']), 3)
        self.assertEqual(response.data['total'], 4)

    def test_public_reach_is_cached(self):
        self.client.get(self.URL)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(queries), 0)

    @override_settings(PUBLIC_REACH_MIN_CELL=2)
    def test_small_regions_can_be_suppressed(self):
        response = self.client.get(self.URL)
        regions = self.regions_by_value(response)
        self.assertEqual(regions['samarkand']['students'], 2)
        self.assertEqual(regions['tashkent_city']['students'], 0)
        self.assertTrue(regions['tashkent_city']['active'])
        # The suppressed cell is not recoverable as total minus published
        # cells: what remains is only the region-less student.
        self.assertEqual(response.data['total'], 3)

    def test_small_regions_are_suppressed_by_default(self):
        self.assertEqual(settings.PUBLIC_REACH_MIN_CELL, 5)
        response = self.client.get(self.URL)
        regions = self.regions_by_value(response)
        self.assertEqual(regions['samarkand']['students'], 0)
        self.assertEqual(regions['tashkent_city']['students'], 0)
        self.assertTrue(regions['samarkand']['active'])
        self.assertEqual(response.data['total'], 1)

    def test_region_contract_matches_schema_configuration(self):
        configured = settings.SPECTACULAR_SETTINGS['ENUM_NAME_OVERRIDES']['SchoolRegionEnum']
        self.assertEqual([tuple(pair) for pair in configured], [tuple(pair) for pair in School.Region.choices])

    def test_other_existing_endpoints_remain_authenticated(self):
        for url in (
            '/api/students/',
            '/api/schools/',
            '/api/applications/',
            '/api/tasks/',
            '/api/dashboard/stats/',
            '/api/parent-portal/',
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_public_reach_rejects_writes(self):
        response = self.client.post(self.URL, {'total': 99}, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
