"""Recommendation letter Ideas and Check depth: access, anonymized prompt, bands, re-check rules, refunds."""
import importlib
import json
import urllib.error
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from . import ai_budget, letter_coach
from .essay_lab import coach
from .models import AiUsageLog, Honor, RecommendationLetter, RecommendationLetterCheck
from .test_essay_lab import FakeGateway
from .test_recommendation_letters import SUGGEST_URL, LetterFixture, gateway_response

BODY = (
    'I have taught Malika Karimova physics for three years. In March she stayed after class to rebuild the '
    'pendulum rig that three groups had given up on. She wrote down every failed attempt in a green notebook. '
    'When the grade ten class asked why she kept going she said that a wrong result is still a result. '
    'Malika Karimova is among the five strongest students I have taught in twelve years. '
    'She explained the rig to a younger boy twice without being asked and without any hurry in her voice. '
    'I recommend her without reservation. Reach me at counselor@example.com.'
)
SCORES = {'evidence': 3, 'insight': 3, 'context': 3, 'structure': 3, 'voice': 3}  # overall 67
SCORE_REPLY = {
    'scores': SCORES, 'summary': 'A warm letter about patience.',
    'strengths': [{'criterion': 'evidence', 'quote': 'In March she stayed after class', 'text': 'A real moment.'}],
    'suggestions': ['What did you not see?', 'Compared with how many students?'],
}
NOTES = {'notes': [
    {'criterion': 'context', 'quote': '[Student] [Student] is among the five strongest students I have taught in twelve years.',
     'question': 'Which students were you comparing her with?', 'context': ''},
    {'criterion': 'evidence', 'quote': 'She wrote down every failed attempt in a green notebook.',
     'question': 'What did you read in that notebook yourself?', 'context': ''},
]}
URL = '/api/recommendations'


class LetterCheckCase(LetterFixture, APITestCase):
    def setUp(self):
        super().setUp()
        self.student_user.first_name, self.student_user.last_name = 'Malika', 'Karimova'
        self.student_user.save(update_fields=['first_name', 'last_name'])
        self.letter = RecommendationLetter.objects.create(
            student=self.student, recommender_name='Base Counselor', recommender_title='School counselor',
            relationship='Taught her physics', status='drafting', body=BODY,
        )
        self.client.force_authenticate(self.counselor)

    def reload(self):
        self.letter.refresh_from_db()
        return self.letter

    def check(self, gateway=None, user=None, letter=None):
        gateway = gateway or FakeGateway(score=SCORE_REPLY)
        letter = letter or self.reload()
        if user is not None:
            self.client.force_authenticate(user)
        with mock.patch('urllib.request.urlopen', side_effect=gateway):
            response = self.client.post(
                f'{URL}/{letter.pk}/depth-check/', {'base_updated_at': letter.updated_at.isoformat()}, format='json')
        return response, gateway

    def set_body(self, text, **fields):
        RecommendationLetter.objects.filter(pk=self.letter.pk).update(body=text, **fields)

    def left(self):
        return ai_budget.user_remaining('recommendation_letter_check', self.counselor)


