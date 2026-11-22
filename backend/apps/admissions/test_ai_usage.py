import csv
import io
import tempfile
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admissions import ai_usage
from apps.admissions.models import AiUsageLog, School
from apps.users.models import User


def make_user(name, school=None, role=User.Role.STUDENT):
    return User.objects.create_user(username=name, email=f'{name}@example.com', role=role, school=school)


class RecordSetup:
    def setUp(self):
        self.school = School.objects.create(name='Usage School', code='usage-school')
        self.user = make_user('usage-student', self.school)

    def answered(self, **extra):
        sink = ai_usage.begin()
        ai_usage.capture({'choices': [{'message': {'content': 'x' * 400}}], **extra},
                         {'model': 'openai/gpt-5.4-mini', 'messages': [{'role': 'user', 'content': 'y' * 800}]})
        return sink


class RecordTests(RecordSetup, TestCase):
    def test_provider_usage_is_stored_as_reported(self):
        self.answered(model='openai/gpt-5.4-mini', usage={
            'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15,
            'prompt_tokens_details': {'cached_tokens': 4}, 'completion_tokens_details': {'reasoning_tokens': 2},
        })
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.OK)
        row = AiUsageLog.objects.get()
        self.assertEqual((row.input_tokens, row.output_tokens, row.cached_input_tokens, row.reasoning_tokens,
                          row.total_tokens, row.usage_estimated), (10, 5, 4, 2, 15, False))

    def test_missing_usage_is_estimated_from_characters(self):
        self.answered()
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.OK)
        row = AiUsageLog.objects.get()
        self.assertEqual((row.input_tokens, row.output_tokens, row.total_tokens, row.usage_estimated), (200, 100, 300, True))

    def test_malformed_usage_values_never_break_recording(self):
        self.answered(usage={'prompt_tokens': 'many', 'completion_tokens': -3, 'total_tokens': None})
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.OK)
        row = AiUsageLog.objects.get()
        # Nothing usable in the block: estimated from characters, not stored as exact zeros.
        self.assertEqual((row.total_tokens, row.usage_estimated), (300, True))

    def test_failed_status_depends_on_whether_the_provider_answered(self):
        ai_usage.begin()
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.FAILED)
        self.answered(usage={'prompt_tokens': 7, 'completion_tokens': 1, 'total_tokens': 8})
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.FAILED)
        statuses = list(AiUsageLog.objects.order_by('id').values_list('status', 'total_tokens'))
        self.assertEqual(statuses, [('provider_error', 0), ('invalid_output', 8)])

    def test_refusals_and_local_answers_have_no_tokens_or_provider(self):
        self.answered(usage={'prompt_tokens': 9, 'completion_tokens': 9, 'total_tokens': 18})
        ai_usage.record('assistant', self.user, provider='gateway', status=ai_usage.BUDGET_REFUSED)
        row = AiUsageLog.objects.get()
        self.assertEqual((row.status, row.total_tokens, row.provider, row.model, row.latency_ms), ('budget_refused', 0, '', '', 0))

    def test_different_model_in_the_reply_marks_the_gateway_fallback(self):
        self.answered(model='openai/gpt-5.4-nano', usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2})
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.OK)
        row = AiUsageLog.objects.get()
        self.assertEqual((row.model, row.fallback_used), ('openai/gpt-5.4-nano', True))

    def test_dated_snapshot_of_the_requested_model_is_not_a_fallback(self):
        self.answered(model='openai/gpt-5.4-mini-2026-03-01', usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2})
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.OK)
        self.assertFalse(AiUsageLog.objects.get().fallback_used)

    def test_error_body_without_choices_or_usage_is_not_an_answer(self):
        ai_usage.begin()
        ai_usage.capture({'error': {'message': 'overloaded'}}, {'model': 'm', 'messages': []})
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.FAILED)
        row = AiUsageLog.objects.get()
        self.assertEqual((row.status, row.total_tokens), ('provider_error', 0))

    def test_record_never_raises(self):
        with mock.patch.object(AiUsageLog.objects, 'create', side_effect=RuntimeError('db down')), \
                self.assertLogs('naseeb.ai_usage', level='ERROR'):
            ai_usage.record('assistant', self.user, provider='gateway', status=ai_usage.OK)

    def test_only_counts_are_stored(self):
        stored = {field.name for field in AiUsageLog._meta.get_fields()}
        self.assertFalse({'prompt', 'content', 'response', 'text', 'messages', 'essay'} & stored)


