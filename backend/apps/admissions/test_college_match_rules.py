"""The college match rules: subject-based candidates, the aid and cost gate, ordering, 3/4/3 and determinism."""
from unittest import mock

from rest_framework.test import APITestCase

from apps.admissions import ai_budget
from apps.admissions import admission_chance
from apps.admissions.college_match import (
    MAX_FAR_REACH, aid_status, international_cost, passes_gate, pick_list, sat_position, sort_key,
)
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
        self.college('Merit Only College', 11, offers_international_aid=False, offers_merit_aid=True, intl_cost_usd=60000)
        self.college('Domestic Aid College', 12, offers_international_aid=False, offers_need_based_aid=True, intl_cost_usd=60000)
        self.ready_profile(scholarship_needed=True)
        notes = {note['code']: note for note in self.match()['notes']}
        self.assertEqual(notes['aid_unknown']['params'], {'count': 1})
        self.assertEqual(notes['aid_unknown']['text'], '1 universities were left out: the catalogue has no aid details')
        self.assertEqual(notes['no_intl_aid']['params'], {'count': 2})
        self.assertEqual(notes['no_intl_aid']['text'], '2 universities were left out: they list no aid for students from abroad')
        self.assertNotIn('aid_unlisted', notes)

    def test_without_a_scholarship_need_a_dropped_university_gets_no_aid_note(self):
        self.college('Dear College', 10, offers_international_aid=False, intl_cost_usd=90000)
        self.ready_profile(scholarship_needed=False)
        codes = [note['code'] for note in self.match()['notes']]
        self.assertNotIn('aid_unknown', codes)
        self.assertNotIn('no_intl_aid', codes)

    def test_a_scholarship_student_without_a_budget_loses_every_no_aid_university(self):
        self.college('Cheap No Aid College', 10, offers_international_aid=False, intl_cost_usd=5000)
        self.college('Aid College', 11)
        self.ready_profile(scholarship_needed=True, budget_usd=None)
        data = self.match()
        names = self.names(data)
        self.assertNotIn('Cheap No Aid College', names, 'no budget is not "within the budget"')
        self.assertIn('Aid College', names)
        notes = {note['code']: note['params'] for note in data['notes']}
        self.assertEqual(notes['aid_unknown'], {'count': 1})

    def test_a_student_without_sat_or_act_is_told_about_universities_that_expect_one(self):
        for index in range(2):
            self.college(f'Test Required {index}', 10 + index, acceptance_rate='10.00', test_optional=False, sat_min=1300, sat_max=1450)
        self.college('ACT Required', 12, acceptance_rate='10.00', test_optional=False, act_min=30, act_max=34)
        self.college('No Rate College', 13, acceptance_rate=None)
        self.ready_profile(sat_score=None, scholarship_needed=False)
        data = self.match()
        names = self.names(data)
        for name in ('Test Required 0', 'Test Required 1', 'ACT Required'):
            self.assertNotIn(name, names)
        notes = {note['code']: note for note in data['notes']}
        self.assertEqual(notes['test_needed']['params'], {'count': 3})
        self.assertEqual(notes['test_needed']['text'],
                         '3 universities were left out because they expect an SAT or ACT score; add yours to see them')
        self.assertEqual(notes['no_admission_data']['params'], {'count': 1}, 'no admit rate is not a missing test')
        self.assertIn(self.mit.name, names, 'every student is far reach at MIT, test or not')

    def test_with_a_score_a_university_without_a_rate_is_no_admission_data(self):
        self.college('Test Required', 10, acceptance_rate=None, test_optional=False, sat_min=1300, sat_max=1450)
        self.ready_profile(scholarship_needed=False)
        notes = {note['code']: note['params'] for note in self.match()['notes']}
        self.assertNotIn('test_needed', notes)
        self.assertEqual(notes['no_admission_data'], {'count': 1})

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
        university.intl_cost_usd = 70000
        self.assertEqual(international_cost(university), 70000)
        elsewhere = University(name='V', country='Germany', net_price_usd=None, tuition_usd=3000)
        elsewhere.cost = None
        self.assertEqual(international_cost(elsewhere), 3000)

    def test_a_us_row_with_a_blank_market_and_only_a_net_price_is_unpriced(self):
        blank = University(name='B', country='USA', market='', net_price_usd=9000)
        blank.cost = 9000  # what pricing.py gives a blank-market row
        self.assertIsNone(international_cost(blank))
        University.objects.filter(pk=self.state.pk).update(market='', intl_cost_usd=None, net_price_usd=9000)
        self.ready_profile(scholarship_needed=False)
        row = next(row for g in self.match()['groups'] for row in g['results'] if row['id'] == self.state.pk)
        self.assertEqual((row['cost_usd'], row['cost_vs_budget']), (None, 'unknown'))

    def test_outside_the_us_the_net_price_comes_before_the_tuition(self):
        elsewhere = University(name='V', country='Germany', net_price_usd=5000, tuition_usd=3000)
        elsewhere.cost = 5000
        self.assertEqual(international_cost(elsewhere), 5000)
        unannotated = University(name='W', country='Germany', net_price_usd=6000, tuition_usd=3000)
        self.assertEqual(international_cost(unannotated), 6000)

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

    def test_an_act_is_named_when_there_is_no_sat(self):
        university = University(sat_min=1200, sat_max=1400, act_min=26, act_max=32)
        self.assertEqual(sat_position(university, None, 31), {'position': 'act_used', 'score': 31, 'min': 1200, 'max': 1400})
        self.assertEqual(sat_position(university, 1300, 31)['position'], 'inside', 'the SAT comes first')
        self.assertEqual(sat_position(University(), None, 31)['position'], 'no_range')

    def test_the_act_card_reaches_the_api(self):
        self.ready_profile(sat_score=None, scholarship_needed=False)
        self.student.application_profile = {'certificates': [{'type': 'act', 'score': 35, 'name': '', 'test_date': None}]}
        self.student.save()
        rows = {row['id']: row for g in self.match()['groups'] for row in g['results']}
        self.assertEqual(rows[self.mit.pk]['sat'], {'position': 'act_used', 'score': 35, 'min': 1520, 'max': 1580})

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

    def test_a_short_abbreviation_is_not_found_inside_another_word(self):
        self.college('Physics College', None, popular_majors='Physics')
        self.college('Politics College', None, popular_majors='Political Science')
        self.college('Abbreviation College', None, popular_majors='CS, Biology')
        for major in ('CS', 'IT'):
            self.ready_profile(target_major=major, scholarship_needed=False)
            names = self.names()
            self.assertNotIn('Physics College', names, major)
            self.assertNotIn('Politics College', names, major)
        self.ready_profile(target_major='CS', scholarship_needed=False)
        self.assertIn('Abbreviation College', self.names())

    def test_suggested_programs_do_not_match_an_abbreviation_inside_another_word(self):
        from apps.admissions.college_match import suggested_programs
        from apps.admissions.models import UniversityProgram
        UniversityProgram.objects.create(university=self.state, name='BSc Physics', canonical_major='Physics')
        UniversityProgram.objects.create(university=self.state, name='BA Political Science', canonical_major='Political Science')
        UniversityProgram.objects.create(university=self.state, name='BSc CS Theory', canonical_major='CS Theory')
        for major in ('cs', 'it'):
            found = [item['name'] for item in suggested_programs(self.state, [major])]
            self.assertNotIn('BSc Physics', found, major)
            self.assertNotIn('BA Political Science', found, major)
        self.assertIn('BSc CS Theory', [item['name'] for item in suggested_programs(self.state, ['cs'])])


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