AI_ON = dict(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key', REC_LETTER_CHECK_MIN_INTERVAL_SECONDS=0)


@override_settings(**AI_ON)
class LetterCheckAccessTests(LetterCheckCase):
    def test_the_counselor_of_the_student_can_check_and_read(self):
        response, _ = self.check()
        self.assertEqual(response.status_code, 200, response.data)
        latest = self.client.get(f'{URL}/{self.letter.pk}/depth-check/latest/')
        self.assertEqual((latest.status_code, latest.data['id']), (200, response.data['id']))

    def test_another_schools_counselor_gets_nothing(self):
        response, gateway = self.check(user=self.counselor_b)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(gateway.bodies, [])
        self.assertEqual(self.client.get(f'{URL}/{self.letter.pk}/depth-check/latest/').status_code, 404)
        self.assertEqual(self.client.patch(f'{URL}/{self.letter.pk}/depth-check/1/notes/',
                                           {'note_id': 'n1', 'state': 'done'}, format='json').status_code, 404)

    def test_a_student_is_refused_even_for_a_shared_letter(self):
        first, _ = self.check()
        RecommendationLetter.objects.filter(pk=self.letter.pk).update(shared_with_student=True)
        self.client.force_authenticate(self.student_user)
        letter = self.reload()
        with mock.patch('urllib.request.urlopen') as urlopen:
            post = self.client.post(f'{URL}/{letter.pk}/depth-check/',
                                    {'base_updated_at': letter.updated_at.isoformat()}, format='json')
        urlopen.assert_not_called()
        self.assertEqual(post.status_code, 403)
        self.assertEqual(self.client.get(f'{URL}/{letter.pk}/depth-check/latest/').status_code, 403)
        self.assertEqual(self.client.patch(f'{URL}/{letter.pk}/depth-check/{first.data["id"]}/notes/',
                                           {'note_id': 'n1', 'state': 'done'}, format='json').status_code, 403)

    def test_other_roles_that_cannot_write_the_letter_are_refused(self):
        for user in (self.teacher, self.organization, self.parent):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(f'{URL}/{self.letter.pk}/depth-check/latest/').status_code, 403, user.role)

    def test_anonymous_is_refused(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(f'{URL}/{self.letter.pk}/depth-check/latest/').status_code, (401, 403))

    def test_latest_is_204_without_a_check(self):
        self.assertEqual(self.client.get(f'{URL}/{self.letter.pk}/depth-check/latest/').status_code, 204)


@override_settings(**AI_ON)
class LetterCheckResultTests(LetterCheckCase):
    def test_the_prompt_has_no_name_and_no_profile_and_no_contact_details(self):
        Honor.objects.create(student=self.student, title='Secret olympiad prize', level='national')
        self.student.application_profile = {'personal_story': 'A private story about the family farm.'}
        self.student.save()
        response, gateway = self.check(FakeGateway(score=SCORE_REPLY, notes=NOTES))
        self.assertEqual(response.status_code, 200, response.data)
        for body in gateway.bodies:
            sent = json.dumps(body, ensure_ascii=False)
            self.assertIn('[Student]', sent)
            for private in ('Malika', 'Karimova', 'Secret olympiad prize', 'family farm', 'counselor@example.com'):
                self.assertNotIn(private, sent)
        self.assertEqual(gateway.steps, ['score', 'notes'])

    def test_shape_bands_and_notes_quote_the_real_letter(self):
        response, _ = self.check(FakeGateway(score=SCORE_REPLY, notes=NOTES))
        data = response.data
        self.assertEqual(set(data), {
            'id', 'created_at', 'model', 'result', 'source', 'text_fingerprint', 'note_states', 'overall',
            'previous_overall', 'checks_left', 'daily_limit', 'reused', 'input_hash', 'current_input_hash'})
        self.assertNotIn('letter_text', json.dumps(data))
        self.assertEqual((data['source'], data['overall'], data['reused'], data['previous_overall']), ('ai', 67, False, None))
        self.assertEqual((data['checks_left'], data['daily_limit']), (4, 5))
        self.assertEqual(data['input_hash'], data['current_input_hash'])
        result = data['result']
        self.assertEqual(set(result['scores']), set(SCORES))
        quotes = [note['quote'] for note in result['notes']]
        # [Student] in the model's quote is mapped back to the real name, so the note can be highlighted.
        self.assertEqual(quotes[0], 'Malika Karimova is among the five strongest students I have taught in twelve years.')
        self.assertTrue(all(coach.normalize(quote) in coach.normalize(BODY) for quote in quotes))
        self.assertEqual([note['id'] for note in result['notes']], ['n1', 'n2'])
        self.assertTrue(all(note['priority'] for note in result['notes']))
        stored = RecommendationLetterCheck.objects.get()
        self.assertEqual((stored.author, stored.letter_text, stored.text_fingerprint), (self.counselor, BODY, coach.text_fingerprint(BODY)))

    def test_a_note_whose_quote_cannot_be_found_in_the_real_letter_is_dropped(self):
        notes = {'notes': [
            {'criterion': 'context', 'quote': '[Student] is a star pupil.', 'question': 'Who says so, and since when?', 'context': ''},
            NOTES['notes'][1],
        ]}
        response, _ = self.check(FakeGateway(score=SCORE_REPLY, notes=notes))
        self.assertEqual([(note['id'], note['quote']) for note in response.data['result']['notes']],
                         [('n1', 'She wrote down every failed attempt in a green notebook.')])

    def test_a_low_score_locks_the_notes_and_makes_one_call(self):
        low = {**SCORE_REPLY, 'scores': {key: 1 for key in SCORES}}
        response, gateway = self.check(FakeGateway(score=low))
        self.assertEqual((response.data['overall'], response.data['result']['notes_locked']), (0, True))
        self.assertEqual(gateway.steps, ['score'])

    def test_unknown_criterion_keys_from_the_essay_rubric_are_dropped(self):
        notes = {'notes': [{**NOTES['notes'][1], 'criterion': 'reflection'}]}
        response, _ = self.check(FakeGateway(score=SCORE_REPLY, notes=notes))
        self.assertEqual(response.data['result']['notes'], [])

    def test_each_call_is_recorded_under_the_letter_check_feature(self):
        self.check(FakeGateway(score=SCORE_REPLY, notes=NOTES))
        self.assertEqual(list(AiUsageLog.objects.values_list('feature', 'status')),
                         [('recommendation_letter_check', 'ok')] * 2)

    def test_weights_come_from_the_rubric_file(self):
        self.assertEqual(coach.CRITERIA['recommendation_letter'],
                         {'evidence': 40, 'insight': 25, 'context': 20, 'structure': 10, 'voice': 5})
        self.assertEqual(coach.compute_overall('recommendation_letter', {key: 4 for key in SCORES}), 100)


