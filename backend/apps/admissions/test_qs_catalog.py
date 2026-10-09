"""QS World University Rankings import and the worldwide college research it feeds."""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from .college_search import fit_context, fit_scores
from .management.commands.load_qs_rankings import DATA_FILE
from .models import University, UniversityProgram
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
        # A blank QS status is never stored as an invalid choice: it takes the model default.
        self.assertEqual(values('Status Unknown University'), ('', 951, '951-1000', University._meta.get_field('institution_type').default))

    def test_every_institution_type_written_is_a_valid_choice(self):
        self.load(row('Blank Type University', 'Jordan', 1001, kind=''), row('Odd Type University', 'Jordan', 1002, kind='state'))
        for university in University.objects.all():
            university.full_clean()
        self.assertEqual(set(University.objects.values_list('institution_type', flat=True)), {University.InstitutionType.PRIVATE})

    def test_duplicate_snapshot_rows_are_reported_not_silently_dropped(self):
        output = self.load(
            row('National University of Singapore (NUS)', 'Singapore', 8),
            row('National University of Singapore', 'Singapore', 9),
            row('Imperial College London', 'United Kingdom', 2),
        )
        self.assertEqual(University.objects.get(country='Singapore').ranking, 8)
        self.assertIn('Skipped 1 rows that match a university listed earlier in the snapshot: National University of Singapore (Singapore)', output)
        self.assertIn('Added 2 universities', output)

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
        self.assertFalse(University.objects.exclude(institution_type__in=University.InstitutionType.values).exists())


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
        response = self.client.get('/api/college-search/?sort=fit&page_size=100')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data['results']

    def test_research_ranks_universities_outside_the_first_four_markets(self):
        oxford = University.objects.create(name='University of Oxford', country='United Kingdom', ranking=4, popular_majors='Computer Science')
        University.objects.create(name='Market University', country='Canada', popular_majors='History')
        top = self.research_as_student('UK')[0]
        self.assertEqual(top['id'], oxford.id)
        self.assertIn('United Kingdom is one of your target countries', [reason['text'] for reason in top['fit']['reasons']])
        # Without an acceptance rate or SAT range the band is unknown, not "target".
        self.assertIsNone(top['fit']['admission_band'])

    def test_band_still_comes_from_admission_data(self):
        University.objects.create(name='Selective University', country='United Kingdom', acceptance_rate='9.00')
        University.objects.create(name='Open University', country='United Kingdom', acceptance_rate='60.00')
        bands = {item['name']: item['fit']['admission_band'] for item in self.research_as_student('UK')}
        self.assertEqual(bands, {'Selective University': 'reach', 'Open University': 'safety'})

    def test_onboarding_country_codes_match_catalogue_spellings(self):
        University.objects.create(name='Spelling University', country='United States of America')
        reasons = self.research_as_student('US, Turkey')[0]['fit']['reasons']
        self.assertIn('United States of America is one of your target countries', [reason['text'] for reason in reasons])

    def test_every_university_is_ranked_and_explained_on_its_page(self):
        University.objects.bulk_create(University(name=f'Scored University {index}', country='Germany') for index in range(60))
        rows = self.research_as_student('UK')
        self.assertEqual(len(rows), 60)
        self.assertTrue(all(row['fit']['reasons'] and 'academic' in row['fit']['score_breakdown'] for row in rows))
        scores = [row['fit']['match_score'] for row in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_every_university_is_scored_and_the_unrelated_ones_rank_last(self):
        target = University.objects.create(name='Target Country University', country='United Kingdom')
        with_data = University.objects.create(name='Data University', country='USA', sat_min=1300, sat_max=1500)
        priced = University.objects.create(name='Priced University', country='Japan', net_price_usd=9000)
        unrelated = University.objects.create(name='Unrelated University', country='Germany', ranking=1)
        rows = self.research_as_student('UK')
        scores = fit_scores(self.student_a, fit_context(self.student_a))
        self.assertEqual(set(scores), {target.id, with_data.id, priced.id, unrelated.id})
        # The map and the rows agree: what a row shows is what it is sorted and filtered by.
        self.assertEqual({row['id']: (row['fit']['match_score'], row['fit']['admission_band']) for row in rows}, scores)
        # Not a target country and no admissions data: last, despite the best rank.
        self.assertEqual(rows[-1]['id'], unrelated.id)

    def test_fit_sort_queries_do_not_grow_with_the_catalogue(self):
        def queries():
            with CaptureQueriesContext(connection) as captured:
                self.client.get('/api/college-search/?sort=fit')
            return len(captured)

        self.research_as_student('UK')
        University.objects.bulk_create(University(name=f'Small {index}', country='United Kingdom') for index in range(3))
        small = queries()
        University.objects.bulk_create(University(name=f'Large {index}', country='United Kingdom', popular_majors='History') for index in range(80))
        self.assertEqual(queries(), small)

    def test_missing_admissions_data_is_unknown_not_a_bonus(self):
        University.objects.create(name='Unknown University', country='United Kingdom', ranking=1)
        University.objects.create(
            name='Known University', country='United Kingdom', ranking=50,
            sat_min=1400, sat_max=1500, acceptance_rate='30.00', net_price_usd=20000,
        )
        University.objects.create(name='Optional University', country='United Kingdom', ranking=60, test_optional=True)
        results = {item['name']: item['fit'] for item in self.research_as_student('UK')}
        unknown, known = results['Unknown University'], results['Known University']
        # The same row with admissions data that fits ranks above the one without.
        self.assertGreater(known['match_score'], unknown['match_score'])
        self.assertNotIn('tests_optional', [reason['code'] for reason in unknown['reasons']])
        self.assertFalse([reason for reason in unknown['reasons'] if 'SAT' in reason['text']])
        self.assertIn('test_range_missing', [gap['code'] for gap in unknown['gaps']])
        self.assertEqual(unknown['score_breakdown']['academic'] - known['score_breakdown']['academic'], -22)
        self.assertIn('tests_optional', [reason['code'] for reason in results['Optional University']['reasons']])

    def test_qs_only_rows_do_not_outrank_curated_universities(self):
        University.objects.bulk_create(
            University(name=f'QS Only University {index}', country='United Kingdom', ranking=index + 1, popular_majors='Computer Science')
            for index in range(30)
        )
        # Only a partial fit: SAT a little under the range and the price above budget.
        curated = University.objects.create(
            name='Curated University', country='United Kingdom', ranking=900, popular_majors='Computer Science',
            sat_min=1480, sat_max=1560, acceptance_rate='40.00', net_price_usd=40000,
        )
        self.assertEqual(self.research_as_student('UK')[0]['id'], curated.id)

    def test_university_catalogue_pages_hold_at_most_100_rows(self):
        University.objects.bulk_create(University(name=f'Catalogue University {index}', country='Germany') for index in range(150))
        self.client.force_authenticate(self.student_a_user)
        response = self.client.get('/api/universities/?page_size=500')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 100)
        self.assertIsNotNone(response.data['next'])

    def test_catalogue_list_is_slim_and_the_detail_is_full(self):
        qs_data = {
            'year': 2027, 'previous_rank': '3', 'source_url': 'https://www.topuniversities.com/', 'region': 'Europe', 'status': 'Public',
            'overall_score': 99.2, 'indicators': {'AR': {'score': 99.6, 'rank': '7'}, 'FSR': {'score': 98.9, 'rank': '44'}},
        }
        university = University.objects.create(name='Imperial College London', country='United Kingdom', qs_data=qs_data, notes='Long notes')
        UniversityProgram.objects.create(university=university, name='BSc Computing', canonical_major='Computer Science')
        self.client.force_authenticate(self.student_a_user)
        row = self.client.get('/api/universities/').data['results'][0]
        # The pickers need no programs; College Search adds the names it uses.
        for field in ('notes', 'offers_merit_aid', 'programs'):
            self.assertNotIn(field, row)
        # Only the QS values the College Search table shows and filters by.
        self.assertEqual(row['qs_data'], {'region': 'Europe', 'status': 'Public', 'overall_score': 99.2, 'indicators': {'AR': {'score': 99.6}}})
        for field in ('name', 'country', 'ranking', 'sat_min', 'net_price_usd', 'application_deadline'):
            self.assertIn(field, row)
        detail = self.client.get(f'/api/universities/{university.pk}/').data
        self.assertEqual(detail['qs_data'], qs_data)
        self.assertEqual([program['canonical_major'] for program in detail['programs']], ['Computer Science'])
        self.assertEqual(detail['notes'], 'Long notes')
