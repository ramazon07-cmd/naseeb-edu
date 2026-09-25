"""Role isolation: university catalog, college research and education-match AI."""
from datetime import date
from django.test import override_settings
from rest_framework import status
from apps.users.models import User
from ..education_ai import latest_assessment_scores
from ..models import (
    ChallengeAttempt,
    OpportunityProgram,
    Scholarship,
    University,
    UniversityProgram,
)
from .base import RoleIsolationBase


class CatalogResearchRoleIsolationTests(RoleIsolationBase):
    def test_student_reads_active_scholarship_and_program_catalogs(self):
        active_scholarship = Scholarship.objects.create(
            title='Active Scholarship', provider='Naseeb', scholarship_type=Scholarship.Type.MERIT,
            funding_level=Scholarship.FundingLevel.FULL, scope=Scholarship.Scope.INTERNATIONAL,
        )
        Scholarship.objects.create(
            title='Hidden Scholarship', provider='Naseeb', scholarship_type=Scholarship.Type.NEED_BASED,
            scope=Scholarship.Scope.NATIONAL, is_active=False,
        )
        OpportunityProgram.objects.filter(source_key__isnull=False).delete()  # migrated catalog snapshot
        national_program = OpportunityProgram.objects.create(
            title='National Program', provider='Naseeb', program_type=OpportunityProgram.ProgramType.NATIONAL,
            category='Research',
        )
        international_program = OpportunityProgram.objects.create(
            title='International Program', provider='Naseeb', program_type=OpportunityProgram.ProgramType.INTERNATIONAL,
            category='Leadership',
        )
        OpportunityProgram.objects.create(
            title='Hidden Program', provider='Naseeb', program_type=OpportunityProgram.ProgramType.NATIONAL,
            category='Camp', is_active=False,
        )
        self.client.force_authenticate(self.student_a_user)
        scholarships = self.results(self.client.get('/api/scholarships/'))
        programs = self.results(self.client.get('/api/opportunity-programs/'))
        self.assertEqual([item['id'] for item in scholarships], [active_scholarship.id])
        self.assertEqual({item['id'] for item in programs}, {national_program.id, international_program.id})
        self.assertEqual({item['program_type'] for item in programs}, {'national', 'international'})

    def test_university_api_exposes_niche_style_aid_fields(self):
        university = University.objects.create(
            name='Aid University', country='Testland', acceptance_rate='42.50', sat_min=1200, sat_max=1400,
            net_price_usd=18000, average_aid_usd=12000, offers_merit_aid=True,
            offers_international_aid=True, test_optional=True,
        )
        UniversityProgram.objects.create(
            university=university,
            name='BSc Computer Science',
            canonical_major='Computer Science',
            tuition_usd=18000,
            source_url='https://example.edu/programs/computer-science',
            verified_at=date(2026, 9, 12),
        )
        self.client.force_authenticate(self.student_a_user)
        result = self.results(self.client.get('/api/universities/'))[0]
        self.assertEqual(result['acceptance_rate'], '42.50')
        self.assertEqual(result['net_price_usd'], 18000)
        self.assertTrue(result['offers_international_aid'])
        self.assertTrue(result['test_optional'])
        self.assertEqual(result['programs'][0]['canonical_major'], 'Computer Science')
        self.assertEqual(result['programs'][0]['verified_at'], '2026-09-12')

    def test_only_product_admin_can_write_universities_others_stay_read_only(self):
        university = University.objects.create(name='Write Scope University', country='Testland')
        self.client.force_authenticate(self.counselor)

        readable = self.client.get('/api/universities/')
        self.assertEqual(readable.status_code, status.HTTP_200_OK)

        blocked_patch = self.client.patch(
            f'/api/universities/{university.id}/',
            {'name': 'Renamed by counselor'},
            format='json',
        )
        self.assertEqual(blocked_patch.status_code, status.HTTP_403_FORBIDDEN)

        blocked_delete = self.client.delete(f'/api/universities/{university.id}/')
        self.assertEqual(blocked_delete.status_code, status.HTTP_403_FORBIDDEN)
        university.refresh_from_db()
        self.assertEqual(university.name, 'Write Scope University')

        admin = User.objects.create_user(
            username='university-write-admin',
            email='university-write-admin@example.com',
            password='StrongPass123!',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(admin)
        allowed_patch = self.client.patch(
            f'/api/universities/{university.id}/',
            {'name': 'Renamed by admin'},
            format='json',
        )
        self.assertEqual(allowed_patch.status_code, status.HTTP_200_OK)

    def test_university_market_is_inferred_from_country(self):
        cases = [
            ('United States', University.Market.US),
            ('Canada', University.Market.CANADA),
            ('China', University.Market.CHINA),
            ('Hong Kong', University.Market.HONG_KONG),
        ]
        for index, (country, expected_market) in enumerate(cases):
            university = University.objects.create(name=f'Market University {index}', country=country)
            self.assertEqual(university.market, expected_market)

    def test_college_research_asks_only_for_missing_profile_data(self):
        self.student_a.gpa = '4.80'
        self.student_a.save(update_fields=['gpa', 'updated_at'])
        self.client.force_authenticate(self.student_a_user)

        response = self.client.get('/api/college-research/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ready'])
        self.assertNotIn('gpa', response.data['missing_fields'])
        self.assertIn('sat_score', response.data['missing_fields'])
        self.assertIn('target_major', response.data['missing_fields'])
        self.assertEqual(
            {question['field'] for question in response.data['questions']},
            set(response.data['missing_fields']),
        )

    def test_student_can_complete_profile_and_receive_ranked_college_research(self):
        university = University.objects.create(
            name='Profile Match University', country='United States', city='Boston', ranking=12,
            acceptance_rate='34.00', sat_min=1350, sat_max=1500, net_price_usd=18000,
            average_aid_usd=24000, offers_merit_aid=True, offers_international_aid=True,
            popular_majors='Computer Science, Data Science',
        )
        self.client.force_authenticate(self.student_a_user)

        response = self.client.post(
            '/api/college-research/',
            {
                'gpa': '4.70',
                'sat_score': 1450,
                'ielts_score': '7.5',
                'target_major': 'Computer Science',
                'target_countries': 'United States, Canada',
                'budget_usd': 22000,
                'scholarship_needed': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['ready'])
        self.assertEqual(response.data['recommendations'][0]['university']['id'], university.id)
        self.assertGreaterEqual(response.data['recommendations'][0]['match_score'], 65)
        self.assertIn(response.data['recommendations'][0]['admission_band'], {'reach', 'target', 'safety'})
        self.assertIn('academic', response.data['recommendations'][0]['score_breakdown'])
        self.student_a.refresh_from_db()
        self.assertEqual(self.student_a.sat_score, 1450)
        self.assertEqual(self.student_a.target_major, 'Computer Science')

    def test_non_student_cannot_use_college_research(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.get('/api/college-research/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(GROQ_API_KEY='')
    def test_major_match_ai_has_validated_offline_fallback(self):
        self.student_a.gpa = '4.70'
        self.student_a.sat_score = 1450
        self.student_a.ielts_score = '7.5'
        self.student_a.target_major = 'Computer Science'
        self.student_a.target_countries = 'United States'
        self.student_a.budget_usd = 30000
        self.student_a.scholarship_needed = True
        self.student_a.save(update_fields=[
            'gpa', 'sat_score', 'ielts_score', 'target_major', 'target_countries',
            'budget_usd', 'scholarship_needed', 'updated_at',
        ])
        self.client.force_authenticate(self.student_a_user)
        response = self.client.post(
            '/api/education-matches/ai/',
            {
                'major_candidates': ['Computer Science', 'Economics', 'Computer Science'],
                'subject_strengths': ['Mathematics', 'Physics'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['mode'], 'deterministic')
        self.assertFalse(response.data['provider_available'])
        self.assertEqual(
            [item['major'] for item in response.data['major_guidance']],
            ['Computer Science', 'Economics'],
        )
        self.assertEqual(response.data['major_guidance'][0]['subjects_to_focus'], ['Mathematics', 'Physics'])
        self.assertNotIn('college_explanations', response.data)

    def test_major_ai_uses_current_assessments_and_ignores_retired_work_values(self):
        for challenge in ['personality', 'interests', 'subjects', 'reasoning', 'values', 'workimportance']:
            ChallengeAttempt.objects.create(
                student=self.student_a,
                challenge=challenge,
                scores={'marker': challenge},
            )
        scores = latest_assessment_scores(self.student_a)
        self.assertEqual(set(scores), {'personality', 'interests', 'subjects', 'reasoning'})

    def test_non_student_cannot_generate_education_match_guidance(self):
        self.client.force_authenticate(self.counselor)
        response = self.client.post(
            '/api/education-matches/ai/',
            {'major_candidates': ['Computer Science']},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
