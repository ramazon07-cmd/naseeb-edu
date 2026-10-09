"""College Search fit: international cost, every test a student can send, unknown bands and aid,
the evidence query, country aliases and the reason codes the frontend translates."""
import re
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.admissions import college_search
from apps.admissions.college_search import (
    IELTS_CONCORDANCE, evidence_counts, fit_context, has_aid_data, ielts_equivalent, score_university,
)
from apps.admissions.models import Honor, Project, University
from apps.admissions.test_college_search import URL, CollegeSearchFixture

FIT_REASONS_JS = Path(__file__).resolve().parents[3] / 'frontend' / 'src' / 'translations' / 'fitReasons.js'


def codes(fit, key):
    return [entry['code'] for entry in fit[key]]


class FitFixture(CollegeSearchFixture):
    def fit(self, university):
        return self.search(f'ids={university.id}')['results'][0]['fit']

    def certificates(self, *rows):
        self.student.application_profile = {**self.student.application_profile, 'certificates': [
            {'name': '', 'test_date': None, **row} for row in rows
        ]}
        self.student.save()


class InternationalCostTests(FitFixture, APITestCase):
    def test_us_rows_are_priced_at_the_international_cost_of_attendance(self):
        self.ready_profile(budget_usd=30000)
        mit = self.fit(self.mit)
        self.assertIn('cost_far_above_budget', codes(mit, 'gaps'))
        gap = next(entry for entry in mit['gaps'] if entry['code'] == 'cost_far_above_budget')
        self.assertEqual(gap['params'], {'cost': 85000, 'budget': 30000})
        self.assertTrue(gap['text'].startswith('Estimated cost of attendance for international students'))
        self.assertNotIn('after aid', gap['text'])
        # Outside the US a row keeps its own price.
        self.assertIn('cost_within_budget', codes(self.fit(self.tashkent), 'reasons'))
        self.assertEqual(self.names('price=budget'), [self.tashkent.name])

    def test_the_net_price_counts_only_where_international_students_get_aid(self):
        aided = University.objects.create(
            name='Aided College', country='United States', net_price_usd=18000, intl_cost_usd=70000,
            offers_international_aid=True, acceptance_rate='30.00',
        )
        unpriced = University.objects.create(name='Unpriced College', country='USA', net_price_usd=9000, acceptance_rate='30.00')
        self.ready_profile(budget_usd=20000)
        reason = next(entry for entry in self.fit(aided)['reasons'] if entry['code'] == 'net_after_aid_within_budget')
        self.assertEqual(reason['text'], 'Estimated net price after aid is within your budget')
        self.assertIn('cost_missing', codes(self.fit(unpriced), 'gaps'))
        self.assertEqual(set(self.names('price=budget')), {self.tashkent.name, aided.name})
        prices = self.names('sort=price')
        self.assertEqual(prices[:4], [self.tashkent.name, aided.name, self.state.name, self.mit.name])
        self.assertEqual(set(prices[4:]), {unpriced.name, self.oxford.name, self.unranked.name})

    def test_the_shipped_scorecard_puts_mit_stanford_and_georgia_tech_above_a_20k_budget(self):
        University.objects.filter(pk__in=[self.mit.pk, self.state.pk]).delete()
        call_command('load_qs_rankings', stdout=StringIO())
        call_command('load_college_scorecard', stdout=StringIO())
        names = ('Massachusetts Institute of Technology', 'Stanford University', 'Georgia Institute of Technology')
        universities = list(University.objects.filter(name__in=names, market=University.Market.US))
        self.assertEqual(len(universities), 3)
        self.assertEqual({item.name: item.intl_cost_usd for item in universities}, {
            'Massachusetts Institute of Technology': 85960, 'Stanford University': 92892, 'Georgia Institute of Technology': 52092,
        })
        self.ready_profile(budget_usd=20000)
        rows = self.search('ids=' + ','.join(str(item.id) for item in universities))['results']
        for row in rows:
            self.assertFalse([code for code in codes(row['fit'], 'reasons') if code.endswith('within_budget')], row['name'])
            self.assertIn('cost_far_above_budget', codes(row['fit'], 'gaps'), row['name'])
        within = set(self.names('price=budget&page_size=100&country=United%20States'))
        self.assertFalse(within & set(names))


