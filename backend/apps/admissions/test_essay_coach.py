"""Essay Coach v2: scoring formula, bands, two-step calls, dedup, re-check rules, note states."""

import hashlib
import io
import json
import random
import re
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from rest_framework import status

from . import ai_budget
from .essay_lab import coach
from .models import AiUsageLog, EssayCheckpoint, EssayDepthCheck, EssayTab
from .test_essay_lab import (
    BASE, ESSAY_TEXT, LONG_TEXT, SCORE_REPLY, EssayLabTestCase, FakeGateway, gateway_response, make_doc,
)

RUBRICS = Path(__file__).parent / 'essay_lab' / 'rubrics'
PS_KEYS = ('reflection', 'specificity', 'voice', 'structure', 'prompt_fit')


def scores(value=None, **overrides):
    result = {key: value or 1 for key in PS_KEYS}
    result.update(overrides)
    return result


def score_reply(**kwargs):
    return {'scores': scores(**kwargs), 'summary': 'About bread.', 'strengths': [],
            'suggestions': ['One thing to try.', 'Another thing to try.']}


class FormulaTests(EssayLabTestCase):
    def test_overall_formula(self):
        self.assertEqual(coach.compute_overall('personal_statement', scores(1)), 0)
        self.assertEqual(coach.compute_overall('personal_statement', scores(4)), 100)
        self.assertEqual(coach.compute_overall('supplement', scores(1)), 0)
        self.assertEqual(coach.compute_overall('supplement', scores(4)), 100)
        # 2*(30*2 + 25*2 + 20*2 + 15*1 + 10*2) = 370 -> (370+3)//6
        self.assertEqual(coach.compute_overall(
            'personal_statement', scores(3, structure=2)), (2 * (30 * 2 + 25 * 2 + 20 * 2 + 15 + 10 * 2) + 3) // 6)

    def test_weights_match_the_rubric_tables_and_sum_to_100(self):
        self.assertEqual(coach.CRITERIA['personal_statement'],
                         {'reflection': 30, 'specificity': 25, 'voice': 20, 'structure': 15, 'prompt_fit': 10})
        self.assertEqual(coach.CRITERIA['supplement'],
                         {'prompt_fit': 30, 'reflection': 25, 'specificity': 20, 'voice': 15, 'structure': 10})
        for filename, rubric in (('personal_statement.md', 'personal_statement'), ('supplemental_essay.md', 'supplement')):
            text = (RUBRICS / filename).read_text(encoding='utf-8')
            table = text.split('## Criteria and weights', 1)[1].split('###', 1)[0]
            rows = re.findall(r'^\|\s*`(\w+)`\s*\|.*?\|\s*(\d+)\s*\|\s*$', table, re.MULTILINE)
            self.assertEqual(len(rows), 5)
            self.assertEqual(sum(int(weight) for _, weight in rows), 100)
            self.assertEqual({key: int(weight) for key, weight in rows}, coach.RUBRIC_WEIGHTS[rubric])
            self.assertEqual(sum(coach.CRITERIA[rubric].values()), 100)

    def test_note_cap_by_band_and_words(self):
        for overall, cap in ((0, 0), (50, 0), (51, 5), (60, 5), (61, 8), (70, 8), (71, 12), (80, 12), (81, 25),
                             (100, 25)):
            self.assertEqual(coach.notes_cap(overall, 10000), cap, overall)
        self.assertEqual(coach.notes_cap(None, 10000), 8)
        # one note per 25 words: a 150-word supplement gets at most 6 whatever its score
        self.assertEqual(coach.notes_cap(100, 150), 6)
        self.assertEqual(coach.notes_cap(75, 60), 2)
        self.assertEqual(coach.notes_cap(75, 24), 0)

    def test_fingerprint_normalization(self):
        expected = hashlib.sha256(b'hello world').hexdigest()
        for text in ('Hello world', '  HELLO,   world!! ', 'hello\n\nworld', '“Hello” — world…', 'ＨＥＬＬＯ world'):
            self.assertEqual(coach.text_fingerprint(text), expected, text)
        self.assertEqual(coach.text_fingerprint("It's"), coach.text_fingerprint('It’s'))
        self.assertEqual(coach.text_fingerprint("It's"), coach.text_fingerprint('Its'))
        self.assertNotEqual(coach.text_fingerprint('hello world'), coach.text_fingerprint('hello worlds'))
        self.assertNotEqual(coach.text_fingerprint('room 12'), coach.text_fingerprint('room 13'))
        self.assertEqual(coach.text_fingerprint(''), hashlib.sha256(b'').hexdigest())
        # letters of other scripts are kept
        self.assertNotEqual(coach.text_fingerprint('Привет мир'), coach.text_fingerprint('Привет'))
        self.assertEqual(coach.text_fingerprint('Oʻzbekiston, vatanim!'), coach.text_fingerprint('oʻzbekiston vatanim'))


class DedupTests(EssayLabTestCase):
    TEXT = 'First sentence is right here. Second sentence follows now. Third one closes it.'

    def notes(self, raw, cap=12, text=None):
        return coach.validate_notes(raw, text or self.TEXT, 'personal_statement', cap)

    def raw(self, quote, question, context='', criterion='reflection'):
        return {'criterion': criterion, 'quote': quote, 'question': question, 'context': context}

    def test_one_note_per_sentence(self):
        notes = self.notes([
            self.raw('First sentence is right here.', 'What was the room like when you first said it?'),
            self.raw('sentence is right', 'Who else heard you say this out loud?'),
            self.raw('right here. Second sentence', 'Which of the two sentences matters more to you?'),
            self.raw('Second sentence follows now.', 'What changed for you in the days that followed it?'),
        ])
        self.assertEqual([note['quote'] for note in notes],
                         ['First sentence is right here.', 'Second sentence follows now.'])

    def test_earlier_important_note_wins(self):
        notes = self.notes([
            self.raw('Second sentence follows', 'Which detail do you remember best from that day?'),
            self.raw('Second sentence follows now.', 'Completely different wording about another thing entirely.'),
        ])
        self.assertEqual([note['question'] for note in notes], ['Which detail do you remember best from that day?'])

    def test_near_duplicate_questions_are_dropped(self):
        notes = self.notes([
            self.raw('First sentence is right here.', 'What did you feel when you first stood there?'),
            self.raw('Third one closes it.', 'What did you feel when you first stood there??'),
            self.raw('Second sentence follows now.', 'Who taught you to count the stars at night?'),
        ])
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[1]['quote'], 'Second sentence follows now.')

    def test_context_repeating_the_question_is_blanked(self):
        notes = self.notes([
            self.raw('First sentence is right here.', 'What did you feel when you first stood there?',
                     context='What did you feel when you first stood there'),
            self.raw('Second sentence follows now.', 'Who taught you to count the stars at night?',
                     context='What did you feel when you first stood there?'),
            self.raw('Third one closes it.', 'Which smell do you connect with that place?',
                     context='Smell often brings memory back faster than sight.'),
        ])
        self.assertEqual(notes[0]['context'], '')
        self.assertEqual(notes[2]['context'], 'Smell often brings memory back faster than sight.')

    def test_a_context_line_is_not_repeated_across_notes(self):
        line = 'Concrete moments make a reader trust the claim.'
        notes = self.notes([
            self.raw('First sentence is right here.', 'What did you feel when you first stood there?', context=line),
            self.raw('Second sentence follows now.', 'Who taught you to count the stars at night?',
                     context=line.upper().replace('.', '!')),
            self.raw('Third one closes it.', 'Which smell do you connect with that place?', context='Another idea.'),
        ])
        self.assertEqual([note['context'] for note in notes], [line, '', 'Another idea.'])

    def test_unknown_criterion_is_dropped_and_first_three_are_priority(self):
        sentences = [f'Word{i} stands alone in sentence {i}.' for i in range(6)]
        text = ' '.join(sentences)
        rng = random.Random(7)
        words = ['amber', 'basalt', 'cobalt', 'dune', 'ember', 'fjord', 'garnet', 'harbor', 'ivory', 'jasper']
        raw = [self.raw(sentence, ' '.join(rng.sample(words, 6)) + '?') for sentence in sentences]
        raw.insert(0, self.raw(sentences[0], 'Unrelated question about marbles and rivers?', criterion='sparkle'))
        notes = self.notes(raw, text=text)
        self.assertEqual(len(notes), 6)
        self.assertEqual([note['priority'] for note in notes], [True, True, True, False, False, False])
        self.assertEqual([note['id'] for note in notes], [f'n{i}' for i in range(1, 7)])


