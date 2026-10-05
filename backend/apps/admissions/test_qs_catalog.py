"""QS World University Rankings import and the worldwide college research it feeds."""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status

from .management.commands.load_qs_rankings import DATA_FILE
from .models import University
from .tests.base import RoleIsolationBase


def row(name, country, rank, rank_label='', kind='public'):
    return {'name': name, 'country': country, 'rank': rank, 'rank_label': rank_label, 'type': kind}


class LoadQsRankingsTests(TestCase):
    def load(self, *rows):
        snapshot = {'source': 'QS World University Rankings 2027', 'source_url': 'https://www.topuniversities.com/', 'universities': list(rows)}
        output = StringIO()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.json'
            path.write_text(json.dumps(snapshot), encoding='utf-8')
            call_command('load_qs_rankings', file=str(path), stdout=output)
        return output.getvalue()

    def test_adds_universities_with_market_rank_and_type(self):
        self.load(
            row('Peking University', 'China', 14),
            row('Zarqa University (ZU)', 'Jordan', 1401, '1401+', 'private'),
            row('Status Unknown University', 'Uzbekistan', 951, '951-1000', ''),
        )
        values = lambda name: University.objects.values_list('market', 'ranking', 'ranking_label', 'institution_type').get(name=name)
        self.assertEqual(values('Peking University'), (University.Market.CHINA, 14, '', 'public'))
        self.assertEqual(values('Zarqa University (ZU)'), ('', 1401, '1401+', 'private'))
        self.assertEqual(values('Status Unknown University'), ('', 951, '951-1000', ''))

    def test_existing_university_keeps_its_details_and_only_takes_the_rank(self):
        duke = University.objects.create(name='Duke University', country='USA', sat_min=1500, net_price_usd=26000, ranking=99)
        nus = University.objects.create(name='National University of Singapore', country='Singapore')
        ntu = University.objects.create(name='Nanyang Technological University', country='Singapore')
        self.load(
            row('Duke University', 'United States', 57, kind='private'),
            row('National University of Singapore (NUS)', 'Singapore', 8),
            row('Nanyang Technological University, Singapore (NTU Singapore)', 'Singapore', 15),
        )
        self.assertEqual(University.objects.count(), 3)
        duke.refresh_from_db()
        self.assertEqual((duke.name, duke.country, duke.sat_min, duke.net_price_usd, duke.ranking), ('Duke University', 'USA', 1500, 26000, 57))
        self.assertEqual(University.objects.get(pk=nus.pk).ranking, 8)
        self.assertEqual(University.objects.get(pk=ntu.pk).ranking, 15)

    def test_running_again_adds_and_changes_nothing(self):
        rows = [row('Imperial College London', 'United Kingdom', 2)]
        self.load(*rows)
        output = self.load(*rows)
        self.assertEqual(University.objects.count(), 1)
        self.assertIn('Added 0 universities and updated QS data for 0', output)

    def test_scores_update_without_changing_admissions_and_are_idempotent(self):
        university = University.objects.create(name='Imperial College London', country='United Kingdom', ranking=2, sat_min=1450, net_price_usd=25000)
        record = row(university.name, university.country, 2)
        record['qs_data'] = {'year': 2027, 'size': 'L', 'overall_score': None, 'indicators': {'AR': {'score': 0, 'rank': '701+'}}}
        self.load(record)
        university.refresh_from_db()
        self.assertEqual(university.qs_data, record['qs_data'])
        self.assertEqual((university.sat_min, university.net_price_usd), (1450, 25000))
        self.assertIsNone(university.acceptance_rate)
        saved_at = university.updated_at
        self.assertIn('updated QS data for 0', self.load(record))
        university.refresh_from_db()
        self.assertEqual(university.updated_at, saved_at)
        # An older snapshot containing only ranks must not erase published scores.
        self.load(row(university.name, university.country, 2))
        university.refresh_from_db()
        self.assertEqual(university.qs_data, record['qs_data'])

    def test_curated_catalogue_loaded_afterwards_does_not_duplicate(self):
        self.load(
            row('Massachusetts Institute of Technology (MIT)', 'United States', 1, kind='private'),
            row('University of Michigan-Ann Arbor', 'United States', 44),
        )
        call_command('load_university_catalog', stdout=StringIO())
        self.assertEqual(University.objects.filter(name__startswith='Massachusetts Institute of Technology').count(), 1)
        self.assertEqual(University.objects.filter(name__startswith='University of Michigan').count(), 1)
        self.assertEqual(University.objects.get(name='Massachusetts Institute of Technology').ranking, 1)

    def test_shipped_snapshot_loads_every_university_once(self):
        rows = json.loads(DATA_FILE.read_text(encoding='utf-8'))['universities']
        call_command('load_qs_rankings', stdout=StringIO())
        self.assertEqual(University.objects.count(), len(rows))
        self.assertGreater(University.objects.values('country').distinct().count(), 100)
        imperial = University.objects.get(name='Imperial College London')
        self.assertEqual(imperial.qs_data['overall_score'], 99.2)
        self.assertEqual(imperial.qs_data['indicators']['SUS'], {'score': 98.0, 'rank': '7='})
        self.assertEqual(len(imperial.qs_data['indicators']), 9)
        self.assertIsNone(University.objects.get(name='Zarqa University (ZU)').qs_data['overall_score'])