@override_settings(**AI_ON)
class LetterRecheckTests(LetterCheckCase):
    def first(self, notes=NOTES):
        response, _ = self.check(FakeGateway(score=SCORE_REPLY, notes=notes))
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_same_text_is_reused_without_a_call_or_budget(self):
        first = self.first()
        usage, left = AiUsageLog.objects.count(), self.left()
        self.set_body(BODY.upper().replace(' ', '  '))
        response, gateway = self.check(FakeGateway())
        self.assertEqual(gateway.bodies, [])
        self.assertEqual((response.status_code, response.data['reused'], response.data['id']), (200, True, first['id']))
        self.assertEqual((RecommendationLetterCheck.objects.count(), AiUsageLog.objects.count(), self.left()), (1, usage, left))
        self.assertFalse(self.client.get(f'{URL}/{self.letter.pk}/depth-check/latest/').data['reused'])

    def test_open_notes_block_a_changed_letter(self):
        self.first()
        self.set_body(BODY + ' She also tutors two classmates every Friday afternoon after practice.')
        response, gateway = self.check(FakeGateway())
        self.assertEqual((response.status_code, response.data['code'], response.data['open']), (409, 'notes_open', 2))
        self.assertEqual(gateway.bodies, [])
        self.assertEqual(self.left(), 4)

    def resolve_all(self, check_id):
        for note_id in ('n1', 'n2'):
            response = self.client.patch(f'{URL}/{self.letter.pk}/depth-check/{check_id}/notes/',
                                         {'note_id': note_id, 'state': 'done'}, format='json')
            self.assertEqual(response.status_code, 200, response.data)

    def test_a_small_change_is_refused_and_a_big_one_runs(self):
        first = self.first()
        self.resolve_all(first['id'])
        self.set_body(BODY.replace('physics', 'physics lessons'))  # 1 word
        response, gateway = self.check(FakeGateway())
        self.assertEqual((response.status_code, response.data['code'], response.data['changed'], response.data['min_words']),
                         (409, 'too_small_change', 1, 3))
        self.assertEqual(gateway.bodies, [])
        self.set_body(BODY + ' She also tutors two classmates every Friday afternoon after practice.')
        response, gateway = self.check(FakeGateway(score=SCORE_REPLY))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['previous_overall'], response.data['reused'], len(gateway.bodies)), (67, False, 2))
        self.assertEqual(RecommendationLetterCheck.objects.count(), 2)

    def test_another_input_runs_a_new_check_for_the_same_text(self):
        first = self.first()
        RecommendationLetter.objects.filter(pk=self.letter.pk).update(relationship='Her form tutor')
        response, gateway = self.check(FakeGateway(score=SCORE_REPLY))
        self.assertEqual((response.status_code, response.data['reused'], len(gateway.bodies)), (200, False, 2))
        self.assertNotEqual(response.data['input_hash'], first['input_hash'])
        with override_settings(ESSAY_COACH_MODEL='other/model'):
            self.assertNotEqual(letter_coach.input_hash(self.reload(), coach.current_model()), response.data['input_hash'])

    def test_the_input_hash_ignores_the_body_but_not_title_or_relationship(self):
        letter = self.reload()
        before = letter_coach.input_hash(letter, 'm')
        letter.body = 'Something else entirely.'
        self.assertEqual(letter_coach.input_hash(letter, 'm'), before)
        letter.recommender_title = 'Head of physics'
        self.assertNotEqual(letter_coach.input_hash(letter, 'm'), before)

    def test_only_the_last_ten_checks_are_kept(self):
        for index in range(11):
            self.set_body(f'{BODY} Alpha{index}x beta{index}y gamma{index}z delta{index}w epsilon{index}v.')
            cache.clear()
            response, _ = self.check(FakeGateway(score=SCORE_REPLY))
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(RecommendationLetterCheck.objects.count(), 10)

    @override_settings(REC_LETTER_CHECK_RECHECK_PER_MINUTE=2)
    def test_the_cheap_per_minute_guard_comes_first(self):
        self.first()
        statuses = [self.check(FakeGateway())[0].status_code for _ in range(3)]
        self.assertEqual(statuses, [200, 429, 429])  # the first guard slot went to the check itself


