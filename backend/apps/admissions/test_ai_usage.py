import csv
import io
import tempfile
from datetime import timedelta
from unittest import mock

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


class RecordTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='Usage School', code='usage-school')
        self.user = make_user('usage-student', self.school)

    def answered(self, **extra):
        sink = ai_usage.begin()
        ai_usage.capture({'choices': [{'message': {'content': 'x' * 400}}], **extra},
                         {'model': 'openai/gpt-5.4-mini', 'messages': [{'role': 'user', 'content': 'y' * 800}]})
        return sink

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
        self.assertEqual(AiUsageLog.objects.get().total_tokens, 0)

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

    def test_record_never_raises(self):
        with mock.patch.object(AiUsageLog.objects, 'create', side_effect=RuntimeError('db down')), \
                self.assertLogs('naseeb.ai_usage', level='ERROR'):
            ai_usage.record('assistant', self.user, provider='gateway', status=ai_usage.OK)

    def test_only_counts_are_stored(self):
        stored = {field.name for field in AiUsageLog._meta.get_fields()}
        self.assertFalse({'prompt', 'content', 'response', 'text', 'messages', 'essay'} & stored)


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

    def test_bad_days_fall_back_and_are_capped(self):
        self.client.force_authenticate(self.support)
        self.assertEqual(self.client.get('/api/admin/ai-usage/?days=abc').data['tokens']['window_days'], 30)
        self.assertEqual(self.client.get('/api/admin/ai-usage/?days=99999').data['tokens']['window_days'], 365)

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