class WorldwideCollegeResearchTests(RoleIsolationBase):
    def test_catalogue_api_exposes_qs_scores_separately_from_admission_data(self):
        data = {'year': 2027, 'overall_score': 99.2, 'size': 'L', 'indicators': {'FSR': {'score': 98.9, 'rank': '44'}}}
        university = University.objects.create(name='Imperial College London', country='United Kingdom', qs_data=data)
        self.client.force_authenticate(self.student_a_user)
        response = self.client.get(f'/api/universities/{university.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['qs_data'], data)
        self.assertIsNone(response.data['acceptance_rate'])
        self.assertEqual(response.data['student_faculty_ratio'], '')

    def research_as_student(self, countries):
        profile = {
            'gpa': '4.70', 'sat_score': 1450, 'ielts_score': '7.5', 'target_major': 'Computer Science',
            'target_countries': countries, 'budget_usd': 30000, 'scholarship_needed': False,
        }
        for field, value in profile.items():
            setattr(self.student_a, field, value)
        self.student_a.save()
        self.client.force_authenticate(self.student_a_user)
        response = self.client.get('/api/college-research/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data['recommendations']

    def test_research_ranks_universities_outside_the_first_four_markets(self):
        oxford = University.objects.create(name='University of Oxford', country='United Kingdom', ranking=4, popular_majors='Computer Science')
        University.objects.create(name='Market University', country='Canada', popular_majors='History')
        top = self.research_as_student('UK')[0]
        self.assertEqual(top['university']['id'], oxford.id)
        self.assertIn('United Kingdom is one of your target countries', top['reasons'])
        # Without an acceptance rate or SAT range the band is unknown, not "target".
        self.assertIsNone(top['admission_band'])

    def test_band_still_comes_from_admission_data(self):
        University.objects.create(name='Selective University', country='United Kingdom', acceptance_rate='9.00')
        University.objects.create(name='Open University', country='United Kingdom', acceptance_rate='60.00')
        bands = {item['university']['name']: item['admission_band'] for item in self.research_as_student('UK')}
        self.assertEqual(bands, {'Selective University': 'reach', 'Open University': 'safety'})

    def test_onboarding_country_codes_match_catalogue_spellings(self):
        University.objects.create(name='Spelling University', country='United States of America')
        reasons = self.research_as_student('US, Turkey')[0]['reasons']
        self.assertIn('United States of America is one of your target countries', reasons)

    def test_every_university_gets_a_score_while_only_the_best_carry_details(self):
        University.objects.bulk_create(University(name=f'Scored University {index}', country='Germany') for index in range(60))
        self.research_as_student('UK')
        data = self.client.get('/api/college-research/').data
        self.assertEqual(len(data['recommendations']), 50)
        self.assertEqual(len(data['scores']), 60)
        top = data['recommendations'][0]
        self.assertEqual(data['scores'][top['university']['id']], [top['match_score'], top['admission_band']])

    def test_university_catalogue_serves_large_pages(self):
        University.objects.bulk_create(University(name=f'Catalogue University {index}', country='Germany') for index in range(150))
        self.client.force_authenticate(self.student_a_user)
        response = self.client.get('/api/universities/?page_size=1000')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 150)
        self.assertIsNone(response.data['next'])
