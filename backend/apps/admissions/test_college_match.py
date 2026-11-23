"""The college match: the student's rubric (no AI), the balanced list, and the optional "Why these fit you" lines."""
import io
import json
import re
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.db.migrations.loader import MigrationLoader
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from apps.admissions import ai_budget, match_reasons
from apps.admissions.college_search import fit_context, record_chance_snapshot, score_university
from apps.admissions.essay_lab import coach
from apps.admissions import ai_providers
from apps.admissions.models import (
    Activity, AiUsageLog, Application, Essay, EssayDepthCheck, EssayTab, Honor, RecommendationLetter, University, UniversityProgram,
    UniversitySubjectRank,
)
from apps.admissions.student_rubric import academics_score, activities_score
from apps.admissions.test_college_fit import FitFixture

URL = '/api/college-match/'
REASONS_URL = '/api/college-match/reasons/'
AI_ON = override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key')
ESSAY = ' '.join(['On the night the power failed I taught my brother fractions by candlelight.'] * 20)
LETTER = 'In twenty years of teaching I have rarely met a student like her. ' * 6 + 'She rebuilt our robotics club.'
HERE = Path(__file__).resolve().parent


def add_check(student, overall, **essay_fields):
    """A saved Essay Lab check for a new essay of the student (overall None = an unscored check)."""
    essay = Essay.objects.create(student=student, title='Personal statement', content=ESSAY, **essay_fields)
    tab = EssayTab.objects.create(essay=essay, title='Main', content=ESSAY)
    return EssayDepthCheck.objects.create(
        essay=essay, tab=tab, save_seq=0, model='m', overall=overall,
        result={'scored': overall is not None, 'overall': overall, 'summary': 's'},
    )


class MatchFixture(FitFixture):
    """The College Search fixture with QS 2026 Computer Science ranks for its two US universities."""

    def rank(self, university, rank, code='COM02', label='', year=2026):
        return UniversitySubjectRank.objects.create(
            university=university, subject_code=code, rank=rank, rank_label=label, year=year,
        )

    def setUp(self):
        super().setUp()
        # A student who needs a scholarship only sees universities that give aid to students from abroad.
        University.objects.filter(pk__in=[self.mit.pk, self.state.pk]).update(offers_international_aid=True)
        self.rank(self.mit, 1)
        self.rank(self.state, 120)


class RubricTests(FitFixture, APITestCase):
    def test_academics_combine_grades_tests_and_olympiads(self):
        self.ready_profile()
        ctx = fit_context(self.student)
        # GPA 3.8/4 -> 8.75, SAT 1450 -> 7.86: their mean.
        self.assertEqual(ctx['rubric']['academics'], 8.3)
        olympiad = Honor(title='International Mathematical Olympiad, bronze', level='international')
        self.assertEqual(academics_score(ctx, [olympiad]), 9.3)
        # Without a test, grades alone stay at most 8.
        self.assertEqual(academics_score({**ctx, 'sat': None, 'act': None}, []), 8)

    def test_activities_reward_reach_and_time_not_the_number_of_rows(self):
        self.ready_profile()
        for index in range(6):
            Activity.objects.create(student=self.student, name=f'Club {index}', role='Member')
        many_small = fit_context(self.student)['rubric']['activities']
        Activity.objects.filter(student=self.student).delete()
        Honor.objects.create(student=self.student, title='National olympiad winner', level='national')
        Activity.objects.create(
            student=self.student, name='Coding club', role='Founder and president', verified=True,
            start_date=date.today() - timedelta(days=800), hours_per_week=6,
        )
        one_strong = fit_context(self.student)['rubric']['activities']
        self.assertGreater(one_strong, many_small)
        # National honor 0.8 and a two-year verified founder 0.5 x 0.65 x 1.1: 10 x (0.7 x 0.8 + 0.2 x 0.3575).
        self.assertEqual(one_strong, 6.3)
        self.assertEqual(activities_score([]), 0)

    def test_a_title_cannot_beat_time_and_verified_results(self):
        self.ready_profile()
        two_years_ago = date.today() - timedelta(days=730)
        for index in range(5):
            Activity.objects.create(
                student=self.student, name=f'Club {index}', role='President and founder', verified=False,
                start_date=two_years_ago,
            )
        titles = fit_context(self.student)['rubric']['activities']
        Activity.objects.filter(student=self.student).delete()
        Activity.objects.create(
            student=self.student, name='Robotics', role='Member', verified=True, start_date=two_years_ago,
            impact='Our team reached the national final',
        )
        verified = fit_context(self.student)['rubric']['activities']
        self.assertGreater(verified, titles)

    def test_a_title_adds_only_a_little(self):
        from apps.admissions.student_rubric import role_weight

        self.assertLess(role_weight('Founder') - role_weight('Member'), 0.15)
        self.assertGreater(role_weight('Founder'), role_weight('Member'))

    def test_the_rubric_has_no_recommendations_and_no_language(self):
        self.ready_profile()
        self.assertEqual(set(fit_context(self.student)['rubric']), {'academics', 'activities', 'essays'})