class TokenKeyTests(RecordSetup, TestCase):
    def last(self):
        return AiUsageLog.objects.latest('id')

    def test_anthropic_style_usage_keys_are_read_as_exact(self):
        self.answered(usage={'input_tokens': 100, 'output_tokens': 50, 'cache_read_input_tokens': 30})
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.OK)
        row = self.last()
        self.assertEqual((row.input_tokens, row.output_tokens, row.total_tokens, row.cached_input_tokens), (100, 50, 150, 30))
        self.assertFalse(row.usage_estimated)

    def test_input_tokens_details_cached_count(self):
        self.answered(usage={'input_tokens': 10, 'output_tokens': 5, 'input_tokens_details': {'cached_tokens': 4}})
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.OK)
        self.assertEqual(self.last().cached_input_tokens, 4)

    def test_unrecognised_usage_block_is_estimated_not_zero(self):
        self.answered(usage={'something_else': 7})
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.OK)
        row = self.last()
        self.assertEqual((row.input_tokens, row.output_tokens), (200, 100))
        self.assertTrue(row.usage_estimated)


class RefundedCallTests(RecordSetup, TestCase):
    def test_refunded_failure_is_an_attempt_not_a_paid_call(self):
        ai_usage.begin()
        ai_usage.record('education_match', self.user, provider='gateway', status=ai_usage.FAILED, refunded=True)
        ai_usage.begin()
        ai_usage.record('education_match', self.user, provider='gateway', status=ai_usage.FAILED)
        data = ai_usage.summary(timezone.now() - timedelta(days=1))['features']['education_match']
        self.assertEqual((data['calls'], data['paid_calls'], data['refunded_calls']), (2, 1, 1))
        self.assertEqual(data['error_rate'], 1.0)

    def test_refunded_flag_is_ignored_for_non_provider_statuses(self):
        ai_usage.record('essay_coach', self.user, provider='gateway', status=ai_usage.BUDGET_REFUSED, refunded=True)
        self.assertFalse(AiUsageLog.objects.get().refunded)

    def test_feature_lists_share_one_source(self):
        from apps.admissions import ai_budget
        self.assertIs(ai_usage.FEATURES, ai_budget.FEATURES)


class SummaryTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='Summary School', code='summary-school')
        for tokens, status_, fallback in ((100, 'ok', False), (200, 'ok', False), (300, 'ok', True), (1000, 'invalid_output', False)):
            AiUsageLog.objects.create(feature='essay_coach', school=self.school, status=status_, input_tokens=tokens,
                                      output_tokens=tokens // 10, total_tokens=tokens + tokens // 10, fallback_used=fallback)
        AiUsageLog.objects.create(feature='essay_coach', school=self.school, status='budget_refused')
        AiUsageLog.objects.create(feature='assistant', status='local_fallback')
        AiUsageLog.objects.create(feature='assistant', status='ok', input_tokens=50, output_tokens=5, total_tokens=55)
        old = AiUsageLog.objects.create(feature='assistant', status='ok', input_tokens=999, total_tokens=999)
        AiUsageLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=90))

    def test_per_feature_numbers_use_paid_calls_only_and_respect_the_window(self):
        data = ai_usage.summary(timezone.now() - timedelta(days=30))
        coach = data['features']['essay_coach']
        self.assertEqual((coach['calls'], coach['paid_calls'], coach['ok_calls'], coach['budget_refused']), (5, 4, 3, 1))
        self.assertEqual(coach['error_rate'], 0.25)
        self.assertEqual(coach['fallback_rate'], 0.25)
        self.assertEqual(coach['input_tokens'], {'sum': 1600, 'avg': 400.0, 'max': 1000, 'p50': 200, 'p90': 1000})
        assistant = data['features']['assistant']
        self.assertEqual((assistant['calls'], assistant['local_fallback'], assistant['input_tokens']['sum']), (2, 1, 50))
        self.assertEqual({row['feature'] for row in data['days']}, {'essay_coach', 'assistant'})
        self.assertEqual([row['school_id'] for row in data['schools'] if row['feature'] == 'essay_coach'], [self.school.pk])

    def test_feature_filter(self):
        data = ai_usage.summary(timezone.now() - timedelta(days=30), 'assistant')
        self.assertEqual(list(data['features']), ['assistant'])

    def test_purge_deletes_only_old_rows(self):
        self.assertEqual(ai_usage.purge(timezone.now() - timedelta(days=30)), 1)
        self.assertEqual(AiUsageLog.objects.count(), 7)


class AdminEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        AiUsageLog.objects.create(feature='essay_coach', status='ok', input_tokens=100, output_tokens=20, total_tokens=120)
        self.support = User.objects.create_user(
            username='usage-admin', email='usage-admin@example.com', role=User.Role.ADMIN, admin_tier=User.AdminTier.SUPPORT,
        )

    def test_support_staff_get_token_aggregates(self):
        self.client.force_authenticate(self.support)
        data = self.client.get('/api/admin/ai-usage/?days=7').data
        self.assertEqual(data['tokens']['window_days'], 7)
        self.assertEqual(data['tokens']['features']['essay_coach']['input_tokens']['sum'], 100)

    def test_feature_filter(self):
        AiUsageLog.objects.create(feature='assistant', status='ok', input_tokens=5, total_tokens=5)
        self.client.force_authenticate(self.support)
        data = self.client.get('/api/admin/ai-usage/?feature=assistant').data
        self.assertEqual(list(data['tokens']['features']), ['assistant'])

    def test_unknown_feature_is_rejected_before_it_reaches_the_cache(self):
        self.client.force_authenticate(self.support)
        self.assertEqual(self.client.get('/api/admin/ai-usage/?feature=nope').status_code, 400)

    def test_repeat_views_reuse_the_aggregates_for_a_minute(self):
        self.client.force_authenticate(self.support)
        with mock.patch.object(ai_usage, 'summary', wraps=ai_usage.summary) as summary:
            self.client.get('/api/admin/ai-usage/?days=7')
            self.client.get('/api/admin/ai-usage/?days=7')
            self.client.get('/api/admin/ai-usage/?days=8')
        self.assertEqual(summary.call_count, 2)

    def test_bad_days_fall_back_and_are_capped(self):
        self.client.force_authenticate(self.support)
        self.assertEqual(self.client.get('/api/admin/ai-usage/?days=abc').data['tokens']['window_days'], 30)
        self.assertEqual(self.client.get('/api/admin/ai-usage/?days=99999').data['tokens']['window_days'], 365)

    def test_response_lists_features_from_the_backend_and_has_no_estimate_without_prices(self):
        from apps.admissions import ai_budget
        self.client.force_authenticate(self.support)
        data = self.client.get('/api/admin/ai-usage/').data
        self.assertEqual(data['feature_names'], list(ai_budget.FEATURES))
        self.assertEqual(set(data['features']), set(ai_budget.FEATURES))
        self.assertIsNone(data['cost_estimate'])
        self.assertIsNone(data['today_from_log'])

    def test_cost_estimate_uses_one_configured_price(self):
        self.client.force_authenticate(self.support)
        AiUsageLog.objects.all().delete()
        AiUsageLog.objects.create(feature='essay_coach', status='ok', input_tokens=1_000_000, output_tokens=500_000,
                                  total_tokens=1_500_000)
        with self.settings(AI_COST_PER_MTOK_INPUT=1, AI_COST_PER_MTOK_OUTPUT=2):
            data = self.client.get('/api/admin/ai-usage/').data
        estimate = data['cost_estimate']
        self.assertEqual(estimate['assumes'], 'one_price_for_all_models')
        self.assertEqual(estimate['features']['essay_coach'], 2.0)
        self.assertEqual(estimate['total_usd'], 2.0)

    def test_cache_outage_reads_today_from_the_log_and_skips_refunded_rows(self):
        school = School.objects.create(name='Log School', code='log-school')
        for _ in range(3):
            AiUsageLog.objects.create(feature='assistant', school=school, status='ok')
        AiUsageLog.objects.create(feature='assistant', school=school, status='provider_error', refunded=True)
        AiUsageLog.objects.create(feature='assistant', school=school, status='local_fallback')
        old = AiUsageLog.objects.create(feature='assistant', school=school, status='ok')
        AiUsageLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))
        self.client.force_authenticate(self.support)
        with mock.patch('apps.admissions.ai_budget.cache_get_many', return_value=None):
            data = self.client.get('/api/admin/ai-usage/').data
        self.assertFalse(data['cache_available'])
        self.assertEqual(data['today_from_log']['assistant']['used'], 3)
        self.assertEqual(data['today_from_log']['assistant']['top_schools'][0]['name'], 'Log School')

    def test_students_are_refused(self):
        self.client.force_authenticate(make_user('usage-student2', role=User.Role.STUDENT))
        self.assertEqual(self.client.get('/api/admin/ai-usage/').status_code, status.HTTP_403_FORBIDDEN)


