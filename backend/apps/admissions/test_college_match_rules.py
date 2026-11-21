"""The college match rules: subject-based candidates, the aid and cost gate, ordering, 3/4/3 and determinism."""
from unittest import mock

from rest_framework.test import APITestCase

from apps.admissions import ai_budget
from apps.admissions.college_match import aid_status, international_cost, passes_gate, sat_position
from apps.admissions.essay_lab import coach
from apps.admissions.models import Activity, Honor, University, UniversitySubjectRank
from apps.admissions.test_college_match import URL, MatchFixture, add_check


class RulesFixture(MatchFixture):
    """Safety-band US universities (80% admit rate, test optional) with Computer Science ranks."""

    def college(self, name, rank=None, code='COM02', **fields):
        values = {
            'country': 'United States', 'acceptance_rate': '80.00', 'test_optional': True,
            'offers_international_aid': True, 'intl_cost_usd': 25000, **fields,
        }
        university = University.objects.create(name=name, **values)
        if rank is not None:
            self.rank(university, rank, code=code)
        return university

    def match(self):
        response = self.client.post(URL)
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        return response.data

    def names(self, data=None, group=None):
        data = data or self.match()
        return [row['name'] for g in data['groups'] if group in (None, g['band']) for row in g['results']]


class GateTests(RulesFixture, APITestCase):
    def test_a_student_who_needs_a_scholarship_loses_universities_without_international_aid(self):
        self.college('Aid College', 10)
        self.college('No Aid College', 11, offers_international_aid=False, offers_merit_aid=True, intl_cost_usd=60000)
        self.college('Cheap No Aid College', 12, offers_international_aid=False, intl_cost_usd=29000)
        self.ready_profile(budget_usd=30000, scholarship_needed=True)
        names = self.names()
        self.assertIn('Aid College', names)
        self.assertNotIn('No Aid College', names)
        self.assertIn('Cheap No Aid College', names, 'within the budget it stays')

    def test_without_a_scholarship_need_only_a_cost_over_twice_the_budget_without_aid_drops(self):
        self.college('Dear College', 10, offers_international_aid=False, intl_cost_usd=70000)
        self.college('Stretch College', 11, offers_international_aid=False, intl_cost_usd=55000)
        self.college('Dear Aid College', 12, intl_cost_usd=90000)
        self.ready_profile(budget_usd=30000, scholarship_needed=False)
        names = self.names()
        self.assertNotIn('Dear College', names)
        self.assertIn('Stretch College', names)
        self.assertIn('Dear Aid College', names, 'aid for international students keeps an expensive university')

    def test_universities_dropped_for_unlisted_aid_are_counted_in_a_note(self):
        self.college('Unlisted Aid College', 10, offers_international_aid=False, intl_cost_usd=60000)
        self.ready_profile(scholarship_needed=True)
        notes = {note['code']: note for note in self.match()['notes']}
        self.assertEqual(notes['aid_unlisted']['params'], {'count': 1})

    def test_an_unknown_cost_is_kept_and_flagged(self):
        self.college('Unpriced College', 10, intl_cost_usd=None)
        self.ready_profile()
        row = next(row for g in self.match()['groups'] for row in g['results'] if row['name'] == 'Unpriced College')
        self.assertTrue(row['cost_unknown'])
        self.assertEqual((row['cost_usd'], row['cost_vs_budget']), (None, 'unknown'))

    def test_the_cost_is_the_international_cost_never_a_us_net_price(self):
        university = University(name='U', country='United States', market='us', net_price_usd=9000, tuition_usd=50000)
        university.cost = None
        self.assertIsNone(international_cost(university))
        elsewhere = University(name='V', country='Germany', net_price_usd=None, tuition_usd=3000)
        elsewhere.cost = None
        self.assertEqual(international_cost(elsewhere), 3000)

    def test_passes_gate_is_pure_rules(self):
        plain = University(name='P', country='Germany')
        ctx = {'budget': 10000, 'scholarship_needed': True}
        self.assertFalse(passes_gate(plain, None, ctx))
        self.assertTrue(passes_gate(plain, 10000, ctx))
        self.assertFalse(passes_gate(plain, 10001, {**ctx, 'scholarship_needed': False}) and False)
        self.assertTrue(passes_gate(plain, 20000, {**ctx, 'scholarship_needed': False}))
        self.assertFalse(passes_gate(plain, 20001, {**ctx, 'scholarship_needed': False}))
        self.assertTrue(passes_gate(University(name='Q', country='Germany', offers_international_aid=True), 90000, ctx))


