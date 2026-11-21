"""Education-match AI: gateway, daily budget, cache, de-identification, permissions."""
import json
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status

from apps.users.models import User

from .. import ai_budget
from ..models import AiUsageLog, ChallengeAttempt
from .base import RoleIsolationBase

URL = '/api/education-matches/ai/'
PAYLOAD = {'major_candidates': ['Computer Science', 'Economics'], 'subject_strengths': ['Mathematics']}
ANSWER = {
    'summary': 'Good fit.',
    'questions_to_consider': ['What do you enjoy?'],
    'major_guidance': [{
        'major': 'Computer Science', 'why_fit': 'Logic.',
        'subjects_to_focus': ['Mathematics'], 'explore_next': 'Try a project.',
    }],
}


def gateway_reply(answer=ANSWER):
    body = json.dumps({
        'choices': [{'message': {'content': json.dumps(answer)}}],
        'model': 'openai/gpt-5.4-nano',
        'usage': {'prompt_tokens': 900, 'completion_tokens': 200, 'total_tokens': 1100},
    }).encode()
    reply = mock.MagicMock()
    reply.read.return_value = body
    reply.__enter__.return_value = reply
    return reply


@override_settings(
    OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='gateway-key',
    EDUCATION_MATCH_DAILY_BUDGET=100, EDUCATION_MATCH_SCHOOL_DAILY_BUDGET=100, EDUCATION_MATCH_USER_DAILY_LIMIT=100,
)
class EducationMatchAITests(RoleIsolationBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.client.force_authenticate(self.student_a_user)

    def post(self, payload=PAYLOAD):
        return self.client.post(URL, payload, format='json')

    def used(self, key=''):
        day = timezone.localdate().isoformat()
        return cache.get(f'ai-budget:education_match:{day}{key}')

    def test_answers_through_the_pinned_gateway_model_at_temperature_zero(self):
        with mock.patch('urllib.request.urlopen', return_value=gateway_reply()) as urlopen:
            response = self.post()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['mode'], 'ai')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'https://ai-gateway.vercel.sh/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer gateway-key')
        body = json.loads(request.data)
        self.assertEqual(body['model'], 'openai/gpt-5.4-nano')
        self.assertEqual(body['temperature'], 0)
        self.assertNotIn('providerOptions', body)

    def test_budget_is_consumed_and_usage_logged_with_counts_only(self):
        with mock.patch('urllib.request.urlopen', return_value=gateway_reply()):
            self.post()
        self.assertEqual(self.used(), 1)
        self.assertEqual(self.used(f':school:{self.school_a.pk}'), 1)
        self.assertEqual(self.used(f':user:{self.student_a_user.pk}'), 1)
        row = AiUsageLog.objects.get(feature='education_match')
        self.assertEqual((row.status, row.provider, row.model, row.input_tokens, row.output_tokens),
                         ('ok', 'gateway', 'openai/gpt-5.4-nano', 900, 200))

    def test_provider_failure_is_503_and_refunds_every_counter(self):
        with mock.patch('urllib.request.urlopen', side_effect=OSError('down')):
            response = self.post()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(self.used(), 0)
        self.assertEqual(self.used(f':school:{self.school_a.pk}'), 0)
        self.assertEqual(self.used(f':user:{self.student_a_user.pk}'), 0)
        self.assertEqual(AiUsageLog.objects.get(feature='education_match').status, 'provider_error')

    def test_unusable_answer_is_503_and_refunded(self):
        with mock.patch('urllib.request.urlopen', return_value=gateway_reply({'summary': 'x', 'major_guidance': []})):
            response = self.post()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(self.used(), 0)
        self.assertEqual(AiUsageLog.objects.get(feature='education_match').status, 'invalid_output')

    @override_settings(EDUCATION_MATCH_USER_DAILY_LIMIT=1)
    def test_daily_limit_is_429_with_no_call(self):
        other = {'major_candidates': ['Economics']}
        with mock.patch('urllib.request.urlopen', return_value=gateway_reply()) as urlopen:
            self.assertEqual(self.post().status_code, status.HTTP_200_OK)
            response = self.post(other)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(self.used(), 1)
        self.assertEqual(AiUsageLog.objects.filter(feature='education_match', status='budget_refused').count(), 1)

    @override_settings(OUTBOUND_AI_ENABLED=False)
    def test_ai_off_is_503_with_no_call_and_no_budget(self):
        with mock.patch('urllib.request.urlopen') as urlopen:
            response = self.post()
        urlopen.assert_not_called()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIsNone(self.used())

    def test_cache_hit_makes_no_call_and_costs_no_budget(self):
        with mock.patch('urllib.request.urlopen', return_value=gateway_reply()) as urlopen:
            first = self.post()
            second = self.post()
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(second.data, first.data)
        self.assertEqual(self.used(), 1)
        self.assertEqual(AiUsageLog.objects.filter(feature='education_match').count(), 1)

    def test_changed_assessment_version_or_majors_miss_the_cache(self):
        with mock.patch('urllib.request.urlopen', return_value=gateway_reply()) as urlopen:
            self.post()
            ChallengeAttempt.objects.create(
                student=self.student_a, challenge='interests', instrument_version='v2', scores={'R': 3},
            )
            self.post()
            self.post({'major_candidates': ['Economics']})
        self.assertEqual(urlopen.call_count, 3)

    def test_cache_is_per_student(self):
        with mock.patch('urllib.request.urlopen', return_value=gateway_reply()) as urlopen:
            self.post()
            self.client.force_authenticate(self.student_b_user)
            self.post()
        self.assertEqual(urlopen.call_count, 2)

    def test_request_body_is_de_identified(self):
        self.student_a.grade = 11
        self.student_a.gpa = '4.50'
        self.student_a.sat_score = 1400
        self.student_a.save(update_fields=['grade', 'gpa', 'sat_score', 'updated_at'])
        ChallengeAttempt.objects.create(
            student=self.student_a, challenge='personality', instrument_version='bfi-50', scores={'openness': 4.1},
        )
        user = self.student_a_user
        user.first_name, user.last_name = 'Zarina', 'Karimova'
        user.save(update_fields=['first_name', 'last_name'])
        with mock.patch('urllib.request.urlopen', return_value=gateway_reply()) as urlopen:
            self.post()
        raw = urlopen.call_args.args[0].data.decode('utf-8')
        body = json.loads(raw)
        sent = json.loads(body['messages'][1]['content'])
        self.assertEqual(set(sent), {'assessment_scores', 'academic_profile', 'candidate_majors', 'subject_strengths'})
        self.assertEqual(sent['assessment_scores']['personality']['instrument_version'], 'bfi-50')
        self.assertEqual(set(sent['academic_profile']), {'grade', 'gpa', 'sat_score', 'ielts_score'})
        for identifying in (user.username, user.email, 'Zarina', 'Karimova', self.school_a.name, self.school_a.code,
                            self.counselor.username, self.counselor.email, 'school_name', 'email', 'username'):
            self.assertNotIn(identifying, raw)

    def test_only_students_may_use_it(self):
        for user in (self.counselor, self.teacher, self.organization):
            self.client.force_authenticate(user)
            with mock.patch('urllib.request.urlopen') as urlopen:
                response = self.post()
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, user.role)
            urlopen.assert_not_called()
        self.client.force_authenticate(None)
        self.assertIn(self.post().status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_user_without_student_profile_is_refused(self):
        lone = User.objects.create_user(username='lone', email='lone@example.com', role=User.Role.STUDENT, school=self.school_a)
        self.client.force_authenticate(lone)
        self.assertEqual(self.post().status_code, status.HTTP_403_FORBIDDEN)


@override_settings(EDUCATION_MATCH_DAILY_BUDGET=5, EDUCATION_MATCH_SCHOOL_DAILY_BUDGET=5, EDUCATION_MATCH_USER_DAILY_LIMIT=5)
class EducationBudgetRefundTests(RoleIsolationBase):
    def test_refund_undoes_consume(self):
        cache.clear()
        self.addCleanup(cache.clear)
        user = self.student_a_user
        self.assertTrue(ai_budget.consume('education_match', user))
        ai_budget.refund('education_match', user)
        day = timezone.localdate().isoformat()
        self.assertEqual(cache.get(f'ai-budget:education_match:{day}'), 0)