class EssaysFactorTests(FitFixture, APITestCase):
    def test_essays_are_unknown_until_a_check_is_scored(self):
        self.ready_profile()
        Essay.objects.create(student=self.student, title='Personal statement', content=ESSAY)
        self.assertIsNone(fit_context(self.student)['rubric']['essays'])
        add_check(self.student, None)
        self.assertIsNone(fit_context(self.student)['rubric']['essays'], 'an unscored check is not a score')

    def test_the_essays_score_is_the_checks_overall_out_of_ten_and_needs_no_provider(self):
        self.ready_profile()
        add_check(self.student, 76)
        with mock.patch.object(ai_providers, 'chat') as post, mock.patch('urllib.request.urlopen') as urlopen:
            rubric = fit_context(self.student)['rubric']
            data = self.client.post(URL).data
        post.assert_not_called()
        urlopen.assert_not_called()
        self.assertEqual(rubric['essays'], 7.6)
        self.assertEqual(data['rubric']['essays'], 7.6)

    def test_the_latest_scored_personal_statement_check_counts(self):
        self.ready_profile()
        add_check(self.student, 60)
        add_check(self.student, 82)
        add_check(self.student, None)
        add_check(self.student, 99, essay_type='supplement')
        self.assertEqual(fit_context(self.student)['rubric']['essays'], 8.2)


