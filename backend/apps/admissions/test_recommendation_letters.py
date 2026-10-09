"""Counselor-written recommendation letters: who writes, who reads, and the suggestion endpoint."""
import json
import urllib.error
from datetime import date
from unittest import mock

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.admissions.models import Activity, Honor, RecommendationLetter
from apps.admissions.test_audit_base import AuditBaseMixin

LETTER_TEXT = 'I have known her for three years as her counselor.'
SUGGEST_URL = '/api/recommendations/suggest/'


def gateway_response(content):
    """A fake urlopen() context manager returning a chat-completions payload."""
    response = mock.MagicMock()
    response.read.return_value = json.dumps({'choices': [{'message': {'content': content}}]}).encode('utf-8')
    response.__enter__.return_value = response
    return response


class LetterFixture(AuditBaseMixin):
    def write_letter(self, **fields):
        return RecommendationLetter.objects.create(
            student=self.student, recommender_name='Base Counselor', status='drafting', body=LETTER_TEXT, **fields,
        )

    def rows(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(f'/api/recommendations/?student={self.student.id}')
        self.assertEqual(response.status_code, 200)
        return self.results(response)


class LetterVisibilityTests(LetterFixture, APITestCase):
    def test_student_reads_the_text_only_once_the_counselor_shares_it(self):
        self.client.force_authenticate(self.counselor)
        created = self.client.post('/api/recommendations/', {
            'student': self.student.id, 'recommender_name': 'Base Counselor', 'status': 'drafting', 'body': LETTER_TEXT,
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertFalse(created.data['shared_with_student'])

        [row] = self.rows(self.student_user)
        self.assertNotIn('body', row)
        self.assertTrue(row['has_body'])

        self.client.force_authenticate(self.counselor)
        shared = self.client.patch(f"/api/recommendations/{created.data['id']}/", {'shared_with_student': True}, format='json')
        self.assertEqual(shared.status_code, 200, shared.data)
        [row] = self.rows(self.student_user)
        self.assertEqual(row['body'], LETTER_TEXT)

    def test_school_organization_never_sees_the_text(self):
        letter = self.write_letter(shared_with_student=True)
        [row] = self.rows(self.organization)
        self.assertNotIn('body', row)
        self.client.force_authenticate(self.organization)
        detail = self.client.get(f'/api/recommendations/{letter.id}/')
        self.assertNotIn('body', detail.data)
        visibility = self.client.get(f'/api/students/{self.student.id}/data-visibility/')
        self.assertEqual(visibility.status_code, 200)
        self.assertNotIn('body', visibility.data['recommendations'][0])

    def test_other_counselors_cannot_reach_the_letter(self):
        letter = self.write_letter()
        for outsider in (self.counselor_peer, self.counselor_b):
            self.client.force_authenticate(outsider)
            self.assertEqual(self.client.get(f'/api/recommendations/{letter.id}/').status_code, 404)
            self.assertEqual(
                self.client.patch(f'/api/recommendations/{letter.id}/', {'body': 'Taken over.'}, format='json').status_code, 404,
            )
        letter.refresh_from_db()
        self.assertEqual(letter.body, LETTER_TEXT)


class StudentLetterWriteTests(LetterFixture, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.student_user)

    def create(self, **extra):
        return self.client.post('/api/recommendations/', {
            'student': self.student.id, 'recommender_name': 'Physics teacher', 'status': 'requested', **extra,
        }, format='json')

    def test_student_cannot_write_or_share_the_text(self):
        self.assertEqual(self.create(body='I recommend myself.').status_code, 400)
        self.assertEqual(self.create(shared_with_student=True).status_code, 400)
        own = self.create(body='', shared_with_student=False)
        self.assertEqual(own.status_code, 201, own.data)
        edit = self.client.patch(f"/api/recommendations/{own.data['id']}/", {'body': 'Sneaked in.'}, format='json')
        self.assertEqual(edit.status_code, 400)
        self.assertEqual(RecommendationLetter.objects.get(pk=own.data['id']).body, '')

    def test_student_cannot_change_or_delete_a_written_letter(self):
        letter = self.write_letter()
        self.assertEqual(self.client.patch(f'/api/recommendations/{letter.id}/', {'status': 'submitted'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/api/recommendations/{letter.id}/').status_code, 403)
        letter.refresh_from_db()
        self.assertEqual((letter.status, letter.body), ('drafting', LETTER_TEXT))

    def test_student_still_manages_letters_nobody_has_written(self):
        tracked = RecommendationLetter.objects.create(student=self.student, recommender_name='Physics teacher')
        update = self.client.patch(f'/api/recommendations/{tracked.id}/', {'notes': 'Sent my CV.'}, format='json')
        self.assertEqual(update.status_code, 200, update.data)
        self.assertEqual(self.client.delete(f'/api/recommendations/{tracked.id}/').status_code, 204)


@override_settings(REC_LETTER_SUGGEST_MIN_INTERVAL_SECONDS=0, AI_GATEWAY_API_KEY='')
class LetterSuggestionTests(LetterFixture, APITestCase):
    def setUp(self):
        super().setUp()
        self.student_user.first_name, self.student_user.last_name = 'Malika', 'Karimova'
        self.student_user.save(update_fields=['first_name', 'last_name'])
        self.student.application_profile = {'gender': 'Female', 'interests': ['Physics']}
        self.student.gpa, self.student.gpa_scale = '3.90', 4
        self.student.save()
        Honor.objects.create(student=self.student, title='Regional olympiad bronze', level='regional')
        Honor.objects.create(student=self.student, title='National physics olympiad gold', level='national', award_date=date(2026, 3, 1))
        Activity.objects.create(student=self.student, name='Robotics club', role='Team captain', impact='Won the city cup')

    def suggest(self, user=None, **payload):
        self.client.force_authenticate(user or self.counselor)
        return self.client.post(SUGGEST_URL, {'student': self.student.id, **payload}, format='json')

    def test_without_ai_the_profile_facts_come_back_strongest_first(self):
        response = self.suggest(draft='')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['source'], 'profile')
        suggestions = response.data['suggestions']
        self.assertEqual(suggestions[0], {'kind': 'tip', 'code': 'opening'})
        facts = [(item['source'], item['title']) for item in suggestions if item['kind'] == 'fact']
        self.assertEqual(facts, [
            ('academics', ''), ('honor', 'National physics olympiad gold'), ('honor', 'Regional olympiad bronze'),
            ('activity', 'Robotics club'),
        ])
        self.assertIn('GPA 3.9 / 4', suggestions[1]['detail'])

    def test_facts_the_draft_already_mentions_drop_out(self):
        response = self.suggest(draft='She won gold at the national physics olympiad and keeps a 3.9 GPA.')
        titles = [item['title'] for item in response.data['suggestions'] if item['kind'] == 'fact']
        self.assertEqual(titles, ['Regional olympiad bronze', 'Robotics club'])

    def test_only_the_students_counselor_can_ask(self):
        for user in (self.student_user, self.organization, self.teacher, self.parent):
            self.assertEqual(self.suggest(user).status_code, 403, user.role)
        for user in (self.counselor_peer, self.counselor_b):
            self.assertEqual(self.suggest(user).status_code, 404, user.username)
        self.assertEqual(self.suggest(self.admin).status_code, 200)

    @override_settings(AI_GATEWAY_API_KEY='test-key')
    def test_ai_gets_facts_without_identity_and_bad_items_are_dropped(self):
        answer = {'suggestions': [
            {'kind': 'sentence', 'text': '[Student] captained the robotics club.', 'source': 'Activity: Robotics club'},
            {'kind': 'essay', 'text': 'Not a kind we show.'},
            {'kind': 'idea', 'text': ''},
        ]}
        with mock.patch('urllib.request.urlopen', return_value=gateway_response(json.dumps(answer))) as urlopen:
            response = self.suggest(draft=f'Malika is a joy to teach at {self.school_a.name}. Call 998901234567.')
        self.assertEqual(response.data, {'source': 'ai', 'suggestions': [
            {'kind': 'sentence', 'text': '[Student] captained the robotics club.', 'source': 'Activity: Robotics club'},
        ]})
        sent = json.loads(urlopen.call_args.args[0].data)['messages'][1]['content']
        self.assertIn('National physics olympiad gold', sent)
        self.assertIn('she/her', sent)
        self.assertIn('[Student] is a joy to teach', sent)
        for private in ('Malika', 'Karimova', self.school_a.name, self.student_user.email, '998901234567'):
            self.assertNotIn(private, sent)

    @override_settings(AI_GATEWAY_API_KEY='test-key')
    def test_a_failing_provider_falls_back_to_the_profile(self):
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('down')):
            response = self.suggest()
        self.assertEqual(response.data['source'], 'profile')

    @override_settings(AI_GATEWAY_API_KEY='test-key', REC_LETTER_AI_DAILY_BUDGET=0)
    def test_a_zero_budget_turns_the_ai_off(self):
        with mock.patch('urllib.request.urlopen') as urlopen:
            response = self.suggest()
        urlopen.assert_not_called()
        self.assertEqual(response.data['source'], 'profile')

    @override_settings(REC_LETTER_SUGGEST_MIN_INTERVAL_SECONDS=60)
    def test_requests_closer_than_the_interval_are_throttled(self):
        clock = mock.Mock(time=mock.Mock(return_value=1000.0))
        with mock.patch('apps.users.throttles.time', clock):
            self.assertEqual(self.suggest().status_code, 200)
            self.assertEqual(self.suggest().status_code, 429)


class StudentLetterReviewTests(LetterFixture, APITestCase):
    """The student checks a letter their counselor shared: it is right, or what to change."""

    def review(self, user, letter, **payload):
        self.client.force_authenticate(user)
        return self.client.post(f'/api/recommendations/{letter.id}/student-review/', payload, format='json')

    def test_student_confirms_or_asks_for_changes_and_the_counselor_reads_it(self):
        letter = self.write_letter(shared_with_student=True)
        confirmed = self.review(self.student_user, letter, decision='confirmed', note='ignored')
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual((confirmed.data['student_review'], confirmed.data['student_review_note']), ('confirmed', ''))
        self.assertIsNotNone(confirmed.data['student_reviewed_at'])

        asked = self.review(self.student_user, letter, decision='changes_requested', note='  My robotics award is from 2025.  ')
        self.assertEqual(asked.status_code, 200, asked.data)
        [row] = self.rows(self.counselor)
        self.assertEqual((row['student_review'], row['student_review_note']), ('changes_requested', 'My robotics award is from 2025.'))

    def test_a_student_cannot_confirm_text_changed_since_they_opened_it(self):
        letter = self.write_letter(shared_with_student=True)
        response = self.review(self.student_user, letter, decision='confirmed', reviewed_body='An older draft.')
        self.assertEqual(response.status_code, 400)
        letter.refresh_from_db()
        self.assertEqual(letter.student_review, '')
        response = self.review(self.student_user, letter, decision='confirmed', reviewed_body=LETTER_TEXT)
        self.assertEqual(response.status_code, 200, response.data)

    def test_counselor_edit_during_review_validation_does_not_confirm_new_text(self):
        from apps.admissions.serializers.records import LetterStudentReviewSerializer

        letter = self.write_letter(shared_with_student=True)
        validate = LetterStudentReviewSerializer.validate

        def edit_during_validation(serializer, attrs):
            RecommendationLetter.objects.filter(pk=letter.pk).update(body='Updated while reviewing.')
            return validate(serializer, attrs)

        with mock.patch.object(LetterStudentReviewSerializer, 'validate', edit_during_validation):
            response = self.review(self.student_user, letter, decision='confirmed', reviewed_body=LETTER_TEXT)
        self.assertEqual(response.status_code, 400)
        letter.refresh_from_db()
        self.assertEqual(letter.student_review, '')

    def test_a_change_request_needs_a_note_and_a_known_decision(self):
        letter = self.write_letter(shared_with_student=True)
        blank = self.review(self.student_user, letter, decision='changes_requested', note='   ')
        self.assertEqual(blank.status_code, 400)
        self.assertIn('note', blank.data)
        self.assertEqual(self.review(self.student_user, letter, decision='maybe').status_code, 400)
        letter.refresh_from_db()
        self.assertEqual(letter.student_review, '')

    def test_a_private_or_unwritten_letter_cannot_be_reviewed(self):
        private = self.write_letter()
        unwritten = RecommendationLetter.objects.create(student=self.student, recommender_name='Physics teacher', shared_with_student=True)
        for letter in (private, unwritten):
            self.assertEqual(self.review(self.student_user, letter, decision='confirmed').status_code, 400)
            letter.refresh_from_db()
            self.assertEqual(letter.student_review, '')

    def test_nobody_else_can_answer_for_the_student(self):
        letter = self.write_letter(shared_with_student=True)
        expected = {
            self.counselor: 403, self.admin: 403, self.organization: 403, self.teacher: 403,
            self.parent: 404, self.student_b_user: 404, self.counselor_b: 404,
        }
        for user, status in expected.items():
            response = self.review(user, letter, decision='confirmed')
            self.assertEqual(response.status_code, status, user.username)
        letter.refresh_from_db()
        self.assertEqual((letter.student_review, letter.student_reviewed_at), ('', None))

    def test_a_new_text_clears_the_review_and_other_edits_keep_it(self):
        letter = self.write_letter(shared_with_student=True)
        self.review(self.student_user, letter, decision='changes_requested', note='Add the robotics award.')
        self.client.force_authenticate(self.counselor)
        kept = self.client.patch(f'/api/recommendations/{letter.id}/', {'deadline': '2026-12-01', 'body': LETTER_TEXT}, format='json')
        self.assertEqual(kept.data['student_review'], 'changes_requested')
        edited = self.client.patch(
            f'/api/recommendations/{letter.id}/', {'body': f'{LETTER_TEXT} She won the regional robotics award.'}, format='json',
        )
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual((edited.data['student_review'], edited.data['student_review_note'], edited.data['student_reviewed_at']), ('', '', None))

    def test_the_review_is_not_writable_through_the_letter(self):
        letter = self.write_letter(shared_with_student=True)
        self.client.force_authenticate(self.counselor)
        response = self.client.patch(f'/api/recommendations/{letter.id}/', {'student_review': 'confirmed'}, format='json')
        self.assertEqual(response.status_code, 200)
        letter.refresh_from_db()
        self.assertEqual(letter.student_review, '')

    def test_the_school_never_sees_the_review(self):
        self.write_letter(shared_with_student=True, student_review='changes_requested', student_review_note='Fix my award year.')
        [row] = self.rows(self.organization)
        for field in ('student_review', 'student_review_note', 'student_reviewed_at'):
            self.assertNotIn(field, row)