class OtherTestsTests(FitFixture, APITestCase):
    def test_fit_does_not_need_sat_or_ielts(self):
        self.ready_profile(sat_score=None, ielts_score=None)
        research = self.client.get('/api/college-research/').data
        self.assertTrue(research['ready'])
        fit = self.fit(self.mit)
        self.assertEqual(codes(fit, 'gaps')[:2], ['test_score_missing', 'english_missing'])
        # Unknown, not zero and not a bonus: only the GPA counts in the academic part.
        self.assertEqual(fit['score_breakdown']['academic'], round(3.8 / 4 * 15))

    def test_missing_tests_take_the_missing_weight_path(self):
        self.ready_profile(sat_score=None, ielts_score=None)
        ctx = fit_context(self.student)
        university = University.objects.prefetch_related(college_search.eligible_programs()).get(pk=self.mit.pk)
        fit = score_university(university, ctx)
        breakdown = fit['score_breakdown']
        earned = sum(breakdown.values())
        missing = college_search.TEST_POINTS + college_search.ENGLISH_POINTS
        self.assertEqual(fit['match_score'], min(100, round(earned * 100 / (100 - missing) * (1 - missing / 200))))

    def test_act_is_scored_against_the_act_range(self):
        self.ready_profile(sat_score=None)
        self.certificates({'type': 'act', 'score': 35})
        fit = self.fit(self.mit)
        reason = next(entry for entry in fit['reasons'] if entry['code'] == 'act_in_range')
        self.assertEqual(reason['params'], {'score': 35, 'min': 34, 'max': 36})
        self.certificates({'type': 'act', 'score': 28}, {'type': 'act', 'score': 30})
        fit = self.fit(self.mit)
        self.assertIn('act_below_minimum', codes(fit, 'gaps'))
        self.assertEqual(fit['admission_band'], 'reach')

    def test_the_better_of_sat_and_act_counts(self):
        self.ready_profile(sat_score=1300)
        self.certificates({'type': 'act', 'score': 36})
        fit = self.fit(self.mit)
        self.assertIn('act_above_range', codes(fit, 'reasons'))
        self.assertNotIn('sat_below_minimum', codes(fit, 'gaps'))
        self.assertEqual(fit['score_breakdown']['academic'], round(3.8 / 4 * 15) + 25 + 8)

    def test_sat_not_required_and_test_optional_universities(self):
        self.ready_profile(sat_score=None, sat_status='not_required')
        optional = University.objects.create(name='Optional College', country='USA', test_optional=True, acceptance_rate='50.00')
        fit = self.fit(optional)
        self.assertIn('tests_optional', codes(fit, 'reasons'))
        self.assertEqual(fit['score_breakdown']['academic'], round(3.8 / 4 * 15) + 20 + 8)
        # A university that publishes ranges and is not test-optional expects a score.
        self.assertIn('tests_required', codes(self.fit(self.mit), 'gaps'))
        # Not taken yet at a test-optional university: unknown, not a bonus.
        self.student.sat_status = 'not_taken'
        self.student.save()
        fit = self.fit(optional)
        self.assertIn('tests_optional', codes(fit, 'reasons'))
        self.assertEqual(fit['score_breakdown']['academic'], round(3.8 / 4 * 15) + 8)

    def test_english_tests_are_converted_to_ielts_and_the_best_counts(self):
        self.ready_profile(ielts_score='6.0')
        self.certificates({'type': 'toefl', 'score': 100}, {'type': 'duolingo', 'score': 110})
        reason = next(entry for entry in self.fit(self.mit)['reasons'] if entry['code'].startswith('english_'))
        self.assertEqual((reason['code'], reason['params']), ('english_strong', {'test': 'TOEFL', 'score': 100}))
        for row, code in (
            ({'type': 'duolingo', 'score': 110}, 'english_suitable'),
            ({'type': 'pte', 'score': 79}, 'english_strong'),
            ({'type': 'cambridge', 'score': 176}, 'english_suitable'),
            ({'type': 'cambridge', 'score': 160}, 'english_check'),
        ):
            self.ready_profile(ielts_score=None)
            self.certificates(row)
            fit = self.fit(self.mit)
            self.assertIn(code, codes(fit, 'reasons') + codes(fit, 'gaps'), row)

    def test_the_concordance_tables(self):
        cases = {
            'toefl': {120: 9, 117: 8.5, 110: 8, 102: 7.5, 94: 7, 93: 6.5, 79: 6.5, 60: 6, 46: 5.5, 35: 5, 32: 4.5, 0: 4},
            'duolingo': {160: 9, 145: 8.5, 140: 8, 125: 7.5, 120: 7, 105: 6.5, 95: 6, 85: 5.5, 10: 1.5},
            'pte': {90: 9, 86: 8.5, 79: 8, 71: 7.5, 63: 7, 55: 6.5, 47: 6, 39: 5.5, 31: 5, 24: 4.5, 10: 4},
            'cambridge': {230: 7.5, 191: 7.5, 185: 7, 176: 6.5, 169: 6, 162: 5.5, 154: 5, 153: 4.5},
        }
        self.assertEqual(set(cases), set(IELTS_CONCORDANCE))
        for test, scores in cases.items():
            for score, band in scores.items():
                self.assertEqual(ielts_equivalent(test, score), band, (test, score))

    def test_every_test_input_is_in_the_fit_cache_key(self):
        self.ready_profile()
        before = fit_context(self.student)
        self.certificates({'type': 'act', 'score': 33})
        with_act = fit_context(self.student)
        self.certificates({'type': 'act', 'score': 33}, {'type': 'toefl', 'score': 118})
        with_toefl = fit_context(self.student)
        self.student.sat_status = 'not_required'
        self.student.sat_score = None
        self.student.save()
        not_required = fit_context(self.student)
        signatures = {college_search.fit_key(self.student, ctx) for ctx in (before, with_act, with_toefl, not_required)}
        self.assertEqual(len(signatures), 4)
        self.assertEqual((with_act['act'], with_toefl['english']['test']), (33, 'TOEFL'))
        with mock.patch.object(college_search, 'score_university', wraps=college_search.score_university) as scorer:
            self.search('sort=fit')
            self.certificates({'type': 'act', 'score': 34})
            self.search('sort=fit')
        self.assertEqual(scorer.call_count, 2 * (5 + 5), 'a new ACT score rescores the catalogue')


