"""The AI audit fixes: CLI production contract (flags, environment, deadline, process group), one JSON extractor,
refunds, usage accounting, plan checks, grounding and the Telegram import's deadline, backlog and outage handling."""
import json
import os
import tempfile
import time
from io import StringIO
from unittest import mock

from django.core import checks
from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users.models import JobRun, User
from core.checks import ai_cli_model_check, shared_cache_check
from core.environment import build_cache_settings

from . import ai_budget, ai_providers, ai_usage, assistant, education_ai, gateway_errors, match_reasons, rec_letter_ai
from .models import AiUsageLog, School, TelegramImportChannel
from .telegram_import import fetch, formatter, importer, official
from .test_assistant_low_token import CHAT, Fixture
from .test_assistant_review_fixes import used_today
from .test_ai_providers import BODY, CLI, WHICH, cli_output, completed
from .test_college_match import REASONS_URL, MatchFixture
from .test_telegram_import import AI_ON, CLI_IMPORT, GOOD, TODAY

RUN = 'apps.admissions.ai_providers._run_process'


@override_settings(**CLI, AI_CLI_MAX_CONCURRENT=1)
class CliContractTests(SimpleTestCase):
    """What production relies on: flags, environment, one deadline and the process group."""

    def command(self, system=''):
        with mock.patch(WHICH, return_value='/bin/claude'):
            return ai_providers.cli_command(system)

    def test_the_command_turns_off_mcp_tools_sessions_and_settings(self):
        command = self.command('Be brief.')
        self.assertEqual(command[:2], ['/bin/claude', '-p'])
        self.assertIn('--strict-mcp-config', command)
        self.assertEqual(command[command.index('--mcp-config') + 1], '{"mcpServers":{}}')
        self.assertEqual(json.loads(command[command.index('--mcp-config') + 1]), {'mcpServers': {}})
        self.assertEqual(command[command.index('--tools') + 1], '')
        self.assertIn('--no-session-persistence', command)
        self.assertEqual(command[command.index('--setting-sources') + 1], '')
        self.assertIn('--disable-slash-commands', command)
        self.assertEqual(command[command.index('--output-format') + 1], 'json')
        self.assertEqual(command[command.index('--system-prompt') + 1], 'Be brief.')

    def test_the_child_sees_only_allowlisted_variables(self):
        secrets = {
            'SECRET_KEY': 'django-secret', 'DATABASE_URL': 'postgres://u:p@h/db', 'AI_GATEWAY_API_KEY': 'gw-key',
            'REDIS_URL': 'redis://r', 'TELEGRAM_BOT_TOKEN': 'bot', 'AWS_SECRET_ACCESS_KEY': 'aws',
            'PATH': '/usr/bin', 'LANG': 'C.UTF-8', 'CLAUDE_CODE_OAUTH_TOKEN': 'login-token',
        }
        with mock.patch.dict(os.environ, secrets, clear=True), override_settings(AI_CLI_HOME='/var/data/claude'):
            env = ai_providers._cli_environment()
        self.assertEqual(set(env) - {'DISABLE_AUTOUPDATER', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'},
                         {'PATH', 'LANG', 'CLAUDE_CODE_OAUTH_TOKEN', 'HOME'})
        self.assertEqual(env['HOME'], '/var/data/claude')
        self.assertEqual((env['DISABLE_AUTOUPDATER'], env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC']), ('1', '1'))
        for name in ('SECRET_KEY', 'DATABASE_URL', 'AI_GATEWAY_API_KEY', 'REDIS_URL', 'TELEGRAM_BOT_TOKEN'):
            self.assertNotIn(name, env)

    def test_a_real_child_process_gets_that_environment_and_the_prompt_on_stdin(self):
        script = 'import os,sys,json; print(json.dumps({"result": sys.stdin.read() + "|" + str("SECRET_KEY" in os.environ)}))'
        with mock.patch.dict(os.environ, {'SECRET_KEY': 'django-secret', 'PATH': os.environ['PATH']}):
            returncode, stdout, _ = ai_providers._run_process(['python3', '-c', script], 'the prompt', 20)
        self.assertEqual((returncode, json.loads(stdout)['result']), (0, 'the prompt|False'))

    def test_a_timeout_kills_the_whole_process_group(self):
        folder = tempfile.mkdtemp()
        pid_file = os.path.join(folder, 'child.pid')
        # The "CLI" starts a grandchild that would outlive it, then waits.
        script = f'sleep 60 & echo $! > {pid_file}; wait'
        started = time.monotonic()
        with self.assertRaises(ai_providers.CliTimeout):
            ai_providers._run_process(['sh', '-c', script], '', 1.0)
        self.assertLess(time.monotonic() - started, 10)
        with open(pid_file) as handle:
            grandchild = int(handle.read().strip())
        for _ in range(50):
            try:
                os.kill(grandchild, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(grandchild, 9)
            self.fail('the grandchild survived the timeout')

    def test_the_slot_wait_comes_out_of_the_call_deadline(self):
        seen = {}

        def run(command, prompt, timeout):
            seen['timeout'] = timeout
            return completed(cli_output())

        original = ai_providers._cli_slot

        def slow_slot(wait=None, reserve=0):
            time.sleep(0.6)  # the queue took 0.6 s
            return original(wait, reserve)

        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN, side_effect=run), \
                mock.patch.object(ai_providers, '_cli_slot', slow_slot):
            ai_providers.chat(BODY, 10)
        self.assertLess(seen['timeout'], 9.5)  # not a fresh 10 s after the wait
        self.assertGreater(seen['timeout'], 8)

    def test_an_earlier_absolute_deadline_wins_over_the_timeout(self):
        seen = {}

        def run(command, prompt, timeout):
            seen['timeout'] = timeout
            return completed(cli_output())

        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN, side_effect=run):
            ai_providers.chat(BODY, 100, deadline=time.monotonic() + 7)
        self.assertLessEqual(seen['timeout'], 7)

    def test_no_time_left_after_the_wait_fails_without_a_process(self):
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN) as run:
            with self.assertRaises(TimeoutError):
                ai_providers.chat(BODY, 100, deadline=time.monotonic() + 0.2)
        run.assert_not_called()

    @override_settings(AI_CLI_SLOT_WAIT_SECONDS=45)
    def test_an_interactive_call_never_waits_more_than_a_few_seconds_for_a_slot(self):
        waits = []

        class Busy:
            def __enter__(self_inner):
                raise ai_providers.CliBusy('busy')

            def __exit__(self_inner, *exc):
                return False

        def slot(wait=None, reserve=0):
            waits.append(wait)
            return Busy()

        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch.object(ai_providers, '_cli_slot', slot):
            with self.assertRaises(ai_providers.CliBusy):
                ai_providers.chat(BODY, 100)
        self.assertLessEqual(waits[0], ai_providers.MAX_INTERACTIVE_SLOT_WAIT)

    def test_cli_failures_are_the_documented_subclasses_and_count_as_unbilled(self):
        for error in (ai_providers.CliBusy('x'), ai_providers.CliTimeout('x'), ai_providers.CliError('x'),
                      ai_providers.CliOutputError('x')):
            self.assertTrue(gateway_errors.is_unbilled(error), error)
        self.assertTrue(issubclass(ai_providers.CliBusy, TimeoutError))
        self.assertTrue(issubclass(ai_providers.CliError, OSError))
        self.assertTrue(issubclass(ai_providers.CliOutputError, ValueError))
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN, return_value=completed('not json')):
            with self.assertRaises(ai_providers.CliOutputError):
                ai_providers.chat(BODY, 5)