def entry(pk, band, rank=None):
    return {'id': pk, 'band': band, 'key': (rank if rank is not None else pk,)}


def bands(chosen, group):
    return [row['band'] for row in chosen[group]]


class FarReachCapTests(APITestCase):
    FAR, REACH, TARGET, SAFETY = admission_chance.FAR_REACH, admission_chance.REACH, admission_chance.TARGET, admission_chance.SAFETY

    def test_one_far_reach_then_target_before_a_second_far_reach(self):
        self.assertEqual(MAX_FAR_REACH, 1)
        entries = [entry(pk, self.FAR) for pk in range(1, 6)] + [entry(pk, self.TARGET) for pk in range(10, 18)]
        chosen, notes = pick_list(entries)
        self.assertEqual(bands(chosen, 'reach'), [self.FAR, self.TARGET, self.TARGET])
        self.assertEqual([row['id'] for row in chosen['reach']], [1, 14, 15])
        self.assertEqual([row['id'] for row in chosen['target']], [10, 11, 12, 13])
        self.assertEqual([row['id'] for row in chosen['safety']], [16, 17], 'safety fills from target, never far reach')
        self.assertIn({'group': 'reach', 'from': 'target', 'count': 2}, [note['params'] for note in notes])

    def test_two_reach_and_three_far_reach_give_one_far_reach(self):
        entries = [entry(1, self.REACH), entry(2, self.REACH)] + [entry(pk, self.FAR) for pk in (3, 4, 5)]
        entries += [entry(pk, self.TARGET) for pk in range(10, 15)]
        chosen, _ = pick_list(entries)
        self.assertEqual(bands(chosen, 'reach'), [self.REACH, self.REACH, self.FAR])

    def test_a_second_far_reach_only_when_target_and_safety_are_spent(self):
        entries = [entry(pk, self.FAR) for pk in range(1, 6)] + [entry(10, self.TARGET)]
        chosen, notes = pick_list(entries)
        self.assertEqual(bands(chosen, 'reach'), [self.FAR, self.FAR, self.FAR])
        self.assertEqual(bands(chosen, 'target'), [self.TARGET])
        self.assertIn('short_list', [note['code'] for note in notes])

    def test_reach_short_after_an_empty_target_fills_from_safety(self):
        entries = [entry(1, self.REACH)] + [entry(pk, self.SAFETY) for pk in range(10, 16)]
        chosen, notes = pick_list(entries)
        self.assertEqual([row['id'] for row in chosen['reach']], [1, 13, 14])
        self.assertEqual([row['id'] for row in chosen['target']], [15])
        self.assertEqual([row['id'] for row in chosen['safety']], [10, 11, 12])
        params = [note['params'] for note in notes if note['code'] == 'filled_from']
        self.assertEqual(params, [{'group': 'reach', 'from': 'safety', 'count': 2}, {'group': 'target', 'from': 'safety', 'count': 1}])
        self.assertEqual(notes[0]['text'], 'Too few universities in the reach group fit you; 2 from the safety group were added.')