class UnknownBandTests(FitFixture, APITestCase):
    def test_unticking_a_band_keeps_the_rows_without_one(self):
        self.ready_profile()
        everything = {self.mit.name, self.state.name, self.oxford.name, self.tashkent.name, self.unranked.name}
        self.assertEqual(set(self.names('bands=reach,target,unknown')), {self.mit.name, self.oxford.name, self.tashkent.name})
        self.assertEqual(set(self.names('bands=reach,target,safety')), {self.mit.name, self.state.name, self.unranked.name})
        self.assertEqual(set(self.names('bands=unknown')), {self.oxford.name, self.tashkent.name})
        self.assertEqual(set(self.names('bands=reach,target,safety,unknown')), everything)
        self.assertEqual(set(self.names('bands=reach&bands=target&bands=unknown')), {self.mit.name, self.oxford.name, self.tashkent.name})
        self.assertEqual(self.client.get(f'{URL}?bands=dream').status_code, 400)

    def test_without_a_ready_profile_every_row_is_unknown(self):
        self.assertEqual(self.search('bands=unknown')['count'], 5)
        self.assertEqual(self.search('bands=reach,target,safety')['count'], 0)
        self.assertEqual(self.search('facets=true')['facets']['bands'], {'reach': 0, 'target': 0, 'safety': 0, 'unknown': 5})

    def test_facets_count_unknown_as_the_rest_of_the_catalogue(self):
        self.ready_profile()
        bands = self.search('facets=true')['facets']['bands']
        self.assertEqual(bands, {'reach': 1, 'target': 0, 'safety': 2, 'unknown': 2})
        self.assertEqual(sum(bands.values()), University.objects.count())