class CliMetadataTests(SimpleTestCase):
    def test_the_requested_alias_and_the_cli_reported_model_and_cost_stay_apart(self):
        stdout = cli_output(modelUsage={'claude-real-model-1': {'inputTokens': 3}}, total_cost_usd=0.0123)
        payload = ai_providers._cli_payload(stdout, {'model': 'claude-cli/sonnet'})
        self.assertEqual(payload['model'], 'claude-cli/sonnet')
        self.assertEqual(payload['cli'], {'models': ['claude-real-model-1'], 'total_cost_usd': 0.0123})
        bare = ai_providers._cli_payload(cli_output(), {'model': 'claude-cli/sonnet'})
        self.assertEqual(bare['cli'], {'models': [], 'total_cost_usd': None})


class JsonExtractorTests(SimpleTestCase):
    def test_prose_and_fences_around_the_object_are_ignored(self):
        extract = ai_providers.extract_json
        self.assertEqual(extract('Here is the result:\n{"a": 1}'), {'a': 1})
        self.assertEqual(extract('```json\n{"a": {"b": "}"}}\n```\nDone.'), {'a': {'b': '}'}})
        self.assertEqual(extract('note {not json} then {"ok": true}'), {'ok': True})
        for bad in ('', 'nothing here', '{"cut": ', '[1, 2]'):
            with self.assertRaises(ValueError):
                extract(bad)

    def test_every_feature_reads_a_reply_with_prose_in_front(self):
        from .essay_lab import coach

        payload = {'choices': [{'message': {'content': 'Here is the result:\n```json\n{"x": 2}\n```'}}], 'usage': {}}
        with mock.patch.object(ai_providers, 'chat', return_value=payload):
            self.assertEqual(coach._request_gateway([{'role': 'user', 'content': 'q'}], 100, time.monotonic() + 60), {'x': 2})
            self.assertEqual(rec_letter_ai._request_gateway('s', 'u'), {'x': 2})
        self.assertEqual(education_ai._parse_gateway(json.dumps(payload).encode(), {}), {'x': 2})
        self.assertIs(formatter.extract_json, ai_providers.extract_json)


