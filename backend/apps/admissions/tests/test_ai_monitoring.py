"""AI monitoring (latency, error rate, cost), the Health page section, the report and ai_eval."""
import io
from datetime import timedelta

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.admissions import ai_budget, ai_eval, ai_usage
from apps.admissions.models import AiUsageLog, School
from apps.users.models import User


def log(feature='assistant', status='ok', latency=100, input_tokens=1000, output_tokens=500, user=None):
    return AiUsageLog.objects.create(
        feature=feature, status=status, provider='gateway', model='m', latency_ms=latency,
        input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens, user=user,
    )


class SummaryTests(TestCase):
    def since(self):
        return timezone.now() - timedelta(days=1)

    def test_latency_percentiles_error_rate_and_tokens(self):
        for latency in (100, 200, 300, 400, 5000):
            log(latency=latency)
        log(status='provider_error', latency=900)
        log(status='local_fallback', latency=0, input_tokens=0, output_tokens=0)
        row = ai_usage.summary(self.since())['features']['assistant']
        self.assertEqual(row['paid_calls'], 6)
        self.assertEqual(row['latency_ms']['p50'], 300)
        self.assertEqual(row['latency_ms']['p95'], 5000)
        self.assertEqual(row['error_rate'], round(1 / 6, 4))
        self.assertEqual(row['input_tokens']['sum'], 6000)
        self.assertIsNone(row['cost_usd'])

    @override_settings(AI_PRICE_INPUT_USD_PER_1M='0.5', AI_PRICE_OUTPUT_USD_PER_1M='2')
    def test_cost_uses_configured_prices(self):
        log(input_tokens=1_000_000, output_tokens=500_000)
        self.assertEqual(ai_usage.summary(self.since())['features']['assistant']['cost_usd'], 1.5)

    @override_settings(AI_PRICE_INPUT_USD_PER_1M='abc', AI_PRICE_OUTPUT_USD_PER_1M='2')
    def test_bad_prices_mean_no_cost(self):
        self.assertIsNone(ai_usage.prices())

    def test_monitoring_lists_every_feature(self):
        log('essay_coach')
        features = ai_usage.monitoring(self.since())
        self.assertEqual(set(features), set(ai_usage.FEATURES))
        self.assertEqual(features['essay_coach']['paid_calls'], 1)
        self.assertEqual(features['assistant']['paid_calls'], 0)
        self.assertEqual(features['assistant']['latency_p95_ms'], 0)


class HealthEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.ops = User.objects.create_user(
            username='ai-ops', email='ai-ops@example.com', password='StrongPass123!',
            role=User.Role.ADMIN, admin_tier=User.AdminTier.OPS,
        )
        self.client.force_authenticate(self.ops)

    @override_settings(OUTBOUND_AI_ENABLED=False, AI_GATEWAY_API_KEY='secret-key')
    def test_health_reports_ai_counters_and_no_secrets_or_content(self):
        log('recommendation_letter', latency=250)
        response = self.client.get('/api/admin/health/')
        ai = response.data['ai']
        self.assertFalse(ai['outbound_enabled'])
        self.assertTrue(ai['gateway_key_set'])
        self.assertFalse(ai['cost_estimated'])
        self.assertEqual(ai['features']['recommendation_letter']['latency_p50_ms'], 250)
        self.assertNotIn('secret-key', str(response.data))

    def test_old_calls_are_outside_the_24_hour_window(self):
        old = log()
        AiUsageLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=3))
        self.assertEqual(self.client.get('/api/admin/health/').data['ai']['features']['assistant']['calls'], 0)


class ReportCommandTests(TestCase):
    def test_report_shows_latency_and_error_rate_and_configured_cost(self):
        log(latency=120, input_tokens=1_000_000, output_tokens=0)
        out = io.StringIO()
        with override_settings(AI_PRICE_INPUT_USD_PER_1M='3', AI_PRICE_OUTPUT_USD_PER_1M='9'):
            call_command('ai_usage_report', stdout=out)
        header, line = out.getvalue().splitlines()[:2]
        self.assertIn('latency_p95_ms', header)
        self.assertIn('cost_usd', header)
        self.assertEqual(line.split('\t')[header.split('\t').index('cost_usd')], '3.000000')


class BudgetTests(TestCase):
    def test_education_match_has_its_own_budget(self):
        school = School.objects.create(name='B', code='b')
        user = User.objects.create_user(username='edu', email='edu@example.com', role=User.Role.STUDENT, school=school)
        cache.clear()
        self.assertIn('education_match', ai_budget.FEATURES)
        with override_settings(EDUCATION_MATCH_AI_DAILY_BUDGET=0):
            self.assertFalse(ai_budget.consume('education_match', user))
        with override_settings(EDUCATION_MATCH_AI_USER_DAILY_LIMIT=1):
            self.assertTrue(ai_budget.consume('education_match', user))
            self.assertFalse(ai_budget.consume('education_match', user))


class EvalTests(TestCase):
    def test_every_offline_case_passes(self):
        results = ai_eval.run()
        self.assertGreaterEqual(len(results), 10)
        self.assertEqual([r for r in results if r.passed is not True], [])

    def test_command_passes_and_fails_loudly(self):
        out = io.StringIO()
        call_command('ai_eval', stdout=out)
        self.assertIn('0 failed', out.getvalue())
        original = ai_eval.CASES
        ai_eval.CASES = (('assistant', lambda: (_ for _ in ()).throw(AssertionError('boom'))),)
        ai_eval.CASES[0][1].__name__ = 'boom_case'
        try:
            with self.assertRaises(CommandError):
                call_command('ai_eval', stdout=io.StringIO())
        finally:
            ai_eval.CASES = original

    @override_settings(OUTBOUND_AI_ENABLED=False)
    def test_live_cases_are_skipped_while_outbound_ai_is_off(self):
        results = ai_eval.run(live=True)
        self.assertEqual([r.passed for r in results if r.name.startswith('live_')], [None, None])