@override_settings(**AI_ON)
class LetterCheckGuardTests(LetterCheckCase):
    def test_a_stale_base_is_refused(self):
        letter = self.reload()
        stale = letter.updated_at.isoformat()
        RecommendationLetter.objects.filter(pk=letter.pk).update(updated_at=letter.updated_at.replace(year=2020))
        with mock.patch('urllib.request.urlopen') as urlopen:
            response = self.client.post(f'{URL}/{letter.pk}/depth-check/', {'base_updated_at': stale}, format='json')
        urlopen.assert_not_called()
        self.assertEqual((response.status_code, response.data['code']), (409, 'stale'))

    def test_base_updated_at_is_required_and_an_empty_letter_is_refused(self):
        self.assertEqual(self.client.post(f'{URL}/{self.letter.pk}/depth-check/', {}, format='json').status_code, 400)
        self.set_body('   ')
        response, _ = self.check(FakeGateway())
        self.assertEqual((response.status_code, response.data['code']), (400, 'empty_letter'))

    def test_a_failed_check_is_free(self):
        before = self.left()
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('down')) as urlopen:
            response = self.client.post(f'{URL}/{self.letter.pk}/depth-check/',
                                        {'base_updated_at': self.reload().updated_at.isoformat()}, format='json')
        self.assertEqual((response.status_code, response.data['code']), (503, 'coach_unavailable'))
        self.assertEqual(urlopen.call_count, 1)  # no paid retry
        self.assertEqual((self.left(), RecommendationLetterCheck.objects.count()), (before, 0))
        self.assertEqual(AiUsageLog.objects.get().feature, 'recommendation_letter_check')

    @override_settings(ESSAY_COACH_TOTAL_SECONDS=90, ESSAY_COACH_TIMEOUT_SECONDS=40)
    def test_step_two_gets_the_time_left_and_an_overrun_is_a_free_failure(self):
        for elapsed, expect in ((70, 20), (88, None)):
            cache.clear()
            RecommendationLetterCheck.objects.all().delete()
            clock, timeouts, inner = {'now': 0.0}, [], FakeGateway(score=SCORE_REPLY)

            def urlopen(request, timeout=None):
                timeouts.append(timeout)
                reply = inner(request, timeout)
                clock['now'] = elapsed if len(timeouts) == 1 else clock['now']
                return reply

            left = self.left()
            with mock.patch.object(coach, 'time', SimpleNamespace(monotonic=lambda: clock['now'])):
                response, _ = self.check(urlopen)
            if expect:
                self.assertEqual((response.status_code, timeouts), (200, [40, expect]))
            else:
                self.assertEqual((response.status_code, len(timeouts)), (503, 1))
                self.assertEqual((self.left(), RecommendationLetterCheck.objects.count()), (left, 0))

    def test_the_connection_is_released_before_each_provider_call(self):
        events, inner = [], FakeGateway(score=SCORE_REPLY, notes=NOTES)

        def urlopen(request, timeout=None):
            events.append('call')
            return inner(request, timeout)

        with mock.patch('apps.admissions.views.records.release_db_connection', side_effect=lambda: events.append('release')):
            response, _ = self.check(urlopen)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(events, ['release', 'call', 'release', 'call'])

    @override_settings(REC_LETTER_CHECK_USER_DAILY_LIMIT=1)
    def test_the_daily_limit_and_checks_left(self):
        first, _ = self.check()
        self.assertEqual(first.data['checks_left'], 0)
        self.set_body(BODY + ' A new line about her tutoring every Friday afternoon at the school.')
        response, gateway = self.check(FakeGateway())
        self.assertEqual((response.status_code, response.data['code']), (503, 'coach_resting'))
        self.assertEqual(gateway.bodies, [])
        self.assertEqual(AiUsageLog.objects.filter(status='budget_refused').count(), 1)

    @override_settings(REC_LETTER_CHECK_DAILY_BUDGET=0)
    def test_a_zero_platform_budget_turns_checks_off(self):
        response, gateway = self.check(FakeGateway())
        self.assertEqual((response.status_code, response.data['code']), (503, 'coach_resting'))
        self.assertEqual(gateway.bodies, [])

    @override_settings(OUTBOUND_AI_ENABLED=False)
    def test_the_master_switch_off_means_no_check_and_no_cost(self):
        left = self.left()
        response, gateway = self.check(FakeGateway())
        self.assertEqual((response.status_code, response.data['code']), (503, 'coach_unavailable'))
        self.assertEqual((gateway.bodies, self.left(), RecommendationLetterCheck.objects.count()), ([], left, 0))

    def test_the_essay_coach_budget_is_separate(self):
        self.check()
        self.assertEqual(ai_budget.user_remaining('essay_coach', self.counselor), 5)


