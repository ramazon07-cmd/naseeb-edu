import json
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions import ai_budget
from apps.admissions.models import School
from apps.users.models import User

from .test_essay_lab import BASE, EssayLabTestCase, gateway_response


def fresh_fallback():
    return mock.patch.object(ai_budget, '_fallback', ai_budget._ProcessFallback())


@override_settings(
    AI_ASSISTANT_DAILY_BUDGET=100, AI_ASSISTANT_SCHOOL_DAILY_BUDGET=100, AI_ASSISTANT_USER_DAILY_LIMIT=100,
    AI_FALLBACK_PROCESS_DAILY_BUDGET=2,
)
class AiBudgetTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.school_a = School.objects.create(name='Budget A', code='budget-a')
        self.school_b = School.objects.create(name='Budget B', code='budget-b')
        self.a1, self.a2 = (self.user(f'a{i}', self.school_a) for i in (1, 2))
        self.b1 = self.user('b1', self.school_b)

    @staticmethod
    def user(name, school):
        return User.objects.create_user(username=name, email=f'{name}@example.com', role=User.Role.STUDENT,
                                        school=school)

    def spend(self, user, times=1, feature='assistant'):
        return [ai_budget.consume(feature, user) for _ in range(times)]

    def global_count(self, feature='assistant'):
        return cache.get(f'ai-budget:{feature}:{timezone.localdate().isoformat()}')

    @override_settings(AI_ASSISTANT_USER_DAILY_LIMIT=2)
    def test_per_user_cap(self):
        self.assertEqual(self.spend(self.a1, 3), [True, True, False])
        self.assertEqual(self.spend(self.a2), [True])

    @override_settings(AI_ASSISTANT_SCHOOL_DAILY_BUDGET=3)
    def test_per_school_cap(self):
        self.assertEqual(self.spend(self.a1, 2) + self.spend(self.a2, 2), [True, True, True, False])
        self.assertEqual(self.spend(self.b1), [True])

    @override_settings(AI_ASSISTANT_SCHOOL_DAILY_BUDGET=1)
    def test_a_refused_call_is_refunded_from_every_cap(self):
        self.assertEqual(self.spend(self.a1, 5), [True, False, False, False, False])
        self.assertEqual(self.global_count(), 1)

    @override_settings(AI_ASSISTANT_DAILY_BUDGET=2)
    def test_global_cap(self):
        self.assertEqual(self.spend(self.a1) + self.spend(self.b1) + self.spend(self.a2), [True, True, False])

    @override_settings(AI_ASSISTANT_DAILY_BUDGET=0, AI_ASSISTANT_SCHOOL_DAILY_BUDGET=0, AI_ASSISTANT_USER_DAILY_LIMIT=0)
    def test_zero_means_no_cap_for_the_assistant(self):
        self.assertEqual(self.spend(self.a1, 3), [True, True, True])

    @override_settings(ESSAY_COACH_DAILY_BUDGET=0)
    def test_zero_coach_budget_turns_ai_checks_off(self):
        self.assertEqual(self.spend(self.a1, feature='essay_coach'), [False])

    def test_cache_outage_uses_a_small_per_process_allowance(self):
        with fresh_fallback(), mock.patch.object(ai_budget, 'count_hits', return_value=None), \
                self.assertLogs('naseeb.ai_budget', level='WARNING'):
            self.assertEqual(self.spend(self.a1) + self.spend(self.b1) + self.spend(self.a2), [True, True, False])

    @override_settings(AI_FALLBACK_PROCESS_DAILY_BUDGET=0)
    def test_cache_outage_can_fail_closed(self):
        with fresh_fallback(), mock.patch.object(ai_budget, 'count_hits', return_value=None), \
                self.assertLogs('naseeb.ai_budget', level='WARNING'):
            self.assertEqual(self.spend(self.a1), [False])

    @override_settings(
        AI_GATEWAY_API_KEY='test-key', AI_FALLBACK_PROCESS_DAILY_BUDGET=1,
        CACHES={'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                            'LOCATION': 'redis://127.0.0.1:1/0'}},
    )
    def test_assistant_spend_is_bounded_during_a_redis_outage(self):
        self.client.force_authenticate(self.a1)
        with fresh_fallback(), mock.patch('apps.admissions.assistant._gateway_stream',
                                          side_effect=lambda *a: iter(['ok'])) as gateway, \
                self.assertLogs('naseeb', level='WARNING'):
            for _ in range(3):
                response = self.client.post('/api/assistant/chat/',
                                            {'messages': [{'role': 'user', 'content': 'Help'}]}, format='json')
                b''.join(response.streaming_content)
        self.assertEqual(gateway.call_count, 1)


@override_settings(AI_GATEWAY_API_KEY='test-key', ESSAY_COACH_MIN_INTERVAL_SECONDS=0, ESSAY_COACH_USER_DAILY_LIMIT=1)
class EssayCoachBudgetTests(EssayLabTestCase):
    def test_per_user_daily_limit(self):
        essay = self.make_essay()
        payload = {'summary': 'ok', 'strengths': [], 'scores': {}, 'notes': []}

        def check():
            with mock.patch('urllib.request.urlopen', return_value=gateway_response(json.dumps(payload))):
                return self.client.post(f'{BASE}/essays/{essay.pk}/depth-check/', {'base_seq': 0},
                                        format='json')

        self.assertEqual(check().status_code, status.HTTP_200_OK)
        response = check()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['code'], 'coach_resting')