class ReportCommandTests(TestCase):
    def setUp(self):
        for tokens in (1_000_000, 3_000_000):
            AiUsageLog.objects.create(feature='essay_coach', status='ok', input_tokens=tokens,
                                      output_tokens=tokens // 2, total_tokens=tokens + tokens // 2)

    def run_command(self, *args):
        out = io.StringIO()
        call_command('ai_usage_report', *args, stdout=out)
        return out.getvalue()

    def test_prints_a_table_and_costs_with_given_prices(self):
        text = self.run_command('--price-input', '0.5', '--price-output', '2')
        header, line = text.strip().splitlines()
        columns = dict(zip(header.split('\t'), line.split('\t')))
        self.assertEqual(columns['group'], 'essay_coach')
        self.assertEqual(columns['input_tokens_sum'], '4000000')
        self.assertEqual(float(columns['cost_usd']), 4 * 0.5 + 2 * 2)
        self.assertEqual(float(columns['cost_per_paid_call_usd']), 3.0)

    def test_cost_per_paid_call_excludes_refunded_attempts(self):
        AiUsageLog.objects.create(feature='essay_coach', status='provider_error', refunded=True)
        text = self.run_command('--price-input', '0.5', '--price-output', '2')
        header, line = text.strip().splitlines()
        columns = dict(zip(header.split('\t'), line.split('\t')))
        self.assertEqual(columns['paid_calls'], '2')
        self.assertEqual(float(columns['cost_per_paid_call_usd']), 3.0)

    def test_no_prices_means_no_cost_columns(self):
        self.assertNotIn('cost_usd', self.run_command())

    def test_csv_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path = f'{folder}/usage.csv'
            self.run_command('--csv', path, '--by', 'day')
            rows = list(csv.reader(open(path)))
        self.assertEqual(rows[0][0], 'group')
        self.assertTrue(rows[1][0].startswith('essay_coach:'))

    def test_prices_must_come_in_pairs(self):
        with self.assertRaises(CommandError):
            self.run_command('--price-input', '1')

    def test_purge_option(self):
        old = AiUsageLog.objects.first()
        AiUsageLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=100))
        self.assertIn('Deleted 1 rows', self.run_command('--purge-older-than', '30'))
        self.assertEqual(AiUsageLog.objects.count(), 1)