class CardFactsTests(RulesFixture, APITestCase):
    def test_aid_status_from_the_catalogue_fields(self):
        U = University
        self.assertEqual(aid_status(U(offers_international_aid=True, meets_full_need=True)), 'yes')
        self.assertEqual(aid_status(U(intl_need_policy='need_blind')), 'yes')
        self.assertEqual(aid_status(U(intl_need_policy='need_aware')), 'need_aware')
        self.assertEqual(aid_status(U(offers_merit_aid=True)), 'merit')
        self.assertEqual(aid_status(U(offers_need_based_aid=True)), 'none')
        self.assertEqual(aid_status(U(financial_aid_url='https://x.example/aid')), 'none')
        self.assertEqual(aid_status(U()), 'unknown')

    def test_sat_position_below_inside_above_and_no_range(self):
        university = University(sat_min=1200, sat_max=1400)
        self.assertEqual(sat_position(university, 1100)['position'], 'below')
        self.assertEqual(sat_position(university, 1300), {'position': 'inside', 'score': 1300, 'min': 1200, 'max': 1400})
        self.assertEqual(sat_position(university, 1450)['position'], 'above')
        self.assertEqual(sat_position(University(), 1450)['position'], 'no_range')
        self.assertEqual(sat_position(university, None)['position'], 'no_score')

    def test_a_card_names_the_subject_rank_sat_position_aid_and_cost(self):
        self.college('Ranged College', 0, code='COM02')
        UniversitySubjectRank.objects.filter(university__name='Ranged College').update(rank=201, rank_label='201-250')
        self.ready_profile()
        data = self.match()
        rows = {row['name']: row for g in data['groups'] for row in g['results']}
        mit = rows[self.mit.name]
        self.assertEqual(mit['subject'], {'code': 'COM02', 'name': 'Computer Science & Information Systems', 'year': 2026, 'overall': False, 'rank': 1, 'rank_label': '1'})
        self.assertEqual(mit['sat'], {'position': 'below', 'score': 1450, 'min': 1520, 'max': 1580})
        self.assertEqual(mit['aid_status'], 'yes')
        self.assertEqual((mit['cost_usd'], mit['budget_usd'], mit['cost_vs_budget']), (85000, 30000, 'over'))
        self.assertEqual(rows['Ranged College']['subject']['rank_label'], '201-250')
        self.assertEqual(data['subjects'], [{'code': 'COM02', 'name': 'Computer Science & Information Systems'}])
        self.assertEqual(data['hints'], [])


class OrderingTests(RulesFixture, APITestCase):
    def test_subject_rank_comes_first_then_aid_for_internationals(self):
        self.college('Rank Ten Merit', 10, offers_international_aid=False, offers_merit_aid=True, intl_cost_usd=20000)
        self.college('Rank Ten Aid', 10, meets_full_need=True, intl_cost_usd=20000)
        self.college('Rank Five Merit', 5, offers_international_aid=False, offers_merit_aid=True, intl_cost_usd=20000)
        self.ready_profile(scholarship_needed=False)
        self.assertEqual(self.names(group='safety'), ['Rank Five Merit', 'Rank Ten Aid', 'Rank Ten Merit'])

    def test_then_a_higher_international_admit_rate_then_qs_rank_then_name(self):
        self.college('Rate Low', 20, intl_acceptance_rate='55.00', ranking=100)
        self.college('Rate High Late', 20, intl_acceptance_rate='70.00', ranking=400)
        self.college('Rate High Zed', 20, intl_acceptance_rate='70.00', ranking=300)
        self.college('Rate High Alpha', 20, intl_acceptance_rate='70.00', ranking=300)
        self.ready_profile(scholarship_needed=False)
        University.objects.filter(pk=self.state.pk).delete()
        data = self.match()
        order = [row['name'] for g in data['groups'] for row in g['results'] if g['band'] == 'safety'][:3]
        self.assertEqual(order, ['Rate High Alpha', 'Rate High Zed', 'Rate High Late'])
        self.assertIn('Rate Low', self.names(data))

    def test_reach_group_takes_reach_before_far_reach(self):
        self.ready_profile()
        for index in range(2):
            self.college(f'Hard {index}', 1 + index, acceptance_rate='10.00', test_optional=False, sat_min=1300, sat_max=1450)
        data = self.match()
        reach = [row for g in data['groups'] if g['band'] == 'reach' for row in g['results']]
        self.assertEqual(len(reach), 3)
        bands = [row['band'] for row in reach]
        self.assertEqual(bands, ['reach', 'reach', 'far_reach'])
        self.assertEqual(reach[-1]['name'], self.mit.name, 'far reach MIT comes after the reach ones')

    def test_a_ranked_university_beats_an_unranked_one_with_the_major_in_its_popular_majors(self):
        self.college('Popular Majors College', None, popular_majors='Computer Science, Biology')
        self.college('Other College', None, popular_majors='Fine Art')
        self.ready_profile(scholarship_needed=False)
        names = self.names(group='safety')
        self.assertEqual(names, [self.state.name, 'Popular Majors College'])
        self.assertNotIn('Other College', self.names())