class CollegeMatchTests(MatchFixture, APITestCase):
    def match(self):
        response = self.client.post(URL)
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        return response.data

    def test_three_groups_each_card_keeps_its_own_band(self):
        self.ready_profile()
        data = self.match()
        self.assertEqual([(group['band'], group['quota']) for group in data['groups']], [('reach', 3), ('target', 4), ('safety', 3)])
        bands = {group['band']: [row['name'] for row in group['results']] for group in data['groups']}
        self.assertEqual(bands['reach'], [self.mit.name])
        self.assertEqual(bands['safety'], [self.state.name])
        for group in data['groups']:
            self.assertTrue(all(row['fit']['admission_band'] == row['band'] for row in group['results']))
        self.assertEqual(data['groups'][0]['results'][0]['band'], 'far_reach')
        self.assertEqual(data['rubric']['academics'], 8.3)
        self.assertIsNone(data['rubric']['essays'])

    def test_a_card_band_matches_the_university_page_and_the_saved_snapshot(self):
        # No activities (rubric 0) is where a soft-factor-free band and College Search used to disagree:
        # SAT 1300 in a 1200-1400 range is Safety on academics alone but Target once activities count.
        self.ready_profile(sat_score=1300)
        self.assertEqual(fit_context(self.student)['rubric']['activities'], 0)
        cards = [row for group in self.match()['groups'] for row in group['results']]
        self.assertTrue(cards)
        ctx = fit_context(self.student)
        for row in cards:
            university = University.objects.get(pk=row['id'])
            self.assertEqual(row['band'], score_university(university, ctx)['admission_band'], row['name'])
            application = Application.objects.create(student=self.student, university=university, program='CS')
            snapshot = record_chance_snapshot(application)
            self.assertEqual(snapshot.band, row['band'], row['name'])
            self.assertEqual(self.fit(university)['admission_band'], row['band'], row['name'])

    def test_the_student_response_has_no_recommendations_and_no_language(self):
        self.ready_profile()
        RecommendationLetter.objects.create(student=self.student, recommender_name='Teacher', status='submitted', body=LETTER)
        add_check(self.student, 70)
        raw = json.dumps(self.match(), default=str).lower()
        self.assertNotIn('recommendation', raw)
        self.assertNotIn('letter', raw)
        for word in ('grammar', 'fluency', 'spelling'):
            self.assertNotIn(word, raw)
        self.assertNotIn('language', self.match()['rubric'])
        self.assertEqual(set(self.match()['rubric']), {'academics', 'activities', 'essays'})

    def test_students_only_and_a_ready_profile_first(self):
        self.assertEqual(self.client.post(URL).status_code, 400)
        self.assertEqual(self.client.post(URL).data['missing_fields'], ['gpa', 'target_major', 'target_countries'])
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(URL).status_code, 403)

    def test_programs_are_suggested_by_rule_from_the_stated_majors(self):
        self.ready_profile(target_major='Physics, Computer Science')
        UniversityProgram.objects.create(university=self.state, name='BSc Computer Science and AI', canonical_major='Computer Science')
        UniversityProgram.objects.create(university=self.state, name='BSc Data Systems', canonical_major='Computer Science')
        rows = {row['name']: row for group in self.match()['groups'] for row in group['results']}
        names = [program['name'] for program in rows[self.state.name]['suggested_programs']]
        self.assertEqual(len(names), 2, 'at most two programs')
        self.assertTrue(set(names) <= {'BSc Computer Science', 'BSc Computer Science and AI', 'BSc Data Systems'})
        self.assertEqual(rows[self.mit.name]['suggested_programs'], [])

    @AI_ON
    def test_the_default_match_makes_no_ai_call(self):
        self.ready_profile()
        add_check(self.student, 70)
        RecommendationLetter.objects.create(student=self.student, recommender_name='Teacher', status='submitted', body=LETTER)
        with mock.patch.object(ai_providers, 'chat') as post, mock.patch('urllib.request.urlopen') as urlopen, \
                mock.patch.object(ai_budget, 'consume') as consume:
            self.match()
            self.match()
        post.assert_not_called()
        urlopen.assert_not_called()
        consume.assert_not_called()
        self.assertFalse(AiUsageLog.objects.exists())


class NoLanguageScoringTests(TestCase):
    """Naseeb AI never scores language: no college-match code path reads grammar, spelling or fluency."""

    FORBIDDEN = re.compile(r'grammar|spelling|fluency|vocabulary|language_score|\'language\'\s*:', re.IGNORECASE)

    def test_the_scoring_modules_do_not_mention_language_criteria(self):
        sources = {name: (HERE / name).read_text() for name in ('student_rubric.py', 'admission_chance.py')}
        sources['college_match.py'] = (HERE / 'college_match.py').read_text()
        sources['subjects.py'] = (HERE / 'subjects.py').read_text().split('KEYWORDS = ', 1)[0]
        sources['match_reasons.py (facts)'] = (HERE / 'match_reasons.py').read_text().split('SYSTEM = ', 1)[0]
        for name, source in sources.items():
            self.assertIsNone(self.FORBIDDEN.search(source), name)

    def test_the_reasons_prompt_only_forbids_it(self):
        self.assertFalse((HERE / 'rubric_ai.py').exists(), 'the AI essay and letter readers are gone')
        self.assertIn('Never mention essays, recommendation letters, grammar', match_reasons.SYSTEM)