@override_settings(**AI_ON)
class LetterNoteStateTests(LetterCheckCase):
    def patch(self, check_id, note_id, state):
        return self.client.patch(f'{URL}/{self.letter.pk}/depth-check/{check_id}/notes/',
                                 {'note_id': note_id, 'state': state}, format='json')

    def test_states_and_open_again(self):
        check, _ = self.check(FakeGateway(score=SCORE_REPLY, notes=NOTES))
        check_id = check.data['id']
        for state in ('done', 'dismissed', 'gone'):
            self.assertEqual(self.patch(check_id, 'n1', state).data['note_states'], {'n1': state})
        self.assertEqual(self.patch(check_id, 'n2', 'done').data['note_states'], {'n1': 'gone', 'n2': 'done'})
        self.assertEqual(self.patch(check_id, 'n1', 'open').data['note_states'], {'n2': 'done'})
        self.assertEqual(self.client.get(f'{URL}/{self.letter.pk}/depth-check/latest/').data['note_states'], {'n2': 'done'})

    def test_bad_input(self):
        check, _ = self.check(FakeGateway(score=SCORE_REPLY, notes=NOTES))
        check_id = check.data['id']
        self.assertEqual(self.patch(check_id, 'n1', 'maybe').status_code, 400)
        unknown = self.patch(check_id, 'n9', 'done')
        self.assertEqual((unknown.status_code, unknown.data['code']), (400, 'unknown_note'))
        self.assertEqual(self.patch(check_id + 100, 'n1', 'done').status_code, 404)

    def test_a_check_of_another_letter_is_not_reachable(self):
        check, _ = self.check(FakeGateway(score=SCORE_REPLY, notes=NOTES))
        other = RecommendationLetter.objects.create(student=self.student, recommender_name='Other', body='x')
        response = self.client.patch(f'{URL}/{other.pk}/depth-check/{check.data["id"]}/notes/',
                                     {'note_id': 'n1', 'state': 'done'}, format='json')
        self.assertEqual(response.status_code, 404)