class ListShapeTests(RulesFixture, APITestCase):
    def test_three_reach_four_target_three_safety_filled_from_the_nearest_group(self):
        self.ready_profile()
        for index in range(12):
            self.college(f'Open College {index:02}', 20 + index)
        data = self.match()
        sizes = [len(group['results']) for group in data['groups']]
        self.assertEqual(sizes, [3, 4, 3])
        self.assertEqual([group['band'] for group in data['groups']], ['reach', 'target', 'safety'])
        notes = {note['params']['group']: note for note in data['notes'] if note['code'] == 'filled_from'}
        self.assertEqual(notes['target']['params'], {'group': 'target', 'from': 'safety', 'count': 4})
        self.assertEqual(notes['reach']['params']['from'], 'safety')
        self.assertEqual(len(self.names(data)), len(set(self.names(data))))

    def test_a_short_list_says_so(self):
        self.ready_profile()
        data = self.match()
        self.assertEqual(len(self.names(data)), 2)
        self.assertIn('short_list', [note['code'] for note in data['notes']])

    def test_only_target_countries_are_listed(self):
        self.college('German College', 3, country='Germany')
        self.ready_profile(target_countries='US')
        self.assertNotIn('German College', self.names())
        self.ready_profile(target_countries='US, Germany')
        self.assertIn('German College', self.names())


class SubjectChoiceTests(RulesFixture, APITestCase):
    def test_no_mapped_major_uses_the_overall_rank_and_hints(self):
        self.ready_profile(target_major='Quantum basket weaving')
        data = self.match()
        self.assertEqual(data['subjects'], [])
        self.assertEqual(data['hints'][0]['code'], 'pick_major')
        row = next(row for g in data['groups'] for row in g['results'] if row['name'] == self.mit.name)
        self.assertTrue(row['subject']['overall'])
        self.assertEqual(row['subject']['rank'], 1)

    def test_the_best_rank_across_several_majors_counts(self):
        self.college('Business College', 2, code='BUS01')
        self.rank(self.state, 2, code='ECO01')
        self.ready_profile(target_major='Business, Economics', scholarship_needed=False)
        data = self.match()
        rows = {row['name']: row for g in data['groups'] for row in g['results']}
        self.assertEqual(rows['Business College']['subject']['code'], 'BUS01')
        self.assertEqual(rows[self.state.name]['subject'], {
            'code': 'ECO01', 'name': 'Economics & Econometrics', 'year': 2026, 'overall': False, 'rank': 2, 'rank_label': '2',
        })
        self.assertNotIn(self.mit.name, rows, 'no Business or Economics rank')

    def test_a_broad_area_major_hints_at_a_specific_one(self):
        self.rank(self.mit, 5, code='AREA_ENG')
        self.ready_profile(target_major='Engineering')
        data = self.match()
        self.assertEqual(data['hints'][0]['code'], 'broad_area')
        self.assertEqual(self.names(data), [self.mit.name])


class DeterminismTests(RulesFixture, APITestCase):
    def test_the_same_profile_twice_gives_identical_lists(self):
        self.ready_profile()
        for index in range(12):
            self.college(f'Open College {index:02}', 20 + index // 2)
        first, second = self.match(), self.match()
        first.pop('generated_at'), second.pop('generated_at')
        self.assertEqual(first, second)

    def test_activities_and_essays_do_not_change_the_list_or_the_bands(self):
        self.ready_profile()
        for index in range(12):
            self.college(f'Open College {index:02}', 20 + index)
        before = self.match()
        Honor.objects.create(student=self.student, title='International olympiad gold', level='international', verified=True)
        for index in range(4):
            Activity.objects.create(student=self.student, name=f'Club {index}', role='Founder', verified=True, impact='Won nationals')
        add_check(self.student, 96)
        after = self.match()
        shape = lambda data: [(g['band'], [(row['id'], row['band'], row['fit']['admission_band']) for row in g['results']]) for g in data['groups']]
        self.assertEqual(shape(before), shape(after))
        self.assertNotEqual(before['rubric'], after['rubric'])

    def test_the_default_match_makes_no_ai_call(self):
        self.ready_profile()
        with mock.patch.object(coach, '_post') as post, mock.patch('urllib.request.urlopen') as urlopen, \
                mock.patch.object(ai_budget, 'consume') as consume, mock.patch.object(coach, '_request_gateway') as gateway:
            self.match()
        for call in (post, urlopen, consume, gateway):
            call.assert_not_called()
