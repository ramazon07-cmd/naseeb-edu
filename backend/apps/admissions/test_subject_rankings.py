"""The Subject rankings view's API: one page of one subject, best rank first."""
from decimal import Decimal

from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.admissions.catalog_cache import bump_version
from apps.admissions.models import University, UniversitySubjectRank
from apps.admissions.test_audit_base import AuditBaseMixin
from apps.admissions.subjects import SUBJECT_WEIGHTS, subject_indicators

URL = '/api/subject-rankings/'
CS = 'COM02'
ART = 'ART01'


class SubjectRankingFixture(AuditBaseMixin):
    def setUp(self):
        super().setUp()
        cache.clear()
        bump_version()
        self.client.force_authenticate(self.student_user)
        make = University.objects.create
        self.mit = make(name='Massachusetts Institute of Technology', country='United States', city='Cambridge', qs_data={'region': 'Americas'})
        self.oxford = make(name='University of Oxford', country='United Kingdom', city='Oxford', qs_data={'region': 'Europe'})
        self.state = make(name='Ohio State University', country='USA', city='Columbus', qs_data={'region': 'Americas'})
        self.tashkent = make(name='Westminster International University in Tashkent', country='Uzbekistan', city='Tashkent', qs_data={'region': 'Asia'})
        self.peking = make(name='Peking University', country='China (Mainland)', city='Beijing', qs_data={'region': 'Asia'})
        self.unranked = make(name='Quiet College', country='Uzbekistan')
        self.rank(self.mit, CS, 1, score=94.9, scores=(94.7, 97.3, 93.6, 94.0, 88.2))
        self.rank(self.oxford, CS, 4, '=4', 89.8, (85.0, 97.0, 94.2, 86.3, 82.3))
        # Two members of one published range tie on its lower bound: the better score goes first.
        self.rank(self.tashkent, CS, 201, '201-250', 40.0, (30.0, 40.5, 50.0, 60.0, 70.0))
        self.rank(self.peking, CS, 201, '201-250', 45.5, (35.0, 45.5, 55.0, 65.0, 75.0))
        self.rank(self.state, CS, 150, '', None, (50.0, 60.0, 70.0, 80.0, 90.0))
        self.rank(self.mit, ART, 7, '', 70.0, (90.0, 80.0, None, None, None))
        # A previous year never counts once a newer one is loaded.
        self.rank(self.unranked, CS, 2, year=2025)

    def rank(self, university, code, number, label='', score=None, scores=(None,) * 5, year=2026):
        academic, employer, citations, h_index, irn = (None if value is None else Decimal(str(value)) for value in scores)
        return UniversitySubjectRank.objects.create(
            university=university, subject_code=code, rank=number, rank_label=label, score=score, year=year,
            academic_score=academic, employer_score=employer, citations_score=citations, h_index_score=h_index, irn_score=irn,
        )

    def page(self, query=''):
        response = self.client.get(f'{URL}?{query}')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        return response.data

    def names(self, query=''):
        return [row['name'] for row in self.page(query)['results']]


class SubjectRankingTests(SubjectRankingFixture, APITestCase):
    def test_rows_are_ordered_by_rank_with_a_range_tied_on_its_lower_bound(self):
        self.assertEqual(self.names(f'subject={CS}&limit=50'), [
            self.mit.name, self.oxford.name, self.state.name, self.peking.name, self.tashkent.name,
        ])

    def test_a_row_carries_the_rank_as_published_the_scores_and_nothing_else(self):
        rows = {row['name']: row for row in self.page(f'subject={CS}&limit=50')['results']}
        self.assertEqual(rows[self.mit.name], {
            'id': self.mit.pk, 'name': self.mit.name, 'city': 'Cambridge', 'country': 'United States', 'rank': 1, 'label': '',
            'score': 94.9, 'values': [94.7, 97.3, 93.6, 94.0, 88.2],
        })
        self.assertEqual((rows[self.oxford.name]['rank'], rows[self.oxford.name]['label']), (4, '=4'))
        self.assertEqual((rows[self.peking.name]['rank'], rows[self.peking.name]['label']), (201, '201-250'))
        self.assertIsNone(rows[self.state.name]['score'])

    def test_the_indicator_columns_follow_the_subject(self):
        cs = self.page(f'subject={CS}')
        self.assertEqual(cs['indicators'], [
            {'key': 'academic', 'weight': 0.4}, {'key': 'employer', 'weight': 0.3}, {'key': 'citations', 'weight': 0.125},
            {'key': 'h_index', 'weight': 0.125}, {'key': 'irn', 'weight': 0.05},
        ])
        art = self.page(f'subject={ART}')
        self.assertEqual([item['key'] for item in art['indicators']], ['academic', 'employer'])
        self.assertEqual(art['results'][0]['values'], [90.0, 80.0])
        self.assertEqual((cs['subject'], cs['year'], cs['source']), (CS, 2026, 'QS World University Rankings by Subject'))

    def test_every_subject_lists_only_the_indicators_it_has_weights_for(self):
        for code, weights in SUBJECT_WEIGHTS.items():
            self.assertEqual([key for key, _ in subject_indicators(code)], [
                key for key, weight in zip(('academic', 'employer', 'citations', 'h_index', 'irn'), weights) if weight
            ])

    def test_paging_by_limit_and_offset_never_repeats_or_skips_a_row(self):
        first = self.page(f'subject={CS}&limit=10')
        self.assertEqual((first['count'], len(first['results']), first['next_offset']), (5, 5, None))
        UniversitySubjectRank.objects.bulk_create(
            UniversitySubjectRank(
                university=University.objects.create(name=f'Filler {index:02}', country='Germany'),
                subject_code=CS, rank=300 + index, year=2026,
            ) for index in range(30)
        )
        bump_version()
        seen, offset, pages = [], 0, 0
        while offset is not None:
            page = self.page(f'subject={CS}&limit=10&offset={offset}')
            self.assertEqual((page['count'], page['offset']), (35, offset))
            seen += [row['id'] for row in page['results']]
            offset, pages = page['next_offset'], pages + 1
        self.assertEqual((len(seen), len(set(seen)), pages), (35, 35, 4))
        self.assertEqual(len(self.page(f'subject={CS}&limit=25')['results']), 25)
        self.assertEqual(len(self.page(f'subject={CS}&limit=50')['results']), 35)
        self.assertEqual(self.page(f'subject={CS}&limit=25&offset=25')['next_offset'], None)

    def test_only_the_offered_page_sizes_and_known_subjects_and_parameters(self):
        for query in (f'subject={CS}&limit=100', f'subject={CS}&limit=7', 'subject=NOPE', '', f'subject={CS}&offset=-1', f'subject={CS}&page=2', f'subject={CS}&sort=score'):
            self.assertEqual(self.client.get(f'{URL}?{query}').status_code, 400, query)

    def test_a_subject_nobody_is_ranked_in_is_an_empty_page(self):
        page = self.page('subject=LAW01')
        self.assertEqual((page['count'], page['results'], page['next_offset'], page['year']), (0, [], None, None))

    def test_filters_search_country_and_qs_region(self):
        self.assertEqual(self.names(f'subject={CS}&country=USA'), [self.mit.name, self.state.name])
        self.assertEqual(self.names(f'subject={CS}&country=China'), [self.peking.name])
        self.assertEqual(self.names(f'subject={CS}&region=Asia'), [self.peking.name, self.tashkent.name])
        self.assertEqual(self.names(f'subject={CS}&search=oxford'), [self.oxford.name])
        self.assertEqual(self.names(f'subject={CS}&search=beijing'), [self.peking.name])
        self.assertEqual(self.page(f'subject={CS}&region=Americas&country=USA')['count'], 2)
        self.assertEqual(self.names(f'subject={CS}&search=quiet'), [])

    def test_the_view_needs_a_signed_in_user(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'{URL}?subject={CS}').status_code, 401)

    def test_a_row_carries_only_what_the_table_shows(self):
        row = self.page(f'subject={CS}')['results'][0]
        self.assertEqual(set(row), {'id', 'name', 'city', 'country', 'rank', 'label', 'score', 'values'})


