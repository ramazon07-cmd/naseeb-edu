"""College Search pages: small fixed page sizes, server-side filters, sorting, fit and facets."""
from datetime import date
from unittest import mock

from rest_framework.test import APITestCase

from apps.admissions import college_search
from apps.admissions.models import Honor, University, UniversityProgram
from apps.admissions.test_audit_base import AuditBaseMixin

URL = '/api/college-search/'


class CollegeSearchFixture(AuditBaseMixin):
    def setUp(self):
        super().setUp()
        make = University.objects.create
        self.mit = make(
            name='Massachusetts Institute of Technology', country='United States', city='Cambridge', ranking=1,
            acceptance_rate='4.00', sat_min=1520, sat_max=1580, net_price_usd=20000, offers_need_based_aid=True,
            meets_full_need=True, institution_type='private', application_deadline=date(2027, 1, 1),
            qs_data={'region': 'Americas', 'size': 'M', 'overall_score': 100.0},
        )
        self.state = make(
            name='Ohio State University', country='USA', city='Columbus', ranking=150, acceptance_rate='53.00',
            sat_min=1200, sat_max=1400, net_price_usd=26000, offers_merit_aid=True, institution_type='public',
            test_optional=True, application_deadline=date(2026, 11, 1), qs_data={'region': 'Americas', 'size': 'XL'},
        )
        self.oxford = make(
            name='University of Oxford', country='United Kingdom', city='Oxford', ranking=4,
            institution_type='public', qs_data={'region': 'Europe', 'size': 'L'},
        )
        self.tashkent = make(
            name='Westminster International University in Tashkent', country='Uzbekistan', city='Tashkent',
            net_price_usd=4000, offers_international_aid=True, test_optional=True,
            qs_data={'region': 'Asia', 'size': 'S'},
        )
        self.unranked = make(name='Quiet College', country='Uzbekistan', city='Samarkand', acceptance_rate='80.00')
        UniversityProgram.objects.create(university=self.state, name='BSc Computer Science', canonical_major='Computer Science')
        UniversityProgram.objects.create(
            university=self.state, name='Closed Program', canonical_major='Computer Science', is_active=False,
        )
        self.client.force_authenticate(self.student_user)

    def ready_profile(self, **answers):
        values = {
            'gpa': '3.80', 'gpa_scale': 4, 'sat_score': 1450, 'ielts_score': '7.5', 'target_major': 'Computer Science',
            'target_countries': 'US', 'budget_usd': 30000, 'scholarship_needed': True, **answers,
        }
        for field, value in values.items():
            setattr(self.student, field, value)
        self.student.save()

    def search(self, query=''):
        response = self.client.get(f'{URL}?{query}')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        return response.data

    def names(self, query=''):
        return [row['name'] for row in self.search(query)['results']]


class PagingTests(CollegeSearchFixture, APITestCase):
    def test_pages_hold_10_by_default_and_only_the_offered_sizes(self):
        University.objects.bulk_create(University(name=f'Filler {index:02}', country='Germany') for index in range(30))
        first = self.search()
        self.assertEqual((len(first['results']), first['count'], first['page_size'], first['next']), (10, 35, 10, 2))
        self.assertEqual(len(self.search('page_size=25')['results']), 25)
        self.assertEqual(len(self.search('page_size=50')['results']), 35)
        last = self.search('page=4')
        self.assertEqual((len(last['results']), last['next']), (5, None))
        seen = [row['id'] for page in range(1, 5) for row in self.search(f'page={page}')['results']]
        self.assertEqual(len(seen), len(set(seen)))
        for size in ('5', '200', '1000', 'all'):
            self.assertEqual(self.client.get(f'{URL}?page_size={size}').status_code, 400, size)

    def test_rows_are_slim_and_list_only_open_programs(self):
        row = next(row for row in self.search('search=ohio')['results'])
        self.assertNotIn('notes', row)
        self.assertNotIn('catalog_source_url', row)
        self.assertEqual([program['name'] for program in row['programs']], ['BSc Computer Science'])

    def test_unknown_values_are_rejected(self):
        for query in ('sort=random', 'price=10', 'aid=free_lunch', 'bands=dream', 'ids=one', 'test_optional=maybe', 'page=0'):
            self.assertEqual(self.client.get(f'{URL}?{query}').status_code, 400, query)


class FilterAndSortTests(CollegeSearchFixture, APITestCase):
    def test_search_matches_name_city_and_country_and_every_term(self):
        self.assertEqual(self.names('search=tashkent'), ['Westminster International University in Tashkent'])
        self.assertEqual(set(self.names('search=uzbekistan')), {'Westminster International University in Tashkent', 'Quiet College'})
        self.assertEqual(self.names('search=oxford university'), ['University of Oxford'])

    def test_country_joins_the_spellings_of_one_market(self):
        self.assertEqual(set(self.names('country=United%20States')), {self.mit.name, self.state.name})
        self.assertEqual(self.names('country=United%20Kingdom'), [self.oxford.name])

    def test_price_aid_testing_and_type_filters(self):
        self.assertEqual(set(self.names('price=25000')), {self.mit.name, self.tashkent.name})
        self.ready_profile(budget_usd=5000)
        self.assertEqual(self.names('price=budget'), [self.tashkent.name])
        self.assertEqual(self.names('aid=offers_need_based_aid,meets_full_need'), [self.mit.name])
        self.assertEqual(set(self.names('test_optional=true')), {self.state.name, self.tashkent.name})
        self.assertEqual(set(self.names('public=true')), {self.state.name, self.oxford.name})
        self.assertEqual(self.names('region=Europe'), [self.oxford.name])
        self.assertEqual(self.names('size=XL&region=Americas'), [self.state.name])

    def test_sat_in_range_means_a_met_minimum_or_test_optional_without_one(self):
        self.ready_profile(sat_score=1300)
        self.assertEqual(set(self.names('sat_fit=true')), {self.state.name, self.tashkent.name})

    def test_sorts_put_missing_values_last(self):
        # Unranked rows follow, by name.
        self.assertEqual(self.names('sort=ranking'), [self.mit.name, self.oxford.name, self.state.name, self.unranked.name, self.tashkent.name])
        self.assertEqual(self.names('sort=price')[:3], [self.tashkent.name, self.mit.name, self.state.name])
        self.assertEqual(self.names('sort=deadline')[:2], [self.state.name, self.mit.name])
        self.assertEqual(self.names('sort=acceptance')[:3], [self.unranked.name, self.state.name, self.mit.name])