class UnknownAidTests(FitFixture, APITestCase):
    def test_a_row_without_aid_data_scores_aid_as_unknown(self):
        self.ready_profile()
        self.assertFalse(has_aid_data(self.oxford))
        fit = self.fit(self.oxford)
        self.assertIn('aid_unknown', codes(fit, 'gaps'))
        self.assertNotIn('aid_not_offered', codes(fit, 'gaps'))
        self.assertEqual(fit['score_breakdown']['financial'], 0)

    def test_a_row_with_aid_data_and_no_offered_aid_is_a_real_no(self):
        self.oxford.financial_aid_url = 'https://www.ox.ac.uk/admissions/undergraduate/fees-and-funding'
        self.oxford.save()
        self.assertTrue(has_aid_data(self.oxford))
        self.ready_profile()
        fit = self.fit(self.oxford)
        self.assertIn('aid_not_offered', codes(fit, 'gaps'))
        self.assertEqual(fit['score_breakdown']['financial'], 1)

    def test_aid_details_match_the_university_page(self):
        blank = University(name='Blank', country='France')
        self.assertFalse(has_aid_data(blank))
        for field, value in (
            ('average_aid_usd', 0), ('students_receiving_aid_percent', 0), ('financial_aid_url', 'https://example.edu/aid'),
            ('aid_application_notes', 'Apply early.'), ('need_blind', True), ('css_profile_required', True),
            ('fafsa_required', True), ('meets_full_need', True), ('offers_merit_aid', True),
        ):
            self.assertTrue(has_aid_data(University(name='One', country='France', **{field: value})), field)

    def test_aid_does_not_matter_without_a_scholarship_need(self):
        self.ready_profile(scholarship_needed=False)
        fit = self.fit(self.oxford)
        self.assertNotIn('aid_unknown', codes(fit, 'gaps'))
        self.assertEqual(fit['score_breakdown']['financial'], 8)


class EvidenceQueryTests(FitFixture, APITestCase):
    def evidence_queries(self, query):
        with CaptureQueriesContext(connection) as context:
            self.search(query)
        return [item['sql'] for item in context.captured_queries if '"admissions_honor"' in item['sql']]

    def test_evidence_is_counted_in_one_query(self):
        Honor.objects.create(student=self.student, title='Olympiad')
        Honor.objects.create(student=self.student, title='Debate')
        Project.objects.create(student=self.student, title='Robot')
        with self.assertNumQueries(1):
            counts = evidence_counts(self.student)
        self.assertEqual(counts, {
            'achievements': 0, 'honors': 2, 'researches': 0, 'projects': 1, 'internships': 0, 'activities': 0,
        })

    def test_requests_read_the_evidence_once_and_only_when_they_need_fit(self):
        self.ready_profile()
        for query in (f'ids={self.mit.id}', 'sort=ranking', 'sort=price', 'sort=fit&facets=true', 'bands=reach'):
            self.assertEqual(len(self.evidence_queries(query)), 1, query)
        self.assertEqual(self.evidence_queries('search=nowhere-at-all'), [], 'no rows to score')
        self.student.budget_usd = None
        self.student.save()
        self.assertEqual(self.evidence_queries('sort=fit&facets=true'), [], 'no fit until the profile is ready')


class CountryAliasTests(FitFixture, APITestCase):
    def test_every_spelling_of_a_market_finds_its_rows(self):
        for spelling in ('USA', 'US', 'United States', 'United States of America', 'usa'):
            self.assertEqual(set(self.names(f'country={spelling}')), {self.mit.name, self.state.name}, spelling)

    def test_china_and_hong_kong_aliases(self):
        peking = University.objects.create(name='Peking University', country='China (Mainland)')
        tsinghua = University.objects.create(name='Tsinghua University', country='China')
        hku = University.objects.create(name='The University of Hong Kong', country='Hong Kong SAR')
        cuhk = University.objects.create(name='The Chinese University of Hong Kong', country='Hong Kong')
        for spelling in ('China', 'China (Mainland)', 'Mainland China'):
            self.assertEqual(set(self.names(f'country={spelling}')), {peking.name, tsinghua.name}, spelling)
        for spelling in ('Hong Kong', 'Hong Kong SAR', 'HK'):
            self.assertEqual(set(self.names(f'country={spelling}')), {hku.name, cuhk.name}, spelling)


