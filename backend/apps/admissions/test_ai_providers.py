"""The provider switch: gateway by default, the Claude CLI for local testing only. The real CLI is never run."""

import json
from unittest import mock

from django.core import checks
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from core.checks import ai_provider_check
from core.environment import validate_runtime_environment

from . import ai_providers, rec_letter_ai
from .essay_lab import coach

CLI = dict(AI_PROVIDER='claude_cli', AI_TEST_CLI_MODEL='sonnet', APP_ENV='development')
RUN = 'apps.admissions.ai_providers._run_process'
WHICH = 'apps.admissions.ai_providers.shutil.which'
BODY = {
    'model': 'openai/gpt-5.4-mini',
    'messages': [{'role': 'system', 'content': 'Answer in JSON.'}, {'role': 'user', 'content': 'The essay text.'}],
}


def cli_output(text='{"ok": true}', **changes):
    data = {
        'type': 'result', 'subtype': 'success', 'is_error': False, 'result': text,
        'usage': {'input_tokens': 2, 'cache_creation_input_tokens': 700, 'cache_read_input_tokens': 80,
                  'output_tokens': 9},
    }
    data.update(changes)
    return json.dumps(data)


def completed(stdout='', returncode=0, stderr=''):
    """What `_run_process` returns: (returncode, stdout, stderr)."""
    return (returncode, stdout, stderr)


@override_settings(**CLI)
class ClaudeCliProviderTests(SimpleTestCase):
    def call(self, **run):
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN, **run) as runner:
            try:
                return ai_providers.chat(BODY, 12), runner
            except Exception as exc:  # the tests assert on the type
                return exc, runner

    def test_command_is_an_argument_list_with_the_prompt_on_stdin(self):
        payload, runner = self.call(return_value=completed(cli_output()))
        command = runner.call_args.args[0]
        self.assertIsInstance(command, list)
        self.assertEqual(command[:2], ['/bin/claude', '-p'])
        self.assertEqual(command[command.index('--model') + 1], 'sonnet')
        self.assertEqual(command[command.index('--output-format') + 1], 'json')
        self.assertEqual(command[command.index('--system-prompt') + 1], 'Answer in JSON.')
        self.assertEqual(command[command.index('--tools') + 1], '')
        self.assertNotIn('The essay text.', command)
        self.assertEqual(runner.call_args.args[1], 'The essay text.')
        self.assertLessEqual(runner.call_args.args[2], 12)  # the slot wait came out of the same 12 s
        self.assertGreater(runner.call_args.args[2], 10)
        self.assertIsInstance(payload, dict)

    def test_payload_has_the_gateway_shape(self):
        payload, _ = self.call(return_value=completed(cli_output('{"a": 1}')))
        self.assertEqual(payload['choices'][0]['message']['content'], '{"a": 1}')
        self.assertEqual(payload['usage']['prompt_tokens'], 782)
        self.assertEqual(payload['usage']['completion_tokens'], 9)
        self.assertEqual(payload['usage']['total_tokens'], 791)
        self.assertEqual(payload['usage']['prompt_tokens_details']['cached_tokens'], 80)
        self.assertEqual(payload['model'], BODY['model'])

    def test_several_user_messages_become_a_labelled_transcript(self):
        system, prompt = ai_providers._split_messages([
            {'role': 'system', 'content': 'S'}, {'role': 'user', 'content': 'A'}, {'role': 'assistant', 'content': 'B'},
        ])
        self.assertEqual((system, prompt), ('S', '[user]\nA\n\n[assistant]\nB'))

    def test_a_timeout_is_a_timeout_error(self):
        error, _ = self.call(side_effect=ai_providers.CliTimeout('The claude CLI timed out.'))
        self.assertIsInstance(error, TimeoutError)

    def test_a_non_zero_exit_is_an_os_error(self):
        error, _ = self.call(return_value=completed('', returncode=1, stderr='boom'))
        self.assertIsInstance(error, OSError)
        self.assertIn('boom', str(error))

    def test_an_error_result_is_an_os_error(self):
        error, _ = self.call(return_value=completed(cli_output('Credit balance too low', is_error=True)))
        self.assertIsInstance(error, OSError)

    def test_bad_json_is_a_value_error(self):
        for stdout in ('not json', '[]', json.dumps({'type': 'result'}), json.dumps({'result': 5})):
            error, _ = self.call(return_value=completed(stdout))
            self.assertIsInstance(error, ValueError, stdout)

    def test_a_missing_binary_is_an_os_error(self):
        with mock.patch(WHICH, return_value=None), mock.patch(RUN) as runner:
            with self.assertRaises(OSError):
                ai_providers.chat(BODY, 5)
        runner.assert_not_called()

    def test_callers_map_the_errors_to_the_same_failures(self):
        errors = (TimeoutError, OSError, ValueError)
        self.assertTrue(all(issubclass(error, coach._PROVIDER_ERRORS) for error in errors))

    def test_the_coach_reads_the_cli_answer_like_a_gateway_answer(self):
        with mock.patch(WHICH, return_value='/bin/claude'), \
                mock.patch(RUN, return_value=completed(cli_output('```json\n{"x": 2}\n```'))) as runner:
            self.assertEqual(coach._request_gateway(BODY['messages'], 500, coach.time.monotonic() + 60), {'x': 2})
        self.assertEqual(runner.call_args.args[0][runner.call_args.args[0].index('--model') + 1], 'sonnet')

    def test_the_cli_model_is_part_of_the_cache_key_model(self):
        with override_settings(OUTBOUND_AI_ENABLED=True), mock.patch(WHICH, return_value='/bin/claude'):
            self.assertEqual(coach.current_model(), 'claude-cli/sonnet')


