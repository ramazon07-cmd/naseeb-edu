"""Counselor roadmap template search (?search=).

An earlier filter used ``memberships__...``, which CounselorRoadmapTemplate
does not have, so every ?search= raised FieldError.
"""
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions.models import CounselorRoadmapTemplate

from .test_audit_base import AuditBaseMixin

URL = '/api/counselor-roadmap-templates/'
ONBOARDING = CounselorRoadmapTemplate.Kind.PROFESSIONAL_ONBOARDING
MANAGEMENT = CounselorRoadmapTemplate.Kind.SCHOOL_MANAGEMENT


class RoadmapTemplateSearchTests(AuditBaseMixin, APITestCase):
    def setUp(self):
        super().setUp()
        CounselorRoadmapTemplate.objects.create(name='Onboarding Basics', description='First week', kind=ONBOARDING)
        CounselorRoadmapTemplate.objects.create(
            name='Term plan', description='Run the school ONBOARDING day', kind=MANAGEMENT,
        )
        CounselorRoadmapTemplate.objects.create(name='Unrelated', description='Nothing here', kind=MANAGEMENT)
        CounselorRoadmapTemplate.objects.create(
            name='Retired onboarding', description='', kind=ONBOARDING, is_active=False,
        )

    def names(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, url)
        return sorted(row['name'] for row in self.results(response))

    def test_search_matches_name_or_description_case_insensitively(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.names(f'{URL}?search=onboarding'), ['Onboarding Basics', 'Retired onboarding', 'Term plan'],
        )
        self.assertEqual(self.names(f'{URL}?search=FIRST'), ['Onboarding Basics'])

    def test_counselor_search_only_returns_active_templates(self):
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.names(f'{URL}?search=onboarding'), ['Onboarding Basics', 'Term plan'])

    def test_search_combines_with_kind_and_is_active(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.names(f'{URL}?search=onboarding&kind={ONBOARDING}'),
                         ['Onboarding Basics', 'Retired onboarding'])
        self.assertEqual(self.names(f'{URL}?search=onboarding&is_active=false'), ['Retired onboarding'])
        self.assertEqual(self.names(f'{URL}?search=onboarding&kind={MANAGEMENT}&is_active=true'), ['Term plan'])

    def test_blank_no_match_and_odd_search_terms_never_500(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(len(self.names(f'{URL}?search=%20%20')), 4)  # whitespace = no filter
        self.assertEqual(self.names(f'{URL}?search=zzz-no-match'), [])
        for term in ('%25', '_', "o'brien", '%5C', 'onboarding%20day'):
            response = self.client.get(f'{URL}?search={term}')
            self.assertEqual(response.status_code, status.HTTP_200_OK, term)
        self.assertEqual(self.names(f'{URL}?search=onboarding%20day'), ['Term plan'])

    def test_roles_without_template_access_get_empty_results(self):
        for user in (self.teacher, self.organization, self.student_user, self.parent):
            self.client.force_authenticate(user)
            self.assertEqual(self.names(f'{URL}?search=onboarding'), [], user.username)