class CoachApiTestCase(EssayLabTestCase):
    def setUp(self):
        super().setUp()
        self.essay = self.make_essay(content=LONG_TEXT)

    def check(self, gateway=None):
        gateway = gateway or FakeGateway()
        seq = self.tab_of(self.essay).save_seq
        with mock.patch('urllib.request.urlopen', side_effect=gateway):
            response = self.client.post(f'{BASE}/essays/{self.essay.pk}/depth-check/', {'base_seq': seq},
                                        format='json')
        return response, gateway

    def set_text(self, text):
        tab = self.tab_of(self.essay)
        EssayTab.objects.filter(pk=tab.pk).update(doc=make_doc(text), content=text, save_seq=tab.save_seq + 1)

    def distinct_notes(self, count):
        """`count` valid notes on distinct sentences of an essay built for them, as (text, notes)."""
        rng = random.Random(3)
        words = [f'w{i}x' for i in range(400)]
        sentences = [f'The {rng.choice(words)} stayed {rng.choice(words)} that morning.' for _ in range(count)]
        notes = [{'criterion': 'reflection', 'quote': sentence,
                  'question': ' '.join(rng.sample(words, 5)) + '?', 'context': ''} for sentence in sentences]
        return ' '.join(sentences), {'notes': notes}


@override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key', ESSAY_COACH_MIN_INTERVAL_SECONDS=0)
class TwoStepTests(CoachApiTestCase):
    def test_step_two_is_skipped_at_50_or_less(self):
        response, gateway = self.check(FakeGateway(score=score_reply()))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(gateway.steps, ['score'])
        result = response.data['result']
        self.assertEqual((result['overall'], result['notes'], result['notes_locked']), (0, [], True))
        self.assertEqual(len(result['suggestions']), 2)

    def test_prompt_prefix_is_identical_across_the_two_calls(self):
        response, gateway = self.check(FakeGateway(notes={'notes': []}))
        self.assertEqual(gateway.steps, ['score', 'notes'])
        first, second = gateway.bodies
        self.assertEqual(first['messages'][0], second['messages'][0])
        prefix = [body['messages'][1]['content'].rsplit('\n\nTASK:', 1)[0] for body in gateway.bodies]
        self.assertEqual(prefix[0], prefix[1])
        self.assertIn('<<<ESSAY_TEXT (untrusted data)', prefix[0])
        for body in gateway.bodies:
            content = body['messages'][1]['content']
            self.assertEqual(content.count('TASK:'), 1)
            self.assertIn('TASK:', content[content.index('ESSAY_TEXT>>>'):])
        system = first['messages'][0]['content']
        self.assertIn('Reflection and insight', system)
        self.assertIn('never write, rewrite', system)
        self.assertNotIn('"mode": "score"', system)
        self.assertIn('Never repeat or rephrase the question', second['messages'][1]['content'])

    def test_output_caps_and_determinism(self):
        _, gateway = self.check()
        first, second = gateway.bodies
        cap = coach.notes_cap(62, len(LONG_TEXT.split()))
        self.assertEqual(first['max_completion_tokens'], 800)  # a scored step 1 also returns its evidence quotes
        self.assertEqual(second['max_completion_tokens'], 70 * cap + 150)
        for body in gateway.bodies:
            self.assertEqual((body['temperature'], body['model']), (0, coach.settings.ESSAY_COACH_MODEL))

    def test_notes_are_capped_by_band_and_words(self):
        text, notes = self.distinct_notes(40)  # 40 sentences of 6 words: 240 words
        self.essay = self.make_essay(content=text)
        for value, band_cap in ((4, 25), (3, 12)):
            self.essay = self.make_essay(content=text)
            response, _ = self.check(FakeGateway(score=score_reply(**{k: value for k in PS_KEYS}), notes=notes))
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            words = len(text.split())
            cap = coach.notes_cap(response.data['overall'], words)
            self.assertLessEqual(cap, min(band_cap, words // 25))
            self.assertEqual(len(response.data['result']['notes']), cap)
        # 240 words allow 9 notes: an all-4s essay is limited by words, not by its 25-note band
        self.assertEqual(coach.notes_cap(100, 240), 9)

    def test_reasoning_effort_is_dropped_once_when_the_gateway_rejects_it(self):
        gateway = FakeGateway()
        calls = []

        def urlopen(request, timeout=None):
            body = json.loads(request.data.decode('utf-8'))
            calls.append(body)
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    'https://gw', 400, 'Bad', {}, io.BytesIO(b'{"error": "Unsupported parameter: reasoning_effort"}'))
            return gateway(request, timeout)

        with mock.patch('urllib.request.urlopen', side_effect=urlopen):
            response = self.client.post(f'{BASE}/essays/{self.essay.pk}/depth-check/', {'base_seq': 0}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('reasoning_effort', calls[0])
        self.assertNotIn('reasoning_effort', calls[1])

    def test_another_400_is_not_retried(self):
        error = urllib.error.HTTPError('https://gw', 400, 'Bad', {}, io.BytesIO(b'{"error": "bad json"}'))
        with mock.patch('urllib.request.urlopen', side_effect=error) as urlopen:
            response = self.client.post(f'{BASE}/essays/{self.essay.pk}/depth-check/', {'base_seq': 0}, format='json')
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(urlopen.call_count, 1)

    @override_settings(ESSAY_COACH_REASONING_EFFORT='')
    def test_empty_reasoning_effort_is_not_sent(self):
        _, gateway = self.check()
        self.assertNotIn('reasoning_effort', gateway.bodies[0])

    def test_unscored_type_still_gets_notes_at_the_middle_band(self):
        self.essay = self.make_essay(content=LONG_TEXT, essay_type='activity')
        notes = {'notes': [{'criterion': 'specificity', 'quote': 'I rebuilt the school radio with two friends',
                            'question': 'Who held the soldering iron first?', 'context': ''}]}
        response, gateway = self.check(FakeGateway(score={'summary': 'Short.', 'strengths': [], 'suggestions': ['a', 'b']},
                                                   notes=notes))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(gateway.steps, ['score', 'notes'])
        result = response.data['result']
        self.assertEqual((result['scored'], result['overall'], result['scores']), (False, None, {}))
        self.assertEqual(len(result['notes']), 1)
        self.assertNotIn('"scores"', gateway.bodies[0]['messages'][1]['content'].rsplit('TASK:', 1)[1].split('This type')[0])
        self.assertIn('at most 5 notes', gateway.bodies[1]['messages'][1]['content'])

    def test_supplement_scores_use_the_api_keys(self):
        self.essay = self.make_essay(content=LONG_TEXT, essay_type='supplement')
        native = {'fit_specificity': 4, 'reflection': 3, 'evidence': 2, 'voice': 1, 'concision': 4}
        reply = {'scores': native, 'summary': 's', 'strengths': [{'criterion': 'evidence', 'quote': '', 'text': 't'}],
                 'suggestions': []}
        response, gateway = self.check(FakeGateway(score=reply))
        result = response.data['result']
        self.assertEqual(result['scores'], {'prompt_fit': 4, 'reflection': 3, 'specificity': 2, 'voice': 1,
                                            'structure': 4})
        self.assertEqual(result['overall'], coach.compute_overall('supplement', result['scores']))
        self.assertEqual(result['overall'], (2 * (30 * 3 + 25 * 2 + 20 * 1 + 0 + 10 * 3) + 3) // 6)
        self.assertEqual(result['strengths'][0]['criterion'], 'specificity')
        self.assertIn('"fit_specificity"', gateway.bodies[0]['messages'][1]['content'])

    def test_current_danger_is_not_scored(self):
        response, gateway = self.check(FakeGateway(score={'safety': 'current_danger'}))
        self.assertEqual(gateway.steps, ['score'])
        result = response.data['result']
        self.assertEqual((result['scored'], result['overall'], result['notes'], result['summary']), (False, None, [], ''))
        self.assertEqual((result['safety'], result['helpline'], result['notes_locked']), ('current_danger', '', True))

    def test_the_old_safety_mode_is_treated_as_current_danger(self):
        reply = {'mode': 'safety', 'message': 'You are not alone; a trusted person can help.'}
        response, _ = self.check(FakeGateway(score=reply))
        self.assertEqual((response.data['result']['safety'], response.data['overall']), ('current_danger', None))

    def test_both_calls_are_recorded_and_cost_one_budget_unit(self):
        before = ai_budget.user_remaining('essay_coach', self.student_user)
        response, gateway = self.check()
        self.assertEqual(gateway.steps, ['score', 'notes'])
        self.assertEqual(AiUsageLog.objects.filter(feature='essay_coach', status='ok').count(), 2)
        self.assertEqual(response.data['checks_left'], before - 1)

    def test_previous_overall(self):
        first, _ = self.check()
        self.assertIsNone(first.data['previous_overall'])
        self.set_text(LONG_TEXT.replace('grandmother never wasted', 'aunt always saved'))
        second, _ = self.check(FakeGateway(score=score_reply(**{k: 4 for k in PS_KEYS})))
        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertEqual((second.data['overall'], second.data['previous_overall']), (100, 62))
        self.assertEqual(self.client.get(f'{BASE}/essays/{self.essay.pk}/depth-check/latest/').data['previous_overall'], 62)


@override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key', ESSAY_COACH_MIN_INTERVAL_SECONDS=0)
class RecheckRuleTests(CoachApiTestCase):
    NOTES = {'notes': [
        {'criterion': 'reflection', 'quote': 'I learned that patience matters.',
         'question': 'When did you first notice this?', 'context': ''},
        {'criterion': 'specificity', 'quote': 'My grandmother never wasted bread.',
         'question': 'What did the kitchen smell like?', 'context': ''},
    ]}

    def first_check_with_notes(self):
        response, _ = self.check(FakeGateway(notes=self.NOTES))
        self.assertEqual(len(response.data['result']['notes']), 2, response.data)
        return response.data

    def patch_note(self, check_id, note_id, state, client=None):
        return (client or self.client).patch(
            f'{BASE}/essays/{self.essay.pk}/depth-check/{check_id}/notes/', {'note_id': note_id, 'state': state},
            format='json')

    def test_first_check_has_no_restrictions(self):
        response, _ = self.check()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['reused'])

    def test_same_text_returns_the_latest_check_without_budget_or_ai(self):
        first = self.first_check_with_notes()
        usage = AiUsageLog.objects.count()
        left = ai_budget.user_remaining('essay_coach', self.student_user)
        # Open notes do not matter: same text is answered first. Case, spacing and punctuation do not count.
        self.set_text(LONG_TEXT.upper().replace('.', ' .  '))
        with mock.patch('urllib.request.urlopen') as urlopen:
            response = self.client.post(f'{BASE}/essays/{self.essay.pk}/depth-check/',
                                        {'base_seq': self.tab_of(self.essay).save_seq}, format='json')
        urlopen.assert_not_called()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['reused'])
        self.assertEqual(response.data['id'], first['id'])
        self.assertEqual(EssayDepthCheck.objects.count(), 1)
        self.assertEqual(AiUsageLog.objects.count(), usage)
        self.assertEqual(ai_budget.user_remaining('essay_coach', self.student_user), left)
        self.assertEqual(response.data['checks_left'], left)
        self.assertEqual(self.client.get(f'{BASE}/essays/{self.essay.pk}/depth-check/latest/').data['reused'], False)

    def test_reused_does_not_use_the_throttle_slot(self):
        self.check()
        with override_settings(ESSAY_COACH_MIN_INTERVAL_SECONDS=60):
            for _ in range(3):
                response, _ = self.check()
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertTrue(response.data['reused'])

    def test_open_notes_block_a_recheck(self):
        self.first_check_with_notes()
        self.set_text(LONG_TEXT + ' Then we all sat down and laughed for hours.')
        response, gateway = self.check()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual((response.data['code'], response.data['open']), ('notes_open', 2))
        self.assertEqual(gateway.bodies, [])
        self.assertEqual(AiUsageLog.objects.filter(status='ok').count(), 2)

    def test_done_and_dismissed_notes_are_resolved(self):
        first = self.first_check_with_notes()
        self.set_text(LONG_TEXT + ' Then we all sat down and laughed for hours.')
        self.assertEqual(self.patch_note(first['id'], 'n1', 'done').status_code, status.HTTP_200_OK)
        self.assertEqual(self.check()[0].data['open'], 1)
        self.assertEqual(self.patch_note(first['id'], 'n2', 'dismissed').status_code, status.HTTP_200_OK)
        response, gateway = self.check()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(gateway.bodies), 2)
        self.assertEqual(response.data['note_states'], {})  # a new check starts with its own states

    def test_a_note_whose_quote_is_gone_counts_as_resolved(self):
        self.first_check_with_notes()
        changed = (LONG_TEXT.replace('I learned that patience matters.', 'Patience was never the lesson here.')
                   .replace('My grandmother never wasted bread.', 'Nobody in that house threw bread away.'))
        self.set_text(changed)
        response, _ = self.check()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_one_gone_quote_leaves_the_other_note_open(self):
        self.first_check_with_notes()
        self.set_text(LONG_TEXT.replace('I learned that patience matters.', 'Patience was never the lesson here.'))
        response, _ = self.check()
        self.assertEqual((response.status_code, response.data['code'], response.data['open']),
                         (status.HTTP_409_CONFLICT, 'notes_open', 1))

    def test_too_small_a_change_is_refused(self):
        self.check()  # no notes, so only the word threshold applies
        self.set_text(LONG_TEXT.replace('grandmother never', 'aunt always'))  # 2 words
        response, gateway = self.check()
        self.assertEqual((response.status_code, response.data['code']), (status.HTTP_409_CONFLICT, 'too_small_change'))
        self.assertEqual(gateway.bodies, [])
        self.assertEqual(EssayDepthCheck.objects.count(), 1)
        self.set_text(LONG_TEXT.replace('grandmother never wasted', 'aunt always saved'))  # 3 words
        response, _ = self.check()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    @override_settings(ESSAY_COACH_MIN_CHANGED_WORDS=1)
    def test_the_word_threshold_is_a_setting(self):
        self.check()
        self.set_text(LONG_TEXT.replace('grandmother', 'aunt'))
        self.assertEqual(self.check()[0].status_code, status.HTTP_200_OK)

    def test_without_the_checked_text_the_word_rule_is_skipped(self):
        self.check()
        EssayCheckpoint.objects.filter(reason='depth_check').delete()
        self.set_text(LONG_TEXT.replace('grandmother', 'aunt'))
        self.assertEqual(self.check()[0].status_code, status.HTTP_200_OK)

    def test_old_checks_work_with_the_rules(self):
        tab = self.tab_of(self.essay)
        old = EssayDepthCheck.objects.create(
            essay=self.essay, tab=tab, save_seq=tab.save_seq, model='gpt-old',
            result={'summary': 's', 'strengths': ['x'], 'scores': {'voice': 3},
                    'notes': [{'id': 'n1', 'kind': 'reflect', 'quote': 'I learned that patience matters.',
                               'question': 'q', 'why': 'w'}]})
        latest = self.client.get(f'{BASE}/essays/{self.essay.pk}/depth-check/latest/')
        self.assertEqual(latest.status_code, status.HTTP_200_OK)
        self.assertEqual((latest.data['source'], latest.data['text_fingerprint'], latest.data['note_states'],
                          latest.data['overall'], latest.data['previous_overall'], latest.data['reused']),
                         ('ai', '', {}, None, None, False))
        self.assertEqual(latest.data['result']['notes'][0]['kind'], 'reflect')
        # No fingerprint and no checkpoint: v1 notes do not block, nothing to compare words with.
        self.assertEqual(self.check()[0].status_code, status.HTTP_200_OK)
        # A check from before fingerprints is never reused: same text, new input, a new check.
        old.refresh_from_db()
        self.assertEqual(old.input_hash, '')
        self.assertEqual(EssayDepthCheck.objects.count(), 2)

    @override_settings(OUTBOUND_AI_ENABLED=False)
    def test_rules_also_apply_to_the_local_reader(self):
        first, _ = self.check()
        self.assertEqual((first.data['model'], first.data['source']), ('local', 'rules'))
        again, gateway = self.check()
        self.assertEqual((again.status_code, again.data['reused']), (status.HTTP_200_OK, True))
        self.assertEqual(EssayDepthCheck.objects.count(), 1)
        self.assertEqual(AiUsageLog.objects.filter(status='local_fallback').count(), 1)