class ProviderSwitchTests(SimpleTestCase):
    def test_the_default_is_the_gateway(self):
        self.assertEqual(ai_providers.GATEWAY, 'gateway')
        self.assertEqual(ai_providers.provider(), 'gateway')

    @override_settings(AI_PROVIDER='gateway')
    def test_the_gateway_path_makes_the_urllib_call(self):
        reply = mock.MagicMock()
        reply.__enter__.return_value.read.return_value = json.dumps({'choices': []}).encode()
        with mock.patch('urllib.request.urlopen', return_value=reply) as urlopen, mock.patch(RUN) as runner:
            self.assertEqual(ai_providers.chat(BODY, 7), {'choices': []})
        self.assertEqual(urlopen.call_args.kwargs['timeout'], 7)
        runner.assert_not_called()

    @override_settings(AI_PROVIDER='gateway', AI_GATEWAY_API_KEY='')
    def test_gateway_needs_its_key(self):
        self.assertFalse(coach.gateway_configured())
        self.assertFalse(rec_letter_ai.gateway_configured())

    @override_settings(OUTBOUND_AI_ENABLED=True, **CLI)
    def test_the_cli_counts_as_configured_only_when_the_binary_is_found(self):
        with mock.patch(WHICH, return_value='/bin/claude'):
            self.assertTrue(coach.gateway_configured())
            self.assertTrue(rec_letter_ai.gateway_configured())
        with mock.patch(WHICH, return_value=None):
            self.assertFalse(coach.gateway_configured())
            self.assertFalse(rec_letter_ai.gateway_configured())

    @override_settings(OUTBOUND_AI_ENABLED=False, **CLI)
    def test_the_outbound_switch_still_wins(self):
        with mock.patch(WHICH, return_value='/bin/claude'):
            self.assertFalse(coach.gateway_configured())