class AdmitRateOrderTests(RulesFixture, APITestCase):
    def test_the_sort_uses_the_same_rate_as_the_band_estimated_or_published(self):
        pick = {'rank': 10}
        estimated = University(name='Estimated', country='United States', acceptance_rate=50)
        published = University(name='Published', country='United States', acceptance_rate=90, intl_acceptance_rate=20)
        unknown = University(name='Unknown', country='United States')
        self.assertEqual(admission_chance.international_rate(estimated), (50.0, True))
        keys = sorted((sort_key(u, pick, 'yes'), u.name) for u in (unknown, published, estimated))
        self.assertEqual([name for _, name in keys], ['Estimated', 'Published', 'Unknown'])
        forty = University(name='Forty', country='United States', acceptance_rate=50, intl_acceptance_rate=None)
        forty.acceptance_rate = 40  # estimated 32% for students from abroad
        self.assertLess(sort_key(forty, pick, 'yes'), sort_key(published, pick, 'yes'))

    def test_an_estimated_rate_sorts_above_a_lower_published_one_in_the_api(self):
        self.college('Published Rate', 20, intl_acceptance_rate='55.00')
        self.college('Estimated Rate', 20, acceptance_rate='80.00')
        self.ready_profile(scholarship_needed=False)
        University.objects.filter(pk=self.state.pk).delete()
        data = self.match()
        safety = [row for g in data['groups'] if g['band'] == 'safety' for row in g['results']]
        self.assertEqual([row['name'] for row in safety][:2], ['Estimated Rate', 'Published Rate'])
        self.assertTrue(safety[0]['fit']['chance']['admit_rate_estimated'])
        self.assertEqual(safety[0]['fit']['chance']['admit_rate'], 80.0)