@override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key', ESSAY_COACH_MIN_INTERVAL_SECONDS=0)
class NoteStateTests(CoachApiTestCase):
    def setUp(self):
        super().setUp()
        notes = {'notes': [{'criterion': 'reflection', 'quote': 'I learned that patience matters.',
                            'question': 'When did you first notice this?', 'context': ''}]}
        self.checked, _ = self.check(FakeGateway(notes=notes))
        self.url = f'{BASE}/essays/{self.essay.pk}/depth-check/{self.checked.data["id"]}/notes/'

    def patch(self, body, client=None):
        return (client or self.client).patch(self.url, body, format='json')

    def test_owner_marks_and_reopens_a_note(self):
        response = self.patch({'note_id': 'n1', 'state': 'done'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['note_states'], {'n1': 'done'})
        self.assertEqual(EssayDepthCheck.objects.get().note_states, {'n1': 'done'})
        self.assertEqual(self.patch({'note_id': 'n1', 'state': 'dismissed'}).data['note_states'], {'n1': 'dismissed'})
        self.assertEqual(self.patch({'note_id': 'n1', 'state': 'open'}).data['note_states'], {})
        latest = self.client.get(f'{BASE}/essays/{self.essay.pk}/depth-check/latest/')
        self.assertEqual(latest.data['note_states'], {})

    def test_a_note_can_be_marked_gone_and_that_resolves_it(self):
        self.assertEqual(self.patch({'note_id': 'n1', 'state': 'gone'}).data['note_states'], {'n1': 'gone'})
        # The quote is still in the text, but a gone note is resolved like done and dismissed.
        self.set_text(LONG_TEXT + ' Then we all sat down and laughed for hours.')
        response, _ = self.check(FakeGateway())
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_gone_needs_the_owner_too(self):
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.patch({'note_id': 'n1', 'state': 'gone'}).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.counselor)
        self.assertEqual(self.patch({'note_id': 'n1', 'state': 'gone'}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(EssayDepthCheck.objects.get().note_states, {})

    def test_invalid_requests(self):
        self.assertEqual(self.patch({'note_id': 'n9', 'state': 'done'}).data['code'], 'unknown_note')
        self.assertEqual(self.patch({'note_id': 'n1', 'state': 'maybe'}).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.patch({'state': 'done'}).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(EssayDepthCheck.objects.get().note_states, {})

    def test_other_checks_of_the_essay_are_not_reachable_through_another_essay(self):
        other = self.make_essay(title='Other')
        url = f'{BASE}/essays/{other.pk}/depth-check/{self.checked.data["id"]}/notes/'
        self.assertEqual(self.client.patch(url, {'note_id': 'n1', 'state': 'done'}, format='json').status_code,
                         status.HTTP_404_NOT_FOUND)

    def test_only_the_owner_may_change_note_states(self):
        body = {'note_id': 'n1', 'state': 'done'}
        Essay = type(self.essay)
        Essay.objects.filter(pk=self.essay.pk).update(shared_with_counselor=True)
        for user in (self.counselor, self.organization, self.teacher):
            self.client.force_authenticate(user)
            self.assertIn(self.patch(body).status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
                          user.role)
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.patch(body).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(None)
        self.assertIn(self.patch(body).status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertEqual(EssayDepthCheck.objects.get().note_states, {})


@override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key', ESSAY_COACH_MIN_INTERVAL_SECONDS=0)
class ChecksLeftTests(CoachApiTestCase):
    @override_settings(ESSAY_COACH_USER_DAILY_LIMIT=3)
    def test_counts_down_with_ai_checks_only(self):
        first, _ = self.check()
        self.assertEqual(first.data['checks_left'], 2)
        self.assertEqual(self.check()[0].data['checks_left'], 2)  # same text: reused, not counted
        self.set_text(LONG_TEXT.replace('grandmother never wasted', 'aunt always saved'))
        second, _ = self.check()
        self.assertEqual(second.data['checks_left'], 1)
        self.assertEqual(self.client.get(f'{BASE}/essays/{self.essay.pk}/depth-check/latest/').data['checks_left'], 1)

    def test_default_limit_is_five(self):
        self.assertEqual(coach.settings.ESSAY_COACH_USER_DAILY_LIMIT, 5)
        self.assertEqual(self.check()[0].data['checks_left'], 4)

    @override_settings(ESSAY_COACH_USER_DAILY_LIMIT=0)
    def test_no_cap_means_no_number(self):
        self.assertIsNone(self.check()[0].data['checks_left'])

    @override_settings(ESSAY_COACH_USER_DAILY_LIMIT=1)
    def test_refused_checks_do_not_count_and_the_limit_holds(self):
        self.assertEqual(self.check()[0].data['checks_left'], 0)
        self.set_text(LONG_TEXT.replace('grandmother never wasted', 'aunt always saved'))
        refused, gateway = self.check()
        self.assertEqual((refused.status_code, refused.data['code']), (status.HTTP_503_SERVICE_UNAVAILABLE, 'coach_resting'))
        self.assertEqual(gateway.bodies, [])
        self.assertEqual(ai_budget.user_remaining('essay_coach', self.student_user), 0)

    @override_settings(OUTBOUND_AI_ENABLED=False)
    def test_local_checks_are_not_charged(self):
        self.assertEqual(self.check()[0].data['checks_left'], 5)


class LocalFallbackShapeTests(EssayLabTestCase):
    def test_v2_shape(self):
        essay = SimpleNamespace(prompt='', essay_type='free_writing', word_limit=None)
        text = ('I have always wanted to make a difference in the world. I learned that kindness matters. '
                + 'Filler words keep going here. ' * 20)
        result, model = coach.run_local_check(essay, text)
        self.assertEqual(model, 'local')
        self.assertEqual(set(result), {'version', 'scored', 'overall', 'scores', 'summary', 'suggestions',
                                       'strengths', 'notes_locked', 'notes'})
        self.assertEqual((result['version'], result['scored'], result['overall'], result['notes_locked']),
                         (2, False, None, False))
        self.assertGreaterEqual(len(result['suggestions']), 2)
        self.assertTrue(result['notes'])
        for note in result['notes']:
            self.assertEqual(set(note), {'id', 'criterion', 'quote', 'question', 'context', 'priority'})
            self.assertIn(note['criterion'], ('reflection', 'specificity', 'structure'))
            self.assertIn(note['quote'], text)
            self.assertNotEqual(note['context'], note['question'])
        self.assertLessEqual(len(result['notes']), len(text.split()) // 25)
        self.assertEqual(sum(1 for note in result['notes'] if note['priority']), min(3, len(result['notes'])))


class MigrationTests(EssayLabTestCase):
    def test_new_columns_are_additive_and_old_rows_keep_working(self):
        from .migrations import __path__ as migrations_path  # noqa: F401
        import importlib

        migration = importlib.import_module('apps.admissions.migrations.0092_essay_depth_check_v2').Migration
        self.assertEqual(migration.dependencies, [('admissions', '0091_meeting_schedule_window')])
        fields = {op.name: op.field for op in migration.operations}
        self.assertEqual(set(fields), {'text_fingerprint', 'overall', 'note_states'})
        self.assertTrue(fields['overall'].null)
        self.assertEqual(fields['note_states'].default, dict)
        self.assertTrue(fields['text_fingerprint'].blank)
        self.assertTrue(all(type(op).__name__ == 'AddField' for op in migration.operations))
        essay = self.make_essay()
        row = EssayDepthCheck.objects.create(essay=essay, tab=self.tab_of(essay), save_seq=0, model='m',
                                             result={'summary': 'old'})
        row.refresh_from_db()
        self.assertEqual((row.text_fingerprint, row.overall, row.note_states), ('', None, {}))


FINGERPRINT_FIXTURES = Path(__file__).resolve().parents[3] / 'docs' / 'essay-coach-fingerprint-fixtures.json'


class FingerprintFixtureTests(EssayLabTestCase):
    def test_shared_vectors(self):
        cases = json.loads(FINGERPRINT_FIXTURES.read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(cases), 10)
        for case in cases:
            self.assertEqual(coach.text_fingerprint(case['text']), case['sha256'], case['name'])
        digests = {case['name']: case['sha256'] for case in cases}
        # the BOM, \x85 and case/spacing variants all equal the plain text
        self.assertEqual(digests['plain'], digests['bom'])
        self.assertEqual(digests['plain'], digests['next line x85'])
        self.assertEqual(digests['plain'], digests['case and spacing'])


class SentenceSplitTests(EssayLabTestCase):
    def test_decimals_and_abbreviations_do_not_end_a_sentence(self):
        text = 'Dr. Smith paid 3.5 dollars, e.g. for bread, vs. cake. Next sentence here. Mrs. Lee left St. Paul at 5 p.m. today.'
        spans = [text[start:end].strip() for start, end in coach.sentence_spans(text)]
        self.assertEqual(spans, ['Dr. Smith paid 3.5 dollars, e.g. for bread, vs. cake.', 'Next sentence here.',
                                 'Mrs. Lee left St. Paul at 5 p.m. today.'])
        notes = coach.validate_notes([
            {'criterion': 'reflection', 'quote': 'Dr. Smith paid', 'question': 'Who was he to you at the time?'},
            {'criterion': 'voice', 'quote': 'paid 3.5 dollars', 'question': 'Which coin did you hold, and where?'},
            {'criterion': 'voice', 'quote': 'vs. cake', 'question': 'Why did bread win over the cake for you?'},
            {'criterion': 'voice', 'quote': 'Next sentence here.', 'question': 'What came right before that scene?'},
        ], text, 'personal_statement', 12)
        self.assertEqual([note['quote'] for note in notes], ['Dr. Smith paid', 'Next sentence here.'])


@override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key', ESSAY_COACH_MIN_INTERVAL_SECONDS=0)
class CostGuardTests(CoachApiTestCase):
    def failing_gateway(self, fail_step):
        good = FakeGateway()

        def urlopen(request, timeout=None):
            body = json.loads(request.data.decode('utf-8'))
            step = 'notes' if 'TASK: NOTES' in body['messages'][-1]['content'] else 'score'
            if step == fail_step:
                raise OSError('down')
            return good(request, timeout)

        return urlopen

    def test_a_failed_check_is_free(self):
        left = ai_budget.user_remaining('essay_coach', self.student_user)
        day = ai_budget.timezone.localdate().isoformat()
        for step in ('notes', 'score'):
            with mock.patch('urllib.request.urlopen', side_effect=self.failing_gateway(step)):
                response = self.client.post(f'{BASE}/essays/{self.essay.pk}/depth-check/', {'base_seq': 0},
                                            format='json')
            self.assertEqual((response.status_code, response.data['code']),
                             (status.HTTP_503_SERVICE_UNAVAILABLE, 'coach_unavailable'), step)
            self.assertEqual(ai_budget.user_remaining('essay_coach', self.student_user), left, step)
            self.assertEqual(cache.get(f'ai-budget:essay_coach:{day}'), 0, step)
            self.assertEqual(cache.get(f'ai-budget:essay_coach:{day}:school:{self.school.pk}'), 0, step)
        self.assertEqual(EssayDepthCheck.objects.count(), 0)
        # the paid first call of the notes failure is still recorded
        self.assertEqual(AiUsageLog.objects.filter(status='ok').count(), 1)

    def test_a_check_makes_at_most_two_paid_calls(self):
        _, gateway = self.check(FakeGateway(score={'scores': {}}))
        self.assertEqual(len(gateway.bodies), 1)
        _, gateway = self.check()
        self.assertLessEqual(len(gateway.bodies), 2)

    @override_settings(ESSAY_COACH_RECHECK_PER_MINUTE=2)
    def test_the_guard_runs_before_the_rules(self):
        self.check()
        for _ in range(1):
            self.assertTrue(self.check()[0].data['reused'])
        response, gateway = self.check()
        self.assertEqual((response.status_code, response.data['code']), (status.HTTP_429_TOO_MANY_REQUESTS, 'slow_down'))

    def test_refused_rechecks_do_not_use_the_budget_and_open_notes_come_first(self):
        notes = {'notes': [{'criterion': 'reflection', 'quote': 'I learned that patience matters.',
                            'question': 'When did you first notice this?', 'context': ''}]}
        self.check(FakeGateway(notes=notes))
        left = ai_budget.user_remaining('essay_coach', self.student_user)
        self.set_text(LONG_TEXT.replace('grandmother never', 'aunt always'))
        with mock.patch.object(coach, 'changed_words') as words:
            response, gateway = self.check()
        self.assertEqual(response.data['code'], 'notes_open')
        words.assert_not_called()
        self.assertEqual(gateway.bodies, [])
        self.assertEqual(ai_budget.user_remaining('essay_coach', self.student_user), left)

    def test_word_comparison_is_capped_and_short_circuits(self):
        self.assertEqual(coach.changed_words('a b c', 'a b c d e f g', threshold=3), 4)
        self.assertEqual(coach.changed_words('a b c', 'a b x', threshold=3), 1)
        # only the first `limit` characters are compared
        self.assertEqual(coach.changed_words('same words here ' + 'old ' * 50, 'same words here ' + 'new ' * 50, limit=16), 0)
        with mock.patch('difflib.SequenceMatcher') as matcher:
            coach.changed_words('a ' * 10, 'a ' * 3, threshold=3)
        matcher.assert_not_called()

    def test_reuse_needs_the_same_prompt_type_and_model(self):
        self.check()
        self.assertTrue(self.check()[0].data['reused'])
        type(self.essay).objects.filter(pk=self.essay.pk).update(prompt='A different question.')
        self.essay.refresh_from_db()
        response, gateway = self.check()
        self.assertEqual((response.status_code, response.data['reused']), (status.HTTP_200_OK, False))
        self.assertEqual(len(gateway.bodies), 2)
        self.assertTrue(self.check()[0].data['reused'])
        type(self.essay).objects.filter(pk=self.essay.pk).update(essay_type='supplement')
        self.essay.refresh_from_db()
        supplement = {'scores': {'fit_specificity': 2, 'reflection': 2, 'evidence': 2, 'voice': 2, 'concision': 2},
                      'summary': 's', 'strengths': [], 'suggestions': []}
        self.assertFalse(self.check(FakeGateway(score=supplement))[0].data['reused'])
        with override_settings(ESSAY_COACH_MODEL='other/model'):
            response, gateway = self.check(FakeGateway(score=supplement))
        self.assertFalse(response.data['reused'])
        self.assertGreaterEqual(len(gateway.bodies), 1)

    def test_missing_checkpoint_falls_back_to_the_fingerprint_and_logs_no_text(self):
        self.check()
        EssayCheckpoint.objects.filter(reason='depth_check').delete()
        self.assertTrue(self.check()[0].data['reused'])
        self.set_text(LONG_TEXT.replace('grandmother', 'aunt'))
        with self.assertLogs('naseeb.essay_coach', level='INFO') as logs:
            response, _ = self.check()
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        joined = '\n'.join(logs.output)
        self.assertIn('essay_coach_recheck_unmeasured', joined)
        self.assertNotIn('grandmother', joined)
        self.assertNotIn('aunt', joined)


@override_settings(OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='test-key', ESSAY_COACH_MIN_INTERVAL_SECONDS=0)
class InputHashAndDeadlineTests(CoachApiTestCase):
    def test_word_limit_is_part_of_the_input(self):
        self.check()
        self.assertTrue(self.check()[0].data['reused'])
        type(self.essay).objects.filter(pk=self.essay.pk).update(word_limit=250)
        response, gateway = self.check()
        self.assertEqual((response.status_code, response.data['reused']), (status.HTTP_200_OK, False))
        self.assertEqual(len(gateway.bodies), 2)

    def test_the_stored_hash_is_the_one_from_before_the_provider_call(self):
        before = coach.input_hash(type(self.essay).objects.get(pk=self.essay.pk), coach.current_model())
        inner = FakeGateway()

        def urlopen(request, timeout=None):
            type(self.essay).objects.filter(pk=self.essay.pk).update(prompt='Changed while generating.')
            return inner(request, timeout)

        with mock.patch('urllib.request.urlopen', side_effect=urlopen):
            response = self.client.post(f'{BASE}/essays/{self.essay.pk}/depth-check/', {'base_seq': 0}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(EssayDepthCheck.objects.get().input_hash, before)
        self.assertEqual(response.data['input_hash'], before)
        # the client can tell the prompt changed since: the current hash differs from the check's
        self.assertNotEqual(response.data['current_input_hash'], response.data['input_hash'])

    def test_current_input_hash_on_post_reuse_and_latest(self):
        first, _ = self.check()
        current = coach.input_hash(type(self.essay).objects.get(pk=self.essay.pk), coach.current_model())
        self.assertEqual((first.data['input_hash'], first.data['current_input_hash']), (current, current))
        reused, _ = self.check()
        self.assertTrue(reused.data['reused'])
        self.assertEqual(reused.data['current_input_hash'], current)
        latest = self.client.get(f'{BASE}/essays/{self.essay.pk}/depth-check/latest/')
        self.assertEqual((latest.data['input_hash'], latest.data['current_input_hash']), (current, current))
        type(self.essay).objects.filter(pk=self.essay.pk).update(prompt='Another question.')
        latest = self.client.get(f'{BASE}/essays/{self.essay.pk}/depth-check/latest/')
        self.assertEqual(latest.data['input_hash'], current)
        self.assertNotEqual(latest.data['current_input_hash'], current)

    def test_the_connection_is_released_before_each_provider_call(self):
        events = []
        inner = FakeGateway()

        def urlopen(request, timeout=None):
            events.append('call')
            return inner(request, timeout)

        with mock.patch('apps.admissions.essay_lab.views.release_db_connection',
                        side_effect=lambda: events.append('release')), \
                mock.patch('urllib.request.urlopen', side_effect=urlopen):
            response = self.client.post(f'{BASE}/essays/{self.essay.pk}/depth-check/', {'base_seq': 0}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(events, ['release', 'call', 'release', 'call'])

    @override_settings(ESSAY_COACH_TOTAL_SECONDS=90, ESSAY_COACH_TIMEOUT_SECONDS=40)
    def test_step_two_gets_only_the_time_left_and_an_overrun_is_a_free_failure(self):
        for elapsed_after_step_one, expect_timeout in ((70, 20), (88, None)):
            cache.clear()
            EssayDepthCheck.objects.all().delete()
            clock = {'now': 0.0}
            timeouts = []
            inner = FakeGateway()

            def urlopen(request, timeout=None):
                timeouts.append(timeout)
                reply = inner(request, timeout)
                clock['now'] = elapsed_after_step_one if len(timeouts) == 1 else clock['now']
                return reply

            left = ai_budget.user_remaining('essay_coach', self.student_user)
            fake_time = SimpleNamespace(monotonic=lambda: clock['now'])
            with mock.patch.object(coach, 'time', fake_time), mock.patch('urllib.request.urlopen', side_effect=urlopen):
                response = self.client.post(f'{BASE}/essays/{self.essay.pk}/depth-check/', {'base_seq': 0},
                                            format='json')
            self.assertEqual(timeouts[0], 40)
            if expect_timeout:
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                self.assertEqual(timeouts, [40, expect_timeout])
            else:
                self.assertEqual((response.status_code, response.data['code']),
                                 (status.HTTP_503_SERVICE_UNAVAILABLE, 'coach_unavailable'))
                self.assertEqual(len(timeouts), 1)  # no second paid call
                self.assertEqual(ai_budget.user_remaining('essay_coach', self.student_user), left)
                self.assertEqual(EssayDepthCheck.objects.count(), 0)