class LetterHealthFilterTests(SimpleTestCase):
    def test_a_health_sentence_in_the_counselor_draft_never_leaves_the_server(self):
        student = mock.Mock(application_profile={}, grade='11', target_major='Biology', pk=1)
        student.school = None
        draft = 'She leads the robotics club. The student has anxiety and receives therapy. She mentors juniors.'
        with mock.patch.object(rec_letter_ai.letter_coach, 'anonymize', side_effect=lambda text, _s: text):
            message = rec_letter_ai._user_message(student, [], draft, {})
        self.assertNotIn('anxiety', message)
        self.assertNotIn('therapy', message)
        self.assertIn('robotics club', message)
        self.assertIn('mentors juniors', message)

    def test_fact_titles_and_other_free_text_are_filtered_too(self):
        student = mock.Mock(application_profile={'interests': ['chess', 'She has depression and takes medication.']},
                            grade='11', target_major='Biology', pk=1)
        student.school = None
        facts = [{'source': 'honor', 'title': 'The student has anxiety disorder.', 'meta': [], 'detail': ''}]
        with mock.patch.object(rec_letter_ai.letter_coach, 'anonymize', side_effect=lambda text, _s: text):
            message = rec_letter_ai._user_message(student, facts, '', {})
        self.assertNotIn('anxiety', message)
        self.assertNotIn('depression', message)
        self.assertIn('chess', message)


class MatchReasonGroundingTests(SimpleTestCase):
    def test_an_internal_id_is_not_a_fact(self):
        item = {'id': 20, 'admit_rate': 5.0}
        raw = {'reasons': {'20': 'You have a 20% admission chance.'}}
        self.assertEqual(match_reasons.validate(raw, [item], {})['20'], '')
        self.assertEqual(match_reasons.validate({'reasons': {'20': 'Needs 20 points.'}}, [item], {})['20'], '')

    def test_a_personal_admission_chance_is_dropped_even_with_a_known_number(self):
        item = {'id': 7, 'admit_rate': 12.0}
        for line in ('Your chance of admission is 12%.', 'The probability that you get in is high.',
                     'Ваши шансы высоки.', 'Qabul ehtimoli yuqori.'):
            self.assertEqual(match_reasons.validate({'reasons': {'7': line}}, [item], {})['7'], '', line)
        kept = 'The university admits about 12% of applicants.'
        self.assertEqual(match_reasons.validate({'reasons': {'7': kept}}, [item], {})['7'], kept)


class AssistantReplyLimitTests(SimpleTestCase):
    def test_a_long_cli_reply_is_cut_to_the_token_limit_at_a_sentence(self):
        text = 'First sentence here. ' * 100
        cut = assistant.limit_reply(text, 20)
        self.assertLessEqual(len(cut), 80)
        self.assertTrue(cut.endswith('.'))
        self.assertEqual(assistant.limit_reply('Short.', 20), 'Short.')

    def test_the_cli_branch_applies_the_limit(self):
        payload = {'choices': [{'message': {'content': 'Word ' * 500}}], 'usage': {}}
        with override_settings(AI_PROVIDER='claude_cli', APP_ENV='test', AI_ASSISTANT_MAX_OUTPUT_TOKENS=25), \
                mock.patch.object(ai_providers, 'chat', return_value=payload):
            chunks = list(assistant._gateway_stream([{'role': 'user', 'content': 'q'}], 'system'))
        self.assertLessEqual(len(chunks[0]), 101)


