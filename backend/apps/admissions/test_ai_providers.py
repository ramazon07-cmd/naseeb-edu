"""The provider switch: gateway by default, the Claude CLI for local testing only. The real CLI is never run."""

import json
import subprocess
from unittest import mock

from django.core import checks
from django.test import SimpleTestCase, override_settings

from core.checks import ai_provider_check
from core.environment import validate_runtime_environment

from . import ai_providers, rec_letter_ai
from .essay_lab import coach

CLI = dict(AI_PROVIDER='claude_cli', AI_TEST_CLI_MODEL='sonnet', APP_ENV='development')
RUN = 'apps.admissions.ai_providers.subprocess.run'
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
    return subprocess.CompletedProcess(['claude'], returncode, stdout, stderr)


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
        kwargs = runner.call_args.kwargs
        self.assertEqual(kwargs['input'], 'The essay text.')
        self.assertEqual(kwargs['timeout'], 12)
        self.assertFalse(kwargs.get('shell', False))
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
        error, _ = self.call(side_effect=subprocess.TimeoutExpired('claude', 12))
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