class TieAndInsertOrderTests(RulesFixture, APITestCase):
    def build(self, order):
        for index in order:
            self.college(f'Open College {index:02}', 20 + index // 3, pk=5000 + index)

    def test_insert_order_does_not_change_the_list(self):
        self.ready_profile(scholarship_needed=False)
        self.build(range(12))
        first = [(g['band'], [row['id'] for row in g['results']]) for g in self.match()['groups']]
        University.objects.filter(pk__gte=5000).delete()
        self.build(reversed(range(12)))
        second = [(g['band'], [row['id'] for row in g['results']]) for g in self.match()['groups']]
        self.assertEqual(first, second)

    def test_tied_keys_are_broken_by_name_then_pk(self):
        self.ready_profile(scholarship_needed=False)
        University.objects.filter(pk=self.state.pk).delete()
        self.college('Beta College', 20, pk=6003)
        self.college('Twin College', 20, pk=6002)
        self.college('Twin College', 20, pk=6001, country='USA')
        self.college('Alpha College', 20, pk=6004)
        groups = {g['band']: [row['id'] for row in g['results']] for g in self.match()['groups']}
        self.assertEqual(groups['safety'], [6004, 6003, 6001])
        self.assertEqual(groups['reach'][-1], 6002, 'the later twin is the spare that fills reach')


class MajorPhraseTests(RulesFixture, APITestCase):
    def test_oil_and_gas_suggests_a_petroleum_engineering_program(self):
        from apps.admissions.models import UniversityProgram

        petro = self.college('Petroleum College', 5, code='PET01')
        UniversityProgram.objects.create(university=petro, name='BSc Petroleum Engineering', canonical_major='Petroleum Engineering')
        self.ready_profile(target_major='Oil and gas', scholarship_needed=False)
        row = next(row for g in self.match()['groups'] for row in g['results'] if row['id'] == petro.pk)
        self.assertEqual([program['name'] for program in row['suggested_programs']], ['BSc Petroleum Engineering'])


class SampleProfileTests(RulesFixture, APITestCase):
    """The five calibration profiles of docs/naseeb-ai-rules/college-match.md against one small catalogue.

    The catalogue (target country US): MIT (CS #1, 4% admit, SAT 1520-1580), Ohio State (CS #120, test optional),
    six open CS colleges (80% admit, test optional, aid), three selective CS universities (30% admit, SAT
    1350-1500 required, aid), one elite CS university (8% admit, SAT 1500-1570 required, aid), one CS college with
    merit aid only and one with no aid details (both $40-45k), and one engineering school (broad area rank only).
    """

    def setUp(self):
        super().setUp()
        for index in range(6):
            self.college(f'Open CS {index}', 30 + index)
        for index in range(3):
            self.college(f'Selective CS {index}', 10 + index, acceptance_rate='30.00', test_optional=False,
                         sat_min=1350, sat_max=1500, intl_cost_usd=60000)
        self.college('Elite CS', 3, acceptance_rate='8.00', test_optional=False, sat_min=1500, sat_max=1570,
                     intl_cost_usd=80000)
        self.college('Merit CS', 15, acceptance_rate='60.00', offers_international_aid=False, offers_merit_aid=True,
                     intl_cost_usd=45000)
        self.college('Unknown Aid CS', 16, acceptance_rate='60.00', offers_international_aid=False, intl_cost_usd=40000)
        self.college('Engineering School', 8, code='AREA_ENG', acceptance_rate='70.00')

    def summary(self, **answers):
        """``(group sizes, note codes, {note code: params} of the left-out notes, far-reach count)``."""
        self.ready_profile(**answers)
        data = self.match()
        notes = data['notes']
        left_out = {note['code']: note['params'] for note in notes if note['code'] != 'filled_from'}
        far = sum(row['band'] == 'far_reach' for g in data['groups'] for row in g['results'])
        return [len(group['results']) for group in data['groups']], sorted(note['code'] for note in notes), left_out, far

    def test_no_sat(self):
        # The selective universities need a test; MIT and Elite CS are far reach whatever the scores (one is kept).
        self.assertEqual(self.summary(sat_score=None, scholarship_needed=False), (
            [3, 4, 3], ['filled_from', 'filled_from', 'test_needed'], {'test_needed': {'count': 3}}, 1))

    def test_sat_1500_needing_a_scholarship_on_a_10k_budget(self):
        # Merit CS (merit only) and Unknown Aid CS (no aid details) cost more than $10k: left out with a note each.
        # The student lists no activities, so the bands are the ones College Search shows: the selective
        # universities are reaches, not targets, so the capped far reach is not needed.
        self.assertEqual(self.summary(sat_score=1500, scholarship_needed=True, budget_usd=10000), (
            [3, 4, 3], ['aid_unknown', 'filled_from', 'no_intl_aid'],
            {'aid_unknown': {'count': 1}, 'no_intl_aid': {'count': 1}}, 0))

    def test_engineering(self):
        # A broad area: only the engineering school has a rank in it.
        self.assertEqual(self.summary(target_major='Engineering'), ([0, 0, 1], ['short_list'], {'short_list': {'count': 1}}, 0))
        self.assertEqual(self.match()['hints'][0]['code'], 'broad_area')

    def test_russian_computer_science(self):
        # SAT 1450 is reach at the three selective universities; the capped far reach is not needed.
        self.assertEqual(self.summary(target_major='информатика', scholarship_needed=False), (
            [3, 4, 3], ['filled_from'], {}, 0))
        self.assertEqual(self.match()['subjects'], [{'code': 'COM02', 'name': 'Computer Science & Information Systems'}])

    def test_undecided(self):
        # No mapped major: the overall QS rank, so only the two QS-ranked US universities.
        self.assertEqual(self.summary(target_major='Undecided'), ([1, 0, 1], ['short_list'], {'short_list': {'count': 2}}, 1))
        self.assertEqual(self.match()['hints'][0]['code'], 'pick_major')