class CacheIdentityTests(SimpleTestCase):
    def test_the_assistant_key_changes_with_provider_and_cli_model(self):
        question = 'Explain the SAT format'
        with override_settings(AI_PROVIDER='gateway'):
            gateway_key = assistant._answer_cache_key('en', 'simple', question, [1], set())
        with override_settings(AI_PROVIDER='claude_cli', AI_TEST_CLI_MODEL='claude-a-1'):
            first = assistant._answer_cache_key('en', 'simple', question, [1], set())
        with override_settings(AI_PROVIDER='claude_cli', AI_TEST_CLI_MODEL='claude-a-2'):
            second = assistant._answer_cache_key('en', 'simple', question, [1], set())
        self.assertEqual(len({gateway_key, first, second}), 3)

    def test_the_education_key_changes_with_the_model_that_really_answers(self):
        profile = mock.Mock(pk=3)
        with override_settings(AI_PROVIDER='claude_cli', AI_TEST_CLI_MODEL='claude-a-1'):
            first = education_ai._cache_key(profile, {'x': 1})
        with override_settings(AI_PROVIDER='claude_cli', AI_TEST_CLI_MODEL='claude-a-2'):
            second = education_ai._cache_key(profile, {'x': 1})
        with override_settings(AI_PROVIDER='gateway'):
            third = education_ai._cache_key(profile, {'x': 1})
        self.assertEqual(len({first, second, third}), 3)


class UsageAccountingTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='Usage School', code='usage-audit')
        self.user = User.objects.create_user(username='audit-student', email='a@example.com', role=User.Role.STUDENT,
                                             school=self.school)

    def test_a_repair_call_adds_to_the_first_calls_tokens(self):
        sink = ai_usage.begin()
        body = {'model': 'm', 'messages': [{'role': 'user', 'content': 'x' * 40}]}
        first = {'choices': [{'message': {'content': 'bad'}}],
                 'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110,
                           'prompt_tokens_details': {'cached_tokens': 5}}}
        second = {'choices': [{'message': {'content': '{}'}}],
                  'usage': {'prompt_tokens': 200, 'completion_tokens': 10, 'total_tokens': 210,
                            'prompt_tokens_details': {'cached_tokens': 7}}}
        ai_usage.capture(first, body, accumulate=True)
        ai_usage.capture(second, body, accumulate=True)
        ai_usage.record('telegram_import', None, provider='claude_cli', status=ai_usage.OK, sink=sink)
        row = AiUsageLog.objects.get()
        self.assertEqual((row.input_tokens, row.output_tokens, row.total_tokens, row.cached_input_tokens),
                         (300, 20, 320, 12))
        self.assertEqual(sink['answers'], 2)

    def test_without_accumulate_the_last_block_wins_as_before(self):
        sink = ai_usage.begin()
        ai_usage.capture({'choices': [{}], 'usage': {'total_tokens': 5, 'prompt_tokens': 3, 'completion_tokens': 2}})
        ai_usage.capture({'choices': [{}], 'usage': {'total_tokens': 9, 'prompt_tokens': 6, 'completion_tokens': 3}})
        self.assertEqual(sink['usage']['total_tokens'], 9)

    def test_the_log_fallback_counts_a_checks_units_not_its_provider_calls(self):
        from .views.admin_portal import _today_from_log

        for extra in (False, True):
            AiUsageLog.objects.create(user=self.user, school=self.school, feature='essay_coach', status='ok',
                                      provider='claude_cli', extra_attempt=extra)
        report = _today_from_log({self.school.pk: 'Usage School'})
        self.assertEqual(report['essay_coach']['used'], 1)

    def test_a_failed_step_without_an_answer_is_recorded_as_refunded(self):
        from .essay_lab import coach

        spec = mock.Mock(feature='essay_coach', log_id='x')
        with mock.patch.object(coach, '_request_gateway', side_effect=ai_providers.CliBusy('busy')):
            with self.assertRaises(coach.CoachUnavailable):
                coach._run_step(spec, self.user, [], 100, lambda raw: raw, time.monotonic() + 60, lambda: None,
                                extra_attempt=True)
        row = AiUsageLog.objects.get()
        self.assertTrue(row.refunded)
        self.assertTrue(row.extra_attempt)

    def test_a_failed_step_with_no_cli_cause_stays_a_paid_attempt(self):
        from .essay_lab import coach

        spec = mock.Mock(feature='essay_coach', log_id='x')
        with mock.patch.object(coach, '_request_gateway', side_effect=ValueError('bad shape')):
            with self.assertRaises(coach.CoachUnavailable):
                coach._run_step(spec, self.user, [], 100, lambda raw: raw, time.monotonic() + 60, lambda: None)
        self.assertFalse(AiUsageLog.objects.get().refunded)


class JobBudgetRefundTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(TELEGRAM_IMPORT_DAILY_BUDGET=5)
    def test_a_refund_undoes_the_backend_that_took_the_call(self):
        # Reserved while the cache was down: the process counter took it.
        with mock.patch.object(ai_budget, 'count_hits', return_value=None):
            reservation = ai_budget.consume_job('telegram_import')
        self.assertEqual(reservation.backend, 'process')
        # The cache is back (and has its own count) when the call fails.
        cache_counts = ai_budget.count_hits(['ai-budget:telegram_import:' + timezone.localdate().isoformat()], 100)
        self.assertEqual(cache_counts, [1])
        ai_budget.refund_job('telegram_import', reservation)
        self.assertFalse(ai_budget._fallback.counts.get('telegram_import:process'))
        key = 'ai-budget:telegram_import:' + timezone.localdate().isoformat()
        self.assertEqual(cache.get(key), 1, 'the cache counter was not touched')

    @override_settings(TELEGRAM_IMPORT_DAILY_BUDGET=5)
    def test_a_cache_reservation_is_undone_in_the_cache(self):
        reservation = ai_budget.consume_job('telegram_import')
        self.assertEqual(reservation.backend, 'cache')
        ai_budget.refund_job('telegram_import', reservation)
        key = 'ai-budget:telegram_import:' + timezone.localdate().isoformat()
        self.assertEqual(cache.get(key), 0)

    @override_settings(TELEGRAM_IMPORT_DAILY_BUDGET=1)
    def test_a_refused_call_is_false(self):
        self.assertTrue(ai_budget.consume_job('telegram_import'))
        self.assertFalse(ai_budget.consume_job('telegram_import'))