class ProductionRefusalTests(SimpleTestCase):
    def errors(self, provider, app_env):
        return validate_runtime_environment(
            app_env=app_env, debug=app_env != 'production', secret_key='k' * 50,
            database_url='postgresql://u:p@db/x' if app_env == 'production' else '',
            demo_accounts_enabled=False, ai_provider=provider,
        )

    def test_startup_refuses_the_cli_in_production(self):
        self.assertTrue(any('claude_cli' in error for error in self.errors('claude_cli', 'production')))

    def test_startup_allows_the_cli_in_development_and_test(self):
        for env in ('development', 'test'):
            self.assertEqual(self.errors('claude_cli', env), [], env)

    def test_production_with_the_gateway_is_still_accepted(self):
        self.assertEqual(self.errors('gateway', 'production'), [])

    def test_an_unknown_provider_is_refused(self):
        self.assertTrue(any('AI_PROVIDER' in error for error in self.errors('openai', 'development')))

    @override_settings(AI_PROVIDER='claude_cli', APP_ENV='production')
    def test_the_system_check_is_an_error_in_production(self):
        found = ai_provider_check(None)
        self.assertEqual([item.id for item in found], ['naseeb.E001'])
        self.assertIsInstance(found[0], checks.Error)

    @override_settings(**CLI)
    def test_the_system_check_is_quiet_in_development(self):
        self.assertEqual(ai_provider_check(None), [])

    @override_settings(AI_PROVIDER='claude_cli', APP_ENV='production', OUTBOUND_AI_ENABLED=True)
    def test_the_call_itself_refuses_in_production(self):
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN) as runner:
            self.assertFalse(ai_providers.configured())
            with self.assertRaises(RuntimeError):
                ai_providers.chat(BODY, 5)
        runner.assert_not_called()


PROD_BRIDGE = dict(AI_PROVIDER='claude_cli', APP_ENV='production', AI_CLI_ALLOW_PRODUCTION=True, OUTBOUND_AI_ENABLED=True)


class ProductionBridgeTests(SimpleTestCase):
    """AI_CLI_ALLOW_PRODUCTION: a temporary, explicit way to run the CLI in production until the API key is set."""

    def test_startup_accepts_the_cli_in_production_only_with_the_switch(self):
        common = dict(app_env='production', debug=False, secret_key='k' * 50, database_url='postgresql://u:p@db/x',
                      demo_accounts_enabled=False, ai_provider='claude_cli')
        self.assertEqual(validate_runtime_environment(**common, ai_cli_allow_production=True), [])
        self.assertTrue(validate_runtime_environment(**common))

    def test_startup_checks_the_telegram_import_provider_the_same_way(self):
        common = dict(app_env='production', debug=False, secret_key='k' * 50, database_url='postgresql://u:p@db/x',
                      demo_accounts_enabled=False)
        self.assertTrue(validate_runtime_environment(**common, telegram_import_ai_provider='claude_cli'))
        self.assertEqual(
            validate_runtime_environment(**common, telegram_import_ai_provider='claude_cli', ai_cli_allow_production=True), [])
        self.assertEqual(validate_runtime_environment(**common, telegram_import_ai_provider=''), [])
        self.assertTrue(validate_runtime_environment(**common, telegram_import_ai_provider='openai'))

    @override_settings(**PROD_BRIDGE)
    def test_the_system_check_warns_instead_of_failing(self):
        found = ai_provider_check(None)
        self.assertEqual([item.id for item in found], ['naseeb.W010'])
        self.assertIsInstance(found[0], checks.Warning)

    @override_settings(**PROD_BRIDGE, AI_CLI_PATH='/var/data/claude/.local/bin/claude', AI_CLI_HOME='/var/data/claude')
    def test_the_disk_install_and_its_home_are_used(self):
        with mock.patch('apps.admissions.ai_providers.os.path.isfile', return_value=True), \
                mock.patch('apps.admissions.ai_providers.os.access', return_value=True), \
                mock.patch(RUN, return_value=completed(cli_output())) as runner:
            self.assertTrue(ai_providers.configured())
            ai_providers.chat(BODY, 5)
        self.assertEqual(runner.call_args.args[0][0], '/var/data/claude/.local/bin/claude')
        env = ai_providers._cli_environment()
        self.assertEqual(env['HOME'], '/var/data/claude')
        self.assertEqual(env['DISABLE_AUTOUPDATER'], '1')

    @override_settings(**PROD_BRIDGE, AI_CLI_PATH='/nowhere/claude')
    def test_a_missing_disk_install_is_not_configured(self):
        self.assertFalse(ai_providers.configured())


