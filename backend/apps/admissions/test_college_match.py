"""The AI college match: the student's rubric, the AI reading of essays and letters, the balanced list."""
from datetime import date, timedelta
from unittest import mock

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.admissions import rubric_ai
from apps.admissions.college_search import fit_context
from apps.admissions.models import Activity, Essay, Honor, RecommendationLetter, StudentRubricScore
from apps.admissions.student_rubric import academics_score, activities_score
from apps.admissions.test_college_fit import FitFixture

URL = '/api/college-match/'
AI_ON = override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key')
ESSAY = ' '.join(['On the night the power failed I taught my brother fractions by candlelight.'] * 20)
LETTER = 'In twenty years of teaching I have rarely met a student like her. ' * 6 + 'She rebuilt our robotics club.'


def essay_reading(**values):
    return {
        'insight': 8, 'specificity': 8, 'structure': 7, 'language': 6, 'has_concrete_episode': True,
        'quotes': ['I taught my brother fractions by candlelight'], 'rationale': 'Specific and reflective.', **values,
    }


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

    def test_activities_reward_reach_role_and_time_not_the_number_of_rows(self):
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
        # National honor 0.8 and a two-year founder 0.5: 10 x (0.7 x 0.8 + 0.2 x 0.5).
        self.assertEqual(one_strong, 6.6)
        self.assertEqual(activities_score([]), 0)

    def test_essays_and_letters_are_unknown_until_ai_reads_them(self):
        self.ready_profile()
        Essay.objects.create(student=self.student, title='Personal statement', content=ESSAY)
        rubric = fit_context(self.student)['rubric']
        self.assertIsNone(rubric['essays'])
        self.assertIsNone(rubric['recommendations'])


class EssayRulesTests(APITestCase):
    def test_criteria_are_weighted_and_capped_by_the_rules(self):
        score, details = rubric_ai.essay_score(essay_reading(), ESSAY)
        self.assertEqual(score, round(0.35 * 8 + 0.35 * 8 + 0.2 * 7 + 0.1 * 6, 1))
        self.assertEqual(details['quotes'], ['i taught my brother fractions by candlelight'])
        self.assertEqual(rubric_ai.essay_score(essay_reading(has_concrete_episode=False), ESSAY)[0], 5)
        # A quote that is not in the essay is dropped; with none left there is no score.
        self.assertEqual(rubric_ai.essay_score(essay_reading(quotes=['words the student never wrote']), ESSAY), (None, {}))
        with self.assertRaises(ValueError):
            rubric_ai.essay_score(essay_reading(insight='high'), ESSAY)

    def test_letters_score_by_comparison_and_need_an_anecdote(self):
        reading = {'comparison': 'top_few_in_career', 'has_specific_anecdote': True, 'quotes': ['rarely met a student like her']}
        self.assertEqual(rubric_ai.letter_score(reading, LETTER)[0], 9.5)
        self.assertEqual(rubric_ai.letter_score({**reading, 'has_specific_anecdote': False}, LETTER)[0], 5)
        self.assertEqual(rubric_ai.letter_score({**reading, 'comparison': 'generic'}, LETTER)[0], 4)
        with self.assertRaises(ValueError):
            rubric_ai.letter_score({**reading, 'comparison': 'genius'}, LETTER)


class CollegeMatchTests(FitFixture, APITestCase):
    def match(self):
        response = self.client.post(URL)
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        return response.data

    def test_a_balanced_list_grouped_by_band(self):
        self.ready_profile()
        data = self.match()
        self.assertEqual([group['band'] for group in data['groups']], ['far_reach', 'reach', 'target', 'safety'])
        bands = {group['band']: [row['name'] for row in group['results']] for group in data['groups']}
        self.assertEqual(bands['far_reach'], [self.mit.name])
        self.assertEqual(set(bands['safety']), {self.state.name, self.unranked.name})
        for group in data['groups']:
            self.assertLessEqual(len(group['results']), group['quota'])
            self.assertTrue(all(row['fit']['admission_band'] == group['band'] for row in group['results']))
        self.assertEqual(data['rubric']['academics'], 8.3)
        self.assertFalse(data['ai_scoring'])

    def test_the_best_fit_comes_first_within_a_band(self):
        self.ready_profile()
        for index in range(5):
            from apps.admissions.models import University
            University.objects.create(name=f'Open College {index}', country='Germany', acceptance_rate='80.00')
        safety = next(group for group in self.match()['groups'] if group['band'] == 'safety')
        self.assertEqual(len(safety['results']), 3)
        scores = [row['fit']['match_score'] for row in safety['results']]
        self.assertEqual(scores, sorted(scores, reverse=True))
        # US is the target country: Ohio State outranks the German colleges.
        self.assertEqual(safety['results'][0]['name'], self.state.name)

    def test_students_only_and_a_ready_profile_first(self):
        self.assertEqual(self.client.post(URL).status_code, 400)
        self.assertEqual(self.client.post(URL).data['missing_fields'], ['gpa', 'target_major', 'target_countries'])
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.client.post(URL).status_code, 403)

    def test_without_outbound_ai_nothing_is_sent(self):
        self.ready_profile()
        Essay.objects.create(student=self.student, title='Personal statement', content=ESSAY)
        with mock.patch.object(rubric_ai, 'request_reading') as reading:
            self.match()
        reading.assert_not_called()
        self.assertFalse(StudentRubricScore.objects.exists())


@AI_ON
class AiScoringTests(FitFixture, APITestCase):
    def setUp(self):
        super().setUp()
        self.ready_profile()
        self.essay = Essay.objects.create(student=self.student, title='Personal statement', content=ESSAY)
        RecommendationLetter.objects.create(
            student=self.student, recommender_name='Teacher', status='submitted', body=LETTER,
        )

    def readings(self, prompt, text):
        if prompt == rubric_ai.ESSAY_PROMPT:
            return essay_reading()
        return {'comparison': 'top_5_percent', 'has_specific_anecdote': True, 'quotes': ['She rebuilt our robotics club']}

    def test_each_text_is_read_once_and_feeds_the_rubric(self):
        with mock.patch.object(rubric_ai, 'request_reading', side_effect=self.readings) as reading:
            data = self.client.post(URL).data
            self.client.post(URL)
        self.assertEqual(reading.call_count, 2, 'one essay and one letter, read once each')
        self.assertTrue(data['ai_scoring'])
        self.assertEqual(data['rubric']['essays'], 7.6)
        self.assertEqual(data['rubric']['recommendations'], 8.5)

    def test_a_changed_essay_is_read_again(self):
        with mock.patch.object(rubric_ai, 'request_reading', side_effect=self.readings) as reading:
            self.client.post(URL)
            self.essay.content = ESSAY + ' I still keep the candle on my desk.'
            self.essay.save()
            self.client.post(URL)
        self.assertEqual(reading.call_count, 3, 'only the essay is read again')
        self.assertEqual(StudentRubricScore.objects.get(factor='essays').input_hash, rubric_ai.input_hash([self.essay.content]))

    def test_a_failed_reading_leaves_the_score_unknown(self):
        with mock.patch.object(rubric_ai, 'request_reading', side_effect=ValueError('bad json')):
            data = self.client.post(URL).data
        self.assertIsNone(data['rubric']['essays'])
        self.assertFalse(StudentRubricScore.objects.exists())