@AI_ON
@override_settings(
    COLLEGE_MATCH_REASONS_DAILY_BUDGET=100, COLLEGE_MATCH_REASONS_SCHOOL_DAILY_BUDGET=100,
    COLLEGE_MATCH_REASONS_USER_DAILY_LIMIT=5,
)
class ReasonsTests(MatchFixture, APITestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.ready_profile()

    def used(self):
        return 5 - ai_budget.user_remaining(match_reasons.FEATURE, self.student_user)

    def ids(self):
        data = self.client.post(URL).data
        return [row['id'] for group in data['groups'] for row in group['results']]

    def gateway(self, lines=None):
        """A fake gateway answering one line per card id found in the request."""
        bodies = []

        def post(body, timeout):
            bodies.append(body)
            cards = json.loads(body['messages'][1]['content'])['cards']
            reasons = lines if lines is not None else {str(card['id']): f'Reason for {card["name"]}.' for card in cards}
            return {'choices': [{'message': {'content': json.dumps({'reasons': reasons})}}], 'usage': {'total_tokens': 10}}

        patch = mock.patch.object(ai_providers, 'chat', side_effect=post)
        patch.bodies = bodies
        return patch

    def test_one_call_writes_a_line_per_card_and_costs_one_unit(self):
        with self.gateway() as post:
            response = self.client.post(REASONS_URL, {'language': 'ru'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(set(response.data['reasons']), {str(pk) for pk in self.ids()})
        self.assertFalse(response.data['cached'])
        self.assertEqual(self.used(), 1)
        body = post.call_args[0][0]
        self.assertEqual((body['model'], body['temperature']), (coach.settings.ESSAY_COACH_MODEL, 0))
        self.assertEqual(body['reasoning_effort'], coach.settings.ESSAY_COACH_REASONING_EFFORT)
        self.assertIn('Russian', body['messages'][0]['content'])
        self.assertEqual(AiUsageLog.objects.get(feature=match_reasons.FEATURE).status, 'ok')

    @override_settings(AI_PROVIDER='claude_cli', APP_ENV='development')
    def test_the_usage_row_names_the_provider_that_ran(self):
        with self.gateway():
            self.assertEqual(self.client.post(REASONS_URL, {'language': 'en'}, format='json').status_code, 200)
        self.assertEqual(AiUsageLog.objects.get(feature=match_reasons.FEATURE).provider, 'claude_cli')

    def test_the_same_list_is_served_from_the_cache(self):
        with self.gateway() as post:
            first = self.client.post(REASONS_URL).data
            second = self.client.post(REASONS_URL).data
        self.assertEqual(post.call_count, 1, 'no second provider call')
        self.assertEqual(self.used(), 1, 'no second unit')
        self.assertEqual(first['reasons'], second['reasons'])
        self.assertTrue(second['cached'])

    def test_a_changed_profile_or_language_is_a_new_list(self):
        with self.gateway() as post:
            self.client.post(REASONS_URL)
            self.client.post(REASONS_URL, {'language': 'uz'}, format='json')
            self.ready_profile(gpa='3.10')
            self.client.post(REASONS_URL)
        self.assertEqual(post.call_count, 3)

    def test_a_failed_call_answers_503_and_gives_the_unit_back(self):
        with mock.patch.object(ai_providers, 'chat', side_effect=urllib.error.URLError('down')):
            response = self.client.post(REASONS_URL)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['code'], 'coach_unavailable')
        self.assertEqual(self.used(), 0)
        self.assertEqual(AiUsageLog.objects.get(feature=match_reasons.FEATURE).status, 'provider_error')
        # Nothing was cached: the next call tries again.
        with self.gateway() as post:
            self.assertEqual(self.client.post(REASONS_URL).status_code, 200)
        self.assertEqual(post.call_count, 1)

    def test_an_answer_missing_a_card_is_a_failure_too(self):
        with self.gateway(lines={'1': 'only one'}):
            response = self.client.post(REASONS_URL)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.used(), 0)

    @override_settings(COLLEGE_MATCH_REASONS_USER_DAILY_LIMIT=1)
    def test_the_daily_limit_refuses_with_503_and_no_provider_call(self):
        with self.gateway() as post:
            self.assertEqual(self.client.post(REASONS_URL).status_code, 200)
            self.ready_profile(gpa='3.10')
            response = self.client.post(REASONS_URL)
        self.assertEqual((response.status_code, response.data['code']), (503, 'coach_resting'))
        self.assertEqual(post.call_count, 1)

    @override_settings(OUTBOUND_AI_ENABLED=False)
    def test_without_outbound_ai_it_answers_503_and_spends_nothing(self):
        with mock.patch.object(ai_providers, 'chat') as post:
            response = self.client.post(REASONS_URL)
        self.assertEqual(response.status_code, 503)
        post.assert_not_called()
        self.assertEqual(self.used(), 0)

    def test_the_model_sees_facts_only_never_essay_letter_or_name(self):
        self.student_user.first_name, self.student_user.last_name = 'Zarina', 'Karimova'
        self.student_user.save()
        self.ready_profile(target_major='Computer Science, Zarina@example.com')
        add_check(self.student, 70)
        RecommendationLetter.objects.create(student=self.student, recommender_name='Teacher', status='submitted', body=LETTER)
        with self.gateway() as post:
            self.assertEqual(self.client.post(REASONS_URL).status_code, 200)
        sent = json.dumps(post.call_args[0][0], ensure_ascii=False).lower()
        for secret in ('candlelight', 'rarely met a student', 'zarina', 'karimova', 'robotics'):
            self.assertNotIn(secret, sent)
        self.assertNotIn('recommendations', sent)
        payload = json.loads(post.call_args[0][0]['messages'][1]['content'])
        self.assertEqual(set(payload['student']['scores_out_of_10']), {'academics'})
        self.assertEqual(payload['student']['budget_usd'], 30000)
        for card in payload['cards']:
            self.assertNotIn('fit_score', card)
            self.assertIn('cost_vs_budget', card)
            self.assertIn('admit_rate_estimated', card)
            self.assertIn('sat_range_min', card)
        mit = next(card for card in payload['cards'] if card['id'] == self.mit.pk)
        self.assertEqual((mit['sat_score'], mit['sat_range_min'], mit['sat_range_max']), (1450, 1520, 1580))

    def test_a_line_with_a_number_not_in_its_facts_is_dropped(self):
        University.objects.filter(pk=self.mit.pk).update(intl_acceptance_rate='12.00')
        ids = self.ids()
        lines = {str(pk): 'A strong fit for your budget.' for pk in ids}
        self.assertNotIn(99, ids)
        lines[str(self.mit.pk)] = 'An acceptance 99% makes this easy.'
        lines[str(self.state.pk)] = 'About 53% of applicants get in.'
        with self.gateway(lines=lines):
            response = self.client.post(REASONS_URL)
        self.assertEqual(response.status_code, 200, response.data)
        reasons = response.data['reasons']
        self.assertEqual(reasons[str(self.mit.pk)], '', 'a made-up number empties the line')
        self.assertEqual(reasons[str(self.state.pk)], 'About 53% of applicants get in.', 'its own admit rate')
        self.assertEqual(self.used(), 1)

    def test_numbers_in_the_card_or_student_facts_are_kept(self):
        from apps.admissions.match_reasons import validate

        item = {'id': 7, 'admit_rate': 12.0, 'cost_usd': 25000, 'subject_rank_qs_2026': '201-250'}
        student = {'budget_usd': 30000, 'scores_out_of_10': {'academics': 8.3}}
        raw = {'reasons': {'7': 'At 12% admit, #201 in QS 2026, $25,000 a year within $30,000; academics 8.3.'}}
        self.assertEqual(validate(raw, [item], student)['7'], raw['reasons']['7'])
        self.assertEqual(validate({'reasons': {'7': 'Ranked #5.'}}, [item], student)['7'], '')
        with self.assertRaises(ValueError):
            validate({'reasons': {}}, [item], student)

    def test_reasoning_effort_is_dropped_once_when_the_gateway_rejects_it(self):
        calls = []

        def urlopen(request, timeout=None):
            body = json.loads(request.data.decode('utf-8'))
            calls.append(body)
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    'https://gw', 400, 'Bad', {}, io.BytesIO(b'{"error": "Unsupported parameter: reasoning_effort"}'))
            cards = json.loads(body['messages'][1]['content'])['cards']
            payload = {'choices': [{'message': {'content': json.dumps({'reasons': {str(c['id']): 'Fits.' for c in cards}})}}]}
            response = mock.MagicMock()
            response.read.return_value = json.dumps(payload).encode()
            response.__enter__.return_value = response
            return response

        with mock.patch('urllib.request.urlopen', side_effect=urlopen):
            response = self.client.post(REASONS_URL)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('reasoning_effort', calls[0])
        self.assertNotIn('reasoning_effort', calls[1])
        self.assertEqual(self.used(), 1)

    def test_students_only(self):
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(REASONS_URL).status_code, 403)


class MigrationGraphTests(TestCase):
    def test_admissions_has_exactly_one_leaf(self):
        loader = MigrationLoader(connection)
        leaves = [node for node in loader.graph.leaf_nodes() if node[0] == 'admissions']
        self.assertEqual(len(leaves), 1, leaves)