@override_settings(**{**AI_ON, **CLI_IMPORT, 'TELEGRAM_IMPORT_DAILY_BUDGET': 20})
class TelegramDeadlineTests(TestCase):
    def setUp(self):
        cache.clear()
        self.post = mock.Mock(posted_at='2026-11-20T10:00:00+00:00')

    def ask(self, answers, deadline, gate=None):
        calls = []

        def post(body, deadline=None):
            calls.append(body)
            return {'model': body['model'], 'choices': [{'message': {'content': answers[len(calls) - 1]}}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}

        with mock.patch.object(formatter, '_post', post):
            try:
                return formatter.format_post(self.post, 'text', ['https://example.org/x'], TODAY,
                                             deadline=deadline, retry_gate=gate), calls
            except Exception as exc:  # noqa: BLE001
                return exc, calls

    def test_the_repair_call_is_skipped_when_too_little_time_is_left(self):
        result, calls = self.ask(['no json at all', json.dumps(GOOD)], time.monotonic() + 5)
        self.assertIsInstance(result, formatter.OutOfTime)
        self.assertEqual((result.reason, len(calls)), ('time_budget', 1))

    def test_the_repair_call_runs_with_enough_time_and_the_budget_gate(self):
        gate = mock.Mock(return_value=True)
        result, calls = self.ask(['no json at all', json.dumps(GOOD)], time.monotonic() + 80, gate)
        self.assertTrue(result['is_program'])
        self.assertEqual(len(calls), 2)
        gate.assert_called_once()

    def test_a_refused_repair_budget_stops_without_a_second_call(self):
        result, calls = self.ask(['no json at all'], time.monotonic() + 80, lambda: False)
        self.assertEqual((result.reason, len(calls)), ('budget_exhausted', 1))

    def test_every_call_gets_the_runs_deadline_and_slot_wait_is_part_of_the_timeout(self):
        seen = {}

        def chat(body, timeout, **kwargs):
            seen.update(kwargs, timeout=timeout)
            return {'choices': [{'message': {'content': json.dumps(GOOD)}}], 'usage': {}}

        stop = time.monotonic() + 50
        with override_settings(TELEGRAM_IMPORT_CLI_SLOT_WAIT_SECONDS=3, TELEGRAM_IMPORT_TIMEOUT_SECONDS=30), \
                mock.patch.object(ai_providers, 'chat', chat):
            formatter._post({'messages': []}, stop)
        self.assertEqual((seen['deadline'], seen['timeout']), (stop, 33))

    def test_the_import_charges_each_repair_call_and_keeps_both_calls_tokens(self):
        answers = ['no json at all', json.dumps(GOOD)]
        calls = []

        def post(body, deadline=None):
            calls.append(body)
            return {'model': body['model'], 'choices': [{'message': {'content': answers[len(calls) - 1]}}],
                    'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}}

        run = importer.Run(today=TODAY, catalog=importer.rules.Catalog([]), deadline=time.monotonic() + 100,
                           hard_deadline=time.monotonic() + 140)
        with mock.patch.object(formatter, '_post', post):
            result = importer._format(run, self.post, 'text', ['https://example.org/x'], None)
        self.assertTrue(result['is_program'])
        self.assertEqual((len(calls), run.stats.ai_calls), (2, 2))
        key = 'ai-budget:telegram_import:' + timezone.localdate().isoformat()
        self.assertEqual(cache.get(key), 2, 'each provider call took one unit')
        row = AiUsageLog.objects.get(feature='telegram_import')
        self.assertEqual((row.status, row.total_tokens, row.input_tokens), ('ok', 220, 200))

    def test_running_out_of_time_for_the_repair_stops_the_run_and_keeps_the_paid_unit(self):
        calls = []

        def post(body, deadline=None):
            calls.append(body)
            return {'model': body['model'], 'choices': [{'message': {'content': 'no json'}}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}

        run = importer.Run(today=TODAY, catalog=importer.rules.Catalog([]), deadline=time.monotonic() + 100,
                           hard_deadline=time.monotonic() + 4)
        with mock.patch.object(formatter, '_post', post):
            with self.assertRaises(importer.StopRun) as caught:
                importer._format(run, self.post, 'text', ['https://example.org/x'], None)
        self.assertEqual(str(caught.exception), 'time_budget')
        self.assertEqual(len(calls), 1)
        key = 'ai-budget:telegram_import:' + timezone.localdate().isoformat()
        self.assertEqual(cache.get(key), 1, 'the first call was answered, so it stays counted')


class ImportStateTests(TestCase):
    """Backlog progress and outage reporting."""

    def test_a_backlog_cut_short_is_saved_and_resumed(self):
        pages = {
            None: self.page([(30, 'thirty'), (29, 'nine')], before=29),
            29: self.page([(28, 'eight'), (27, 'seven')], before=27),
            27: self.page([(26, 'six'), (25, 'five')], before=25),
        }
        calls = []

        def fetch_page(channel, before=None):
            calls.append(before)
            if len(calls) == 3:
                raise importer.StopRun('time_budget')  # out of time on the third page
            return pages[before]

        state = TelegramImportChannel.objects.create(channel='examplechannel', last_message_id=24)
        run = self.run_object(fetch_page)
        with self.assertRaises(importer.StopRun):
            importer.run_channel(run, 'examplechannel')
        state.refresh_from_db()
        self.assertEqual(state.backlog_before, 27)
        self.assertEqual([post['id'] for post in state.backlog_posts], [27, 28, 29, 30])
        self.assertEqual(state.last_message_id, 24, 'nothing was skipped')
        # The next run starts at the saved cursor, not at the newest page.
        calls.clear()
        run = self.run_object(lambda channel, before=None: (calls.append(before), pages[before])[1])
        with mock.patch.object(importer, 'handle_post', return_value='') as handled:
            importer.run_channel(run, 'examplechannel')
        self.assertEqual(calls, [27])
        self.assertEqual([call.args[1].id for call in handled.call_args_list], [25, 26, 27, 28, 29, 30])
        state.refresh_from_db()
        self.assertEqual((state.backlog_before, state.backlog_posts, state.last_message_id), (None, [], 30))

    def run_object(self, fetch_page):
        today = TODAY
        return importer.Run(today=today, catalog=importer.rules.Catalog([]), deadline=time.monotonic() + 100,
                            hard_deadline=time.monotonic() + 140, fetch=fetch_page)

    def page(self, posts, before):
        items = ''.join(
            f'<div class="tgme_widget_message" data-post="examplechannel/{pk}"><div class="tgme_widget_message_text js-message_text">{text}</div>'
            f'<time datetime="2026-11-20T10:00:00+00:00"></time></div>' for pk, text in posts)
        return f'<a class="js-messages_more" data-before="{before}"></a>{items}'

    def test_a_provider_outage_is_a_failed_job_not_an_ok_one(self):
        stats = importer.RunStats(stopped='gateway_unavailable')
        with mock.patch.object(importer, 'run', return_value=stats):
            with self.assertRaises(Exception):
                call_command('import_telegram_programs', stdout=StringIO())
        run = JobRun.objects.get(name='import_telegram_programs')
        self.assertEqual(run.result, 'failed')
        self.assertIn('gateway_unavailable', run.error)

    def test_every_channel_unreadable_is_a_failed_job(self):
        stats = importer.RunStats(failed_channels=['a', 'b'])
        with mock.patch.object(importer, 'run', return_value=stats):
            with self.assertRaises(Exception):
                call_command('import_telegram_programs', stdout=StringIO())
        self.assertIn('channels_unreadable', JobRun.objects.get().error)

    def test_expected_idle_stops_stay_ok(self):
        for stopped in ('outbound_ai_off', 'budget_off', 'budget_exhausted', 'time_budget'):
            JobRun.objects.all().delete()
            with mock.patch.object(importer, 'run', return_value=importer.RunStats(stopped=stopped)):
                call_command('import_telegram_programs', stdout=StringIO())
            self.assertEqual(JobRun.objects.get().result, 'ok', stopped)


class ImportNetworkBoundTests(SimpleTestCase):
    def test_a_trickling_telegram_page_is_cut_at_the_deadline(self):
        class Trickle:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, size=-1):
                time.sleep(0.3)
                return b'x'

        opener = mock.Mock()
        opener.open.return_value = Trickle()
        with mock.patch.object(fetch, 'build_opener', return_value=opener), \
                mock.patch.object(fetch, 'telegram_ssl_context'):
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                fetch.fetch_html('examplechannel', deadline=time.monotonic() + 1)
        self.assertLess(time.monotonic() - started, 5)

    def test_the_deadline_scope_reaches_fetch_html(self):
        with fetch.deadline_scope(time.monotonic() - 1):
            with self.assertRaises(TimeoutError):
                fetch.fetch_html('examplechannel')

    def test_a_dns_lookup_that_hangs_is_cut_off(self):
        def hang(*args, **kwargs):
            time.sleep(3)
            return []

        with mock.patch.object(official.socket, 'getaddrinfo', hang):
            started = time.monotonic()
            with self.assertRaises(official.PageUnavailable) as caught:
                official.public_addresses('example.org', timeout=0.3)
        self.assertEqual(str(caught.exception), 'slow')
        self.assertLess(time.monotonic() - started, 2)


class CacheSettingsTests(SimpleTestCase):
    def test_production_without_redis_gets_a_cache_the_workers_share(self):
        caches = build_cache_settings('', shared_file_dir='/tmp/x-shared')
        self.assertTrue(caches['default']['BACKEND'].endswith('FileBasedCache'))
        self.assertEqual(caches['default']['LOCATION'], '/tmp/x-shared')

    def test_redis_and_development_are_unchanged(self):
        self.assertTrue(build_cache_settings('redis://r:6379')['default']['BACKEND'].endswith('RedisCache'))
        self.assertTrue(build_cache_settings('')['default']['BACKEND'].endswith('LocMemCache'))

    def test_the_deploy_check_still_asks_for_redis(self):
        with override_settings(DEBUG=False, CACHES=build_cache_settings('', shared_file_dir='/tmp/x')):
            self.assertEqual([item.id for item in shared_cache_check(None)], ['naseeb.W001'])
        with override_settings(DEBUG=False, CACHES=build_cache_settings('redis://r:6379')):
            self.assertEqual(shared_cache_check(None), [])


class CliModelPinTests(SimpleTestCase):
    def test_production_on_the_cli_warns_about_a_moving_alias(self):
        with override_settings(APP_ENV='production', AI_PROVIDER='claude_cli', AI_TEST_CLI_MODEL='sonnet'):
            found = ai_cli_model_check(None)
        self.assertEqual([item.id for item in found], ['naseeb.W011'])
        self.assertIsInstance(found[0], checks.Warning)
        with override_settings(APP_ENV='production', AI_PROVIDER='claude_cli', AI_TEST_CLI_MODEL='claude-sonnet-4-5'):
            self.assertEqual(ai_cli_model_check(None), [])
        with override_settings(APP_ENV='production', AI_PROVIDER='gateway', TELEGRAM_IMPORT_AI_PROVIDER='',
                               AI_TEST_CLI_MODEL='sonnet'):
            self.assertEqual(ai_cli_model_check(None), [])


class CalibrationGateTests(SimpleTestCase):
    def test_calibration_follows_the_runtime_cli_policy(self):
        from django.core.management.base import CommandError

        with override_settings(APP_ENV='production', AI_CLI_ALLOW_PRODUCTION=False):
            with self.assertRaises(CommandError) as caught:
                call_command('coach_calibrate', '--provider', 'claude_cli', stdout=StringIO())
        self.assertIn('AI_CLI_ALLOW_PRODUCTION', str(caught.exception))
        with override_settings(APP_ENV='production', AI_CLI_ALLOW_PRODUCTION=True, OUTBOUND_AI_ENABLED=False):
            with self.assertRaises(CommandError) as caught:
                call_command('coach_calibrate', '--provider', 'claude_cli', stdout=StringIO())
        self.assertIn('No real gateway configured', str(caught.exception))


@override_settings(
    OUTBOUND_AI_ENABLED=True, COLLEGE_MATCH_REASONS_DAILY_BUDGET=100, COLLEGE_MATCH_REASONS_SCHOOL_DAILY_BUDGET=100,
    COLLEGE_MATCH_REASONS_USER_DAILY_LIMIT=5, EDUCATION_MATCH_DAILY_BUDGET=100, EDUCATION_MATCH_SCHOOL_DAILY_BUDGET=100,
    EDUCATION_MATCH_USER_DAILY_LIMIT=5, AI_PROVIDER='claude_cli', APP_ENV='test',
)
class PlanAndCandidateTests(MatchFixture, APITestCase):
    EDUCATION_URL = '/api/education-matches/ai/'

    def setUp(self):
        super().setUp()
        cache.clear()
        self.ready_profile(target_major='Computer Science, Economics')
        patcher = mock.patch(WHICH, return_value='/bin/claude')
        patcher.start()
        self.addCleanup(patcher.stop)

    def no_plan(self):
        return mock.patch('apps.users.entitlements.feature_enabled', return_value=False)

    def test_match_reasons_need_the_plans_ai_feature_before_any_budget_or_provider(self):
        with self.no_plan(), mock.patch.object(ai_providers, 'chat') as chat, \
                mock.patch.object(ai_budget, 'consume') as consume:
            response = self.client.post(REASONS_URL)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'feature_not_in_plan')
        chat.assert_not_called()
        consume.assert_not_called()

    def test_education_needs_the_plans_ai_feature_too(self):
        with self.no_plan(), mock.patch.object(ai_providers, 'chat') as chat:
            response = self.client.post(self.EDUCATION_URL, {}, format='json')
        self.assertEqual(response.status_code, 403)
        chat.assert_not_called()

    def test_education_uses_the_students_own_majors_not_the_requests(self):
        seen = {}

        def chat(body, timeout, **kwargs):
            seen['context'] = json.loads(body['messages'][1]['content'])
            answer = {'summary': 's', 'major_guidance': [
                {'major': 'Computer Science', 'why_fit': 'w', 'subjects_to_focus': [], 'explore_next': 'e'},
                {'major': 'Astrology', 'why_fit': 'w', 'subjects_to_focus': [], 'explore_next': 'e'},
            ], 'questions_to_consider': []}
            return {'choices': [{'message': {'content': 'Here you go: ' + json.dumps(answer)}}], 'usage': {}}

        with mock.patch.object(ai_providers, 'chat', side_effect=chat):
            response = self.client.post(
                self.EDUCATION_URL, {'major_candidates': ['Astrology', 'Computer Science']}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(seen['context']['candidate_majors'], ['computer science'])
        self.assertEqual([item['major'] for item in response.data['major_guidance']], ['computer science'])

    def test_education_without_a_stated_major_asks_for_one(self):
        self.ready_profile(target_major='')
        with mock.patch.object(ai_providers, 'chat') as chat:
            response = self.client.post(self.EDUCATION_URL, {'major_candidates': ['Astrology']}, format='json')
        self.assertEqual(response.status_code, 400)
        chat.assert_not_called()

    def test_a_cli_slot_failure_refunds_the_unit_and_marks_the_row(self):
        with mock.patch.object(ai_providers, 'chat', side_effect=ai_providers.CliBusy('busy')):
            response = self.client.post(REASONS_URL)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(5 - ai_budget.user_remaining(match_reasons.FEATURE, self.student_user), 0)
        row = AiUsageLog.objects.get(feature=match_reasons.FEATURE)
        self.assertTrue(row.refunded)

    def test_an_education_answer_the_cli_garbled_gives_the_allowance_back(self):
        payload = {'choices': [{'message': {'content': 'sorry, no json'}}], 'usage': {}}
        with mock.patch.object(ai_providers, 'chat', return_value=payload):
            response = self.client.post(self.EDUCATION_URL, {}, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(5 - ai_budget.user_remaining('education_match', self.student_user), 0)


@override_settings(OUTBOUND_AI_ENABLED=True, AI_PROVIDER='claude_cli', APP_ENV='test', AI_STREAM_SLOT_WAIT_SECONDS=0)
class AssistantCliFailureTests(Fixture, APITestCase):
    def setUp(self):
        self.make()
        self.client.force_authenticate(self.student_user)

    def test_every_cli_failure_gives_the_daily_unit_back_and_marks_the_row(self):
        for error in (ai_providers.CliBusy, ai_providers.CliTimeout, ai_providers.CliError, ai_providers.CliOutputError):
            AiUsageLog.objects.all().delete()
            body = {'messages': [{'role': 'user', 'content': 'Explain the SAT format'}]}
            with mock.patch.object(ai_providers, '_cli_binary', return_value='/bin/claude'), \
                    mock.patch.object(ai_providers, 'chat', side_effect=error('failed')):
                response = self.client.post(CHAT, body, format='json')
                b''.join(response.streaming_content)
            self.assertEqual(response['X-Assistant-Source'], 'local-fallback', error)
            self.assertEqual(used_today(), 0, error)
            row = AiUsageLog.objects.get(feature='assistant')
            self.assertEqual((row.status, row.refunded), ('provider_error', True), error)