@override_settings(**CLI, AI_CLI_SLOT_WAIT_SECONDS=0)
class CliSlotTests(SimpleTestCase):
    """At most AI_CLI_MAX_CONCURRENT Claude processes at once; the rest wait, then fail like a timeout."""

    def hold_slot(self):
        import threading
        held, release = threading.Event(), threading.Event()

        def holder():
            with ai_providers._cli_slot():
                held.set()
                release.wait(5)
        thread = threading.Thread(target=holder)
        thread.start()
        self.assertTrue(held.wait(5))
        self.addCleanup(thread.join, 5)
        self.addCleanup(release.set)
        return release

    @override_settings(AI_CLI_MAX_CONCURRENT=1)
    def test_a_second_call_waits_and_then_fails_without_starting_a_process(self):
        self.hold_slot()
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN) as runner:
            with self.assertRaises(TimeoutError):
                ai_providers.chat(BODY, 5)
        runner.assert_not_called()

    @override_settings(AI_CLI_MAX_CONCURRENT=2)
    def test_two_slots_let_two_calls_run(self):
        self.hold_slot()
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN, return_value=completed(cli_output())):
            self.assertIn('choices', ai_providers.chat(BODY, 5))

    @override_settings(AI_CLI_MAX_CONCURRENT=1, AI_CLI_SLOT_WAIT_SECONDS=3)
    def test_a_waiting_call_runs_once_the_slot_frees(self):
        import threading
        release = self.hold_slot()
        threading.Timer(0.3, release.set).start()
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN, return_value=completed(cli_output())):
            self.assertIn('choices', ai_providers.chat(BODY, 5))

    @override_settings(AI_CLI_MAX_CONCURRENT=2)
    def test_a_background_call_leaves_the_last_slot_to_students(self):
        self.hold_slot()  # one of the two is taken: a background call that reserves one must not take the other
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN) as runner:
            with self.assertRaises(TimeoutError):
                ai_providers.chat(BODY, 5, slot_wait=0, reserve=1)
        runner.assert_not_called()

    @override_settings(AI_CLI_MAX_CONCURRENT=1)
    def test_a_background_call_gives_up_after_its_own_short_wait(self):
        import time
        self.hold_slot()
        started = time.monotonic()
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN):
            with self.assertRaises(TimeoutError):
                ai_providers.chat(BODY, 5, slot_wait=0.3, reserve=1)
        self.assertLess(time.monotonic() - started, 3)

    @override_settings(AI_PROVIDER='gateway', **{k: v for k, v in CLI.items() if k != 'AI_PROVIDER'})
    def test_a_feature_can_choose_the_cli_while_the_app_uses_the_gateway(self):
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN, return_value=completed(cli_output())):
            self.assertIn('choices', ai_providers.chat(BODY, 5, override='claude_cli'))
        self.assertFalse(ai_providers.uses_cli())
        self.assertTrue(ai_providers.uses_cli('claude_cli'))
        self.assertEqual(ai_providers.active_model('m', 'claude_cli'), 'claude-cli/' + settings.AI_TEST_CLI_MODEL)

    @override_settings(AI_CLI_MAX_CONCURRENT=1)
    def test_a_failed_call_gives_its_slot_back(self):
        with mock.patch(WHICH, return_value='/bin/claude'), \
                mock.patch(RUN, side_effect=ai_providers.CliTimeout('timed out')):
            with self.assertRaises(TimeoutError):
                ai_providers.chat(BODY, 5)
        with mock.patch(WHICH, return_value='/bin/claude'), mock.patch(RUN, return_value=completed(cli_output())):
            self.assertIn('choices', ai_providers.chat(BODY, 5))