class LetterMigrationTests(LetterCheckCase):
    def test_the_migration_is_additive_and_follows_0093(self):
        migration = importlib.import_module('apps.admissions.migrations.0094_recommendation_letter_check').Migration
        self.assertIn(('admissions', '0093_essay_depth_check_input_hash'), migration.dependencies)
        self.assertEqual([type(op).__name__ for op in migration.operations], ['CreateModel'])

    def test_the_letter_text_is_not_a_serializer_field(self):
        from .serializers import LetterCheckSerializer

        self.assertNotIn('letter_text', LetterCheckSerializer.Meta.fields)
        self.assertNotIn('letter', LetterCheckSerializer.Meta.fields)


class LetterSuggestAiFlagTests(LetterCheckCase):
    def suggest(self, **payload):
        return self.client.post(SUGGEST_URL, {'student': self.student.id, 'draft': '', **payload}, format='json')

    @override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key', REC_LETTER_FACTS_PER_MINUTE=1000)
    def test_facts_only_makes_no_gateway_call_and_costs_nothing(self):
        Honor.objects.create(student=self.student, title='Regional olympiad bronze', level='regional')
        with mock.patch('urllib.request.urlopen') as urlopen:
            for payload in ({}, {'ai': False}):
                response = self.suggest(**payload)
                self.assertEqual((response.status_code, response.data['source']), (200, 'profile'))
                self.assertIn('Regional olympiad bronze', [item.get('title') for item in response.data['suggestions']])
        urlopen.assert_not_called()
        self.assertEqual(AiUsageLog.objects.count(), 0)
        self.assertEqual(ai_budget.user_remaining('recommendation_letter', self.counselor), 20)

    @override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key', REC_LETTER_SUGGEST_MIN_INTERVAL_SECONDS=0)
    def test_ai_true_counts_the_budget_and_returns_ai_left(self):
        answer = {'suggestions': [{'kind': 'idea', 'text': 'Mention the pendulum rig.'}]}
        with mock.patch('urllib.request.urlopen', return_value=gateway_response(json.dumps(answer))) as urlopen:
            response = self.suggest(ai=True)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual((response.data['source'], response.data['ai_left'], response.data['ai_limit'], response.data['ai_available']), ('ai', 19, 20, True))
        self.assertEqual(ai_budget.user_remaining('recommendation_letter', self.counselor), 19)

    @override_settings(OUTBOUND_AI_ENABLED=False, AI_GATEWAY_API_KEY='test-key', REC_LETTER_SUGGEST_MIN_INTERVAL_SECONDS=0)
    def test_master_switch_off_gives_facts_only_even_when_ai_is_asked(self):
        Honor.objects.create(student=self.student, title='Regional olympiad bronze', level='regional')
        with mock.patch('urllib.request.urlopen') as urlopen:
            response = self.suggest(ai=True)
        urlopen.assert_not_called()
        self.assertEqual((response.status_code, response.data['source'], response.data['ai_left']), (200, 'profile', 20))
        self.assertFalse(response.data['ai_available'])
        self.assertIn('Regional olympiad bronze', [item.get('title') for item in response.data['suggestions']])

    @override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key', REC_LETTER_SUGGEST_MIN_INTERVAL_SECONDS=60,
                       REC_LETTER_FACTS_PER_MINUTE=1000)
    def test_facts_requests_use_the_generous_throttle_not_the_ai_one(self):
        clock = mock.Mock(time=mock.Mock(return_value=1000.0))
        with mock.patch('apps.users.throttles.time', clock):
            self.assertEqual([self.suggest().status_code for _ in range(5)], [200] * 5)
            with mock.patch('urllib.request.urlopen', return_value=gateway_response('{"suggestions": []}')):
                self.assertEqual(self.suggest(ai=True).status_code, 200)
                self.assertEqual(self.suggest(ai=True).status_code, 429)

    def test_the_default_user_limit_is_20(self):
        from django.conf import settings

        self.assertEqual(settings.REC_LETTER_AI_USER_DAILY_LIMIT, 20)
        self.assertEqual(settings.REC_LETTER_CHECK_USER_DAILY_LIMIT, 5)