# Every code score_university can emit; frontend/src/translations/fitReasons.js translates each.
FIT_CODES = {
    'sat_above_range', 'sat_in_range', 'sat_near_minimum', 'sat_below_minimum',
    'act_above_range', 'act_in_range', 'act_near_minimum', 'act_below_minimum',
    'tests_optional', 'tests_required', 'test_score_missing', 'test_range_missing_for', 'test_range_missing',
    'english_strong', 'english_suitable', 'english_check', 'english_missing',
    'country_match', 'major_match', 'major_check',
    'cost_within_budget', 'cost_above_budget', 'cost_far_above_budget', 'cost_missing',
    'net_after_aid_within_budget', 'net_after_aid_above_budget', 'net_after_aid_far_above_budget',
    'aid_available', 'aid_not_offered', 'aid_unknown',
}


def stub_university(**values):
    fields = dict(
        country='United States', market='us', sat_min=None, sat_max=None, act_min=None, act_max=None,
        test_optional=False, popular_majors='', net_price_usd=None, intl_cost_usd=None, acceptance_rate=None,
        offers_international_aid=False, offers_merit_aid=False, offers_need_based_aid=False,
        **dict.fromkeys(college_search.AID_DETAILS),
    )
    fields.update(values)
    return SimpleNamespace(programs=SimpleNamespace(all=list), **fields)


class ReasonCodeTests(APITestCase):
    def context(self, **values):
        return {
            'gpa': 3.8, 'gpa_scale': 4, 'sat': None, 'sat_status': 'not_taken', 'act': None, 'english': None,
            'budget': 20000, 'countries': ['us'], 'major': 'computer science', 'major_name': 'Computer Science',
            'scholarship_needed': True, 'strength': 0, **values,
        }

    def test_every_code_is_emitted_and_shaped_for_the_frontend(self):
        english = lambda ielts: {'test': 'IELTS', 'score': ielts, 'ielts': ielts}  # noqa: E731
        scenarios = [
            (dict(sat_min=1200, sat_max=1400), dict(sat=1500, english=english(7.5))),
            (dict(sat_min=1200, sat_max=1400, popular_majors='Computer Science'), dict(sat=1300, english=english(6.5))),
            (dict(sat_min=1200), dict(sat=1150, english=english(5.5))),
            (dict(sat_min=1200), dict(sat=900)),
            (dict(act_min=30, act_max=33), dict(act=34)),
            (dict(act_min=30, act_max=33), dict(act=31)),
            (dict(act_min=30), dict(act=29)),
            (dict(act_min=30), dict(act=20)),
            (dict(test_optional=True), dict()),
            (dict(sat_min=1200), dict(sat_status='not_required')),
            (dict(sat_min=1200), dict()),
            (dict(sat_min=1200), dict(act=30)),
            (dict(), dict(sat=1400)),
            (dict(intl_cost_usd=15000), dict()),
            (dict(intl_cost_usd=25000), dict()),
            (dict(intl_cost_usd=90000), dict()),
            (dict(net_price_usd=15000, offers_international_aid=True), dict()),
            (dict(net_price_usd=25000, offers_international_aid=True), dict()),
            (dict(net_price_usd=90000, offers_international_aid=True), dict()),
            (dict(financial_aid_url='https://example.edu/aid', popular_majors='Computer Science'), dict(sat=1400, english=english(7))),
        ]
        seen = set()
        for university, ctx in scenarios:
            fit = score_university(stub_university(**university), self.context(**ctx))
            for entry in fit['reasons'] + fit['gaps']:
                self.assertEqual(set(entry), {'code', 'params', 'text'})
                self.assertRegex(entry['code'], r'^[a-z]+(_[a-z]+)*$')
                self.assertTrue(entry['text'])
                seen.add(entry['code'])
        self.assertEqual(seen, FIT_CODES)

    def test_the_frontend_translates_every_code(self):
        source = FIT_REASONS_JS.read_text(encoding='utf-8')
        block = source[source.index('FIT_REASON_TEMPLATES'):]
        translated = set(re.findall(r'^  ([a-z_]+): \{', block, re.MULTILINE))
        self.assertEqual(translated, FIT_CODES)