@override_settings(**CLI, OUTBOUND_AI_ENABLED=True, AI_GATEWAY_API_KEY='')
class AssistantCliTests(SimpleTestCase):
    def test_the_assistant_counts_the_cli_as_ready_without_a_gateway_key(self):
        from . import assistant
        with mock.patch(WHICH, return_value='/bin/claude'):
            self.assertTrue(assistant._provider_ready())
        with mock.patch(WHICH, return_value=None):
            self.assertFalse(assistant._provider_ready())

    def test_the_assistant_reply_comes_back_as_one_chunk(self):
        from . import assistant
        payload = ai_providers._cli_payload(cli_output('Start with your Common App essay.'), {'model': 'claude-cli/sonnet'})
        with mock.patch.object(ai_providers, 'chat', return_value=payload) as chat:
            chunks = list(assistant._gateway_stream([{'role': 'user', 'content': 'What next?'}], 'Be brief.'))
        self.assertEqual(chunks, ['Start with your Common App essay.'])
        sent = chat.call_args.args[0]
        self.assertEqual(sent['messages'][0], {'role': 'system', 'content': 'Be brief.'})
        self.assertNotIn('stream', sent)


class EducationAiCliTests(SimpleTestCase):
    def test_major_explanations_run_through_the_cli_without_a_gateway_key(self):
        from . import education_ai
        payload = ai_providers._cli_payload(cli_output('{"summary": "ok"}'), {'model': 'claude-cli/sonnet'})
        with override_settings(AI_PROVIDER='claude_cli', AI_GATEWAY_API_KEY='', OUTBOUND_AI_ENABLED=True), \
                mock.patch(WHICH, return_value='/bin/claude'), \
                mock.patch.object(ai_providers, 'chat', return_value=payload) as chat:
            self.assertTrue(education_ai.recommendation_ai_available())
            raw, body = education_ai._call_gateway({'majors': []})
        self.assertEqual(education_ai._parse_gateway(raw, body), {'summary': 'ok'})
        self.assertTrue(chat.call_args.args[0]['model'].startswith('claude-cli/'))

    def test_a_cli_failure_is_an_unbilled_gateway_failure(self):
        from . import education_ai
        with override_settings(AI_PROVIDER='claude_cli'), mock.patch(WHICH, return_value='/bin/claude'), \
                mock.patch.object(ai_providers, 'chat', side_effect=TimeoutError('busy')):
            with self.assertRaises(education_ai.GatewayFailure) as caught:
                education_ai._call_gateway({'majors': []})
        self.assertTrue(caught.exception.unbilled)


@override_settings(**CLI, AI_CLI_SLOT_WAIT_SECONDS=0, AI_CLI_MAX_CONCURRENT=3)
class CliSlotReserveTests(SimpleTestCase):
    """A caller with reserve=N only takes a slot while N others stay free, whichever slots the others hold."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch('apps.admissions.ai_providers.tempfile.gettempdir', return_value=folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.folder = f'{folder.name}/naseeb-ai-cli-slots'

    def hold(self, *indexes):
        import fcntl
        import os
        os.makedirs(self.folder, exist_ok=True)
        for index in indexes:
            handle = open(f'{self.folder}/slot-{index}.lock', 'w')
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.addCleanup(handle.close)

    def take(self, reserve):
        with ai_providers._cli_slot(reserve=reserve):
            return True

    def test_no_reserve_takes_any_free_slot(self):
        self.hold(0, 1)
        self.assertTrue(self.take(0))

    def test_reserve_refuses_when_students_hold_the_low_slots(self):
        # Slots 0 and 1 are busy: slot 2 is the only free one, and it is the one reserved.
        self.hold(0, 1)
        with self.assertRaises(TimeoutError):
            self.take(1)

    def test_reserve_refuses_when_students_hold_the_high_slots(self):
        self.hold(1, 2)
        with self.assertRaises(TimeoutError):
            self.take(1)

    def test_reserve_takes_a_slot_when_another_stays_free(self):
        self.hold(2)
        self.assertTrue(self.take(1))

    def test_a_reserving_call_releases_its_slot_and_probes(self):
        self.hold(2)
        self.take(1)
        self.hold(0)
        # Slots 0 and 2 are held now; nothing from the earlier call is still locked, so slot 1 is free
        # but it is the last one, which a reserve=1 caller must leave alone.
        with self.assertRaises(TimeoutError):
            self.take(1)
        self.assertTrue(self.take(0))

    @override_settings(AI_CLI_MAX_CONCURRENT=1)
    def test_a_single_slot_ignores_the_reserve(self):
        self.assertTrue(self.take(1))
