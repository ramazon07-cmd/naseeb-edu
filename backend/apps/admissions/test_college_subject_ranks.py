"""Subject ranks in College Search (the ``subject`` param) and on the university page (``subjects``)."""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.admissions.models import University, UniversitySubjectRank
from apps.admissions.test_college_search import URL, CollegeSearchFixture

CS = 'COM02'


def rank(university, code, number, label='', score=None, year=2026):
    return UniversitySubjectRank.objects.create(
        university=university, subject_code=code, rank=number, rank_label=label, score=score, year=year,
    )


class SubjectSearchTests(CollegeSearchFixture, APITestCase):
    def setUp(self):
        super().setUp()
        rank(self.state, CS, 201, '201-250')
        rank(self.mit, CS, 1, '', 98.5)
        rank(self.oxford, CS, 4, '=4', 93.0)
        rank(self.mit, 'LAW01', 40)
        # A previous year never counts once a newer one is loaded.
        rank(self.tashkent, CS, 2, year=2025)

    def by_name(self, query):
        return {row['name']: row for row in self.search(query)['results']}

    def test_rows_carry_the_rank_in_the_selected_subject_and_unranked_ones_none(self):
        rows = self.by_name(f'subject={CS}&page_size=50')
        self.assertEqual(rows[self.mit.name]['subject_rank'], {'code': CS, 'rank': 1, 'label': '', 'score': 98.5, 'year': 2026, 'values': [None, None, None, None, None]})
        self.assertEqual(rows[self.state.name]['subject_rank']['label'], '201-250')
        self.assertEqual(rows[self.oxford.name]['subject_rank']['label'], '=4')
        self.assertIsNone(rows[self.tashkent.name]['subject_rank'])
        self.assertIsNone(rows[self.unranked.name]['subject_rank'])

    def test_rows_carry_the_subjects_indicator_scores_in_the_order_of_its_columns(self):
        UniversitySubjectRank.objects.filter(university=self.mit, subject_code='ARC01').delete()
        rank(self.mit, 'ARC01', 1, '', 99.0)
        rank(self.oxford, 'ARC01', 2, '', 95.5)
        UniversitySubjectRank.objects.filter(subject_code='ARC01', university=self.mit).update(
            academic_score='98.7', employer_score='90.1', citations_score='80.0', h_index_score='70.5')
        data = self.search('subject=ARC01&subject_only=true&sort=subject&page_size=50')
        # Archaeology is scored by academic and employer reputation, citations and H-index (no IRN).
        self.assertEqual(data['subject']['code'], 'ARC01')
        self.assertEqual([item['key'] for item in data['subject']['indicators']], ['academic', 'employer', 'citations', 'h_index'])
        self.assertEqual(data['results'][0]['subject_rank']['values'], [98.7, 90.1, 80.0, 70.5])
        self.assertEqual(data['results'][1]['subject_rank']['values'], [None, None, None, None])

    def test_the_answer_names_the_score_columns_only_when_a_subject_is_asked_for(self):
        self.assertNotIn('subject', self.search())
        self.assertEqual(self.search(f'subject={CS}')['subject']['year'], 2026)

    def test_a_tie_in_a_published_range_goes_to_the_better_subject_score_and_unranked_stay_last(self):
        rank(self.mit, 'MAT01', 201, '201-250', 70.0)
        rank(self.oxford, 'MAT01', 201, '201-250', 80.0)
        names = self.names('subject=MAT01&sort=subject&page_size=50')
        self.assertEqual(names[:2], [self.oxford.name, self.mit.name])

    def test_rows_have_no_subject_rank_key_without_a_subject(self):
        self.assertNotIn('subject_rank', self.search()['results'][0])

    def test_best_in_subject_sorts_by_rank_with_unranked_last(self):
        names = self.names(f'subject={CS}&sort=subject&page_size=50')
        self.assertEqual(names[:3], [self.mit.name, self.oxford.name, self.state.name])
        self.assertEqual(set(names[3:]), {self.tashkent.name, self.unranked.name})

    def test_only_ranked_keeps_the_universities_ranked_in_the_subject(self):
        self.assertEqual(self.names(f'subject={CS}&subject_only=true&sort=subject&page_size=50'), [self.mit.name, self.oxford.name, self.state.name])
        self.assertEqual(self.search(f'subject={CS}&subject_only=true')['count'], 3)
        self.assertEqual(self.search(f'subject={CS}')['count'], 5)
        self.assertEqual(self.names('subject=LAW01&subject_only=true'), [self.mit.name])

    def test_subject_filter_combines_with_other_filters_and_fit_sort(self):
        self.ready_profile()
        self.assertEqual(self.names(f'subject={CS}&subject_only=true&country=USA&sort=subject'), [self.mit.name, self.state.name])
        fit = self.search(f'subject={CS}&subject_only=true&sort=fit&page_size=50')
        self.assertEqual({row['name'] for row in fit['results']}, {self.mit.name, self.oxford.name, self.state.name})
        self.assertTrue(all(row['subject_rank'] and row['fit'] for row in fit['results']))
        self.assertFitOrder(fit['results'])

    def test_unknown_subject_and_sorting_without_one_are_refused(self):
        self.assertEqual(self.client.get(f'{URL}?subject=NOPE').status_code, 400)
        refused = self.client.get(f'{URL}?sort=subject')
        self.assertEqual(refused.status_code, 400)
        self.assertIn('sort', refused.data)

    def test_a_subject_nobody_is_ranked_in_still_answers(self):
        UniversitySubjectRank.objects.all().delete()
        self.assertEqual(self.search(f'subject={CS}&sort=subject')['count'], 5)
        self.assertEqual(self.search(f'subject={CS}&subject_only=true')['count'], 0)

    def test_the_research_answer_names_the_subjects_of_the_major(self):
        self.ready_profile()
        response = self.client.get('/api/college-research/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['subjects'][0], CS)

    def test_queries_do_not_grow_with_the_page_size(self):
        University.objects.bulk_create(University(name=f'Filler {index:02}', country='Germany') for index in range(60))
        for university in University.objects.filter(name__startswith='Filler'):
            rank(university, CS, 300 + university.pk)

        def count(size):
            with CaptureQueriesContext(connection) as queries:
                self.search(f'subject={CS}&subject_only=true&sort=subject&page_size={size}')
            return len(queries)

        self.assertEqual(count(10), count(50))


class UniversitySubjectsTests(CollegeSearchFixture, APITestCase):
    def setUp(self):
        super().setUp()
        for code, number, score in (('LAW01', 7, 97.0), ('PHI01', 1, 100.0), (CS, 22, 90.0), ('ACC01', 11, 94.0), ('AREA_ENG', 30, 80.0)):
            rank(self.mit, code, number, '', score)
        rank(self.mit, 'MAT01', 3, year=2025)

    def detail(self, university=None):
        response = self.client.get(f'/api/universities/{(university or self.mit).pk}/')
        self.assertEqual(response.status_code, 200)
        return response.data['subjects']

    def test_the_students_major_comes_first_then_the_best_ranks_and_areas_last(self):
        self.ready_profile(target_major='Computer Science')
        subjects = self.detail()
        self.assertEqual(subjects['year'], 2026)
        self.assertEqual([item['code'] for item in subjects['items']], [CS, 'PHI01', 'LAW01', 'ACC01', 'AREA_ENG'])
        self.assertEqual([item['mine'] for item in subjects['items']], [True, False, False, False, False])
        first = subjects['items'][0]
        self.assertEqual((first['name'], first['area'], first['rank'], first['score']), ('Computer Science & Information Systems', 'AREA_ENG', 22, 90.0))
        self.assertTrue(subjects['items'][-1]['is_area'])

    def test_each_major_subject_is_pinned_in_the_order_the_student_wrote_them(self):
        self.ready_profile(target_major='Law, Computer Science')
        codes = [item['code'] for item in self.detail()['items']]
        self.assertEqual(codes[:2], ['LAW01', CS])

    def test_without_a_mapped_major_the_order_is_by_rank(self):
        self.ready_profile(target_major='Underwater basket weaving')
        items = self.detail()['items']
        self.assertEqual([item['code'] for item in items], ['PHI01', 'LAW01', 'ACC01', CS, 'AREA_ENG'])
        self.assertFalse(any(item['mine'] for item in items))

    def test_a_university_without_ranks_has_an_empty_list(self):
        self.assertEqual(self.detail(self.state), {'year': 2026, 'items': []})

    def test_the_list_endpoint_stays_slim(self):
        response = self.client.get('/api/universities/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('subjects', response.data['results'][0])

    def test_detail_queries_do_not_grow_with_the_number_of_ranks(self):
        def count(university):
            with CaptureQueriesContext(connection) as queries:
                self.detail(university)
            return len(queries)

        few = count(self.state)
        for code in ('ART01', 'BIO01', 'CHE01', 'ECO01', 'EDU01', 'HIS01', 'MED01'):
            rank(self.state, code, 50)
        self.assertEqual(count(self.state), few)