class SubjectRankingCostTests(SubjectRankingFixture, APITestCase):
    def setUp(self):
        super().setUp()
        UniversitySubjectRank.objects.bulk_create(
            UniversitySubjectRank(
                university=University.objects.create(name=f'Filler {index:02}', country='Germany', qs_data={'region': 'Europe'}),
                subject_code=CS, rank=300 + index, year=2026, score=50 + index / 10, academic_score=Decimal('50.5'),
            ) for index in range(60)
        )
        bump_version()

    def queries(self, query):
        cache.clear()
        bump_version()
        with CaptureQueriesContext(connection) as captured:
            self.page(query)
        return [item['sql'] for item in captured if 'universitysubjectrank' in item['sql']]

    def test_a_page_costs_the_same_two_queries_at_every_size_and_filter(self):
        counts = {query: len(self.queries(query)) for query in (
            f'subject={CS}&limit=10', f'subject={CS}&limit=25', f'subject={CS}&limit=50', f'subject={CS}&limit=50&offset=10',
            f'subject={CS}&limit=25&search=filler&country=Germany&region=Europe',
        )}
        self.assertEqual(set(counts.values()), {2}, counts)

    def test_the_newest_year_is_one_subquery_not_one_more_query(self):
        sql = ' '.join(self.queries(f'subject={CS}&limit=10')).upper()
        self.assertEqual(sql.count('MAX('), 0)
        self.assertIn('ORDER BY', sql)

    def test_the_newest_year_subquery_is_not_tied_to_each_candidate_row(self):
        # A correlated subquery compares U0.subject_code with the outer row's column and is re-run per row.
        for query in (f'subject={CS}&limit=10', f'subject={CS}&limit=10&search=filler&country=Germany'):
            subqueries = [sql for sql in self.queries(query) if 'U0.' in sql]
            self.assertTrue(subqueries)
            for sql in subqueries:
                self.assertIn(f'U0."subject_code" = \'{CS}\'', sql)
                self.assertNotIn('U0."subject_code" = ("admissions_universitysubjectrank"', sql)

    def test_a_repeated_page_comes_from_the_cache_without_touching_the_ranks(self):
        first = self.page(f'subject={CS}&limit=25')
        with CaptureQueriesContext(connection) as captured:
            second = self.page(f'subject={CS}&limit=25')
        self.assertEqual(first, second)
        self.assertEqual([item for item in captured if 'universitysubjectrank' in item['sql']], [])
        # Another page or filter is another cache entry.
        with CaptureQueriesContext(connection) as captured:
            self.page(f'subject={CS}&limit=25&offset=25')
        self.assertTrue([item for item in captured if 'universitysubjectrank' in item['sql']])

    def test_loading_new_rankings_replaces_the_cached_pages(self):
        before = self.page(f'subject={CS}&limit=10')
        UniversitySubjectRank.objects.filter(university=self.oxford, subject_code=CS).update(rank=1, rank_label='')
        self.assertEqual(self.page(f'subject={CS}&limit=10'), before)  # still cached
        bump_version()
        after = self.page(f'subject={CS}&limit=10')
        self.assertNotEqual(after, before)
        self.assertEqual(after['results'][0]['rank'], 1)

    def test_a_25_row_page_is_small(self):
        import json

        size = len(json.dumps(self.page(f'subject={CS}&limit=25')))
        self.assertLess(size, 6000, size)