class FitTests(CollegeSearchFixture, APITestCase):
    def test_without_a_ready_profile_rows_have_no_fit_and_fit_sort_keeps_the_ranking(self):
        data = self.search('sort=fit')
        self.assertTrue(all('fit' not in row for row in data['results']))
        self.assertEqual(data['results'][0]['name'], self.mit.name)

    def test_each_row_carries_its_fit_and_fit_sort_ranks_by_score(self):
        self.ready_profile()
        rows = self.search('sort=fit')['results']
        scores = [row['fit']['match_score'] for row in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))
        state = next(row for row in rows if row['id'] == self.state.id)
        self.assertIn('Computer Science matches an available field of study', state['fit']['reasons'])
        self.assertEqual(state['fit']['admission_band'], 'safety')

    def test_bands_filter_on_the_students_fit(self):
        self.ready_profile()
        self.assertEqual(self.names('bands=reach'), [self.mit.name])
        self.assertEqual(set(self.names('bands=safety')), {self.state.name, self.unranked.name})
        # Every box unticked shows nothing; no bands parameter shows everything.
        self.assertEqual(self.search('bands=')['count'], 0)
        self.assertEqual(self.search()['count'], 5)

    def test_the_catalogue_is_scored_once_per_profile(self):
        self.ready_profile()
        with mock.patch.object(college_search, 'score_university', wraps=college_search.score_university) as scorer:
            self.search('sort=fit')
            first = scorer.call_count
            self.search('sort=fit&page_size=25')
            self.search('bands=reach')
        self.assertEqual(first, 5 + 5)  # the whole catalogue once, then the rows on the page
        self.assertEqual(scorer.call_count, first + 5 + 1)
        Honor.objects.create(student=self.student, title='New olympiad medal')
        with mock.patch.object(college_search, 'score_university', wraps=college_search.score_university) as scorer:
            self.search('sort=fit')
        self.assertEqual(scorer.call_count, 10, 'new evidence changes the profile, so the scores are rebuilt')

    def test_query_count_does_not_grow_with_the_page(self):
        University.objects.bulk_create(University(name=f'Filler {index:03}', country='Germany') for index in range(120))
        self.ready_profile()
        self.search('sort=fit&facets=true')
        small, _ = self.get_counted(f'{URL}?sort=fit&page_size=10')
        large, _ = self.get_counted(f'{URL}?sort=fit&page_size=100')
        self.assertEqual(small, large)


class FacetAndIdsTests(CollegeSearchFixture, APITestCase):
    def test_facets_count_the_whole_catalogue_once(self):
        self.ready_profile(sat_score=1300)
        facets = self.search('facets=true&search=oxford')['facets']
        self.assertEqual(facets['countries'], {'United States': 2, 'United Kingdom': 1, 'Uzbekistan': 2})
        self.assertEqual(facets['aid'], {'offers_need_based_aid': 1, 'offers_merit_aid': 1, 'offers_international_aid': 1, 'meets_full_need': 1})
        self.assertEqual((facets['test_optional'], facets['public'], facets['sat_fit']), (2, 2, 2))
        self.assertEqual(facets['qs']['region'], {'Americas': 2, 'Europe': 1, 'Asia': 1})
        self.assertEqual(facets['bands'], {'reach': 1, 'target': 0, 'safety': 2})
        self.assertNotIn('facets', self.search('page=1'))

    def test_ids_return_just_those_rows(self):
        self.ready_profile()
        data = self.search(f'ids={self.oxford.id},{self.state.id}')
        self.assertEqual([row['id'] for row in data['results']], [self.oxford.id, self.state.id])
        self.assertIn('fit', data['results'][0])
        too_many = ','.join(str(index) for index in range(1, 102))
        self.assertEqual(self.client.get(f'{URL}?ids={too_many}').status_code, 400)


class AccessTests(CollegeSearchFixture, APITestCase):
    def test_only_students_search(self):
        for user in (self.counselor, self.organization, self.teacher, self.parent, self.admin):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(URL).status_code, 403, user.role)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_students_find_universities_from_the_global_search(self):
        results = self.client.get('/api/search/?q=oxford').data['results']
        self.assertEqual([item['title'] for item in results['universities']], ['University of Oxford'])
        self.client.force_authenticate(self.counselor)
        self.assertNotIn('universities', self.client.get('/api/search/?q=oxford').data['results'])

    def test_the_catalogue_list_is_searched_and_paged_with_slim_rows(self):
        data = self.client.get('/api/universities/?search=oxford&page_size=1000').data
        self.assertEqual([row['name'] for row in data['results']], ['University of Oxford'])
        self.assertNotIn('notes', data['results'][0])
        detail = self.client.get(f'/api/universities/{self.oxford.id}/').data
        self.assertIn('notes', detail)
