"""The one place a Naseeb AI check reaches a model: the AI Gateway, or (local testing only) the Claude CLI.

`chat(body, timeout)` takes the gateway request body (`model`, `messages`, ...) and returns the payload
shape the gateway returns: `choices[0].message.content` plus a `usage` block. Callers keep their own
validation, usage capture and error handling, so a provider switch changes nothing for them.

- `gateway` (default): the HTTPS call to AI_GATEWAY_URL with AI_GATEWAY_API_KEY.
- `claude_cli`: runs `claude -p --model AI_TEST_CLI_MODEL --output-format json` so the owner can test with a
  Claude subscription instead of an API key. Allowed ONLY when APP_ENV is development or test: settings
  refuse to start otherwise (core/environment.py) and `chat` refuses again at call time.

Errors match the gateway path, so callers' failure, refund and usage handling is unchanged: a timeout is
TimeoutError, a non-zero exit, a CLI error result or a missing binary is OSError, unreadable output is
ValueError.

The CLI cannot pin temperature or a token ceiling, and its reply is not strictly JSON-mode; a model name
from a calibration run is `claude-cli/<model>`, so a result checked here never counts for another model.
"""

import json
import shutil
import subprocess
import tempfile
import urllib.request

from django.conf import settings

GATEWAY = 'gateway'
CLAUDE_CLI = 'claude_cli'
PROVIDERS = (GATEWAY, CLAUDE_CLI)
CLI_ENVIRONMENTS = ('development', 'test')
CLI_BINARY = 'claude'


def provider():
    return settings.AI_PROVIDER


def uses_cli():
    return provider() == CLAUDE_CLI


def cli_available():
    return shutil.which(CLI_BINARY) is not None


def active_model(gateway_model):
    """The model name a call carries: the gateway model, or `claude-cli/<model>` for the CLI."""
    return f'claude-cli/{settings.AI_TEST_CLI_MODEL}' if uses_cli() else gateway_model


def configured():
    """Whether a real provider can be called (not the outbound switch: callers check that themselves)."""
    if uses_cli():
        return settings.APP_ENV in CLI_ENVIRONMENTS and cli_available()
    return bool(settings.AI_GATEWAY_API_KEY)


def chat(body, timeout):
    """Send `body` through the active provider; returns the gateway-shaped payload."""
    if uses_cli():
        return _claude_cli(body, timeout)
    return _gateway(body, timeout)


def _gateway(body, timeout):
    request = urllib.request.Request(
        settings.AI_GATEWAY_URL,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {settings.AI_GATEWAY_API_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Vercel-AI-App-Name': 'Naseeb Edu',
        },
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def _split_messages(messages):
    """(system text, prompt text): system messages go to --system-prompt, the rest to stdin."""
    system = '\n\n'.join(str(m.get('content', '')) for m in messages if m.get('role') == 'system')
    rest = [m for m in messages if m.get('role') != 'system']
    if len(rest) == 1:
        return system, str(rest[0].get('content', ''))
    return system, '\n\n'.join(f"[{m.get('role', 'user')}]\n{m.get('content', '')}" for m in rest)


def _claude_cli(body, timeout):
    if settings.APP_ENV not in CLI_ENVIRONMENTS:
        raise RuntimeError('AI_PROVIDER=claude_cli is only allowed when APP_ENV is development or test.')
    binary = shutil.which(CLI_BINARY)
    if not binary:
        raise OSError('The claude CLI was not found on PATH.')
    system, prompt = _split_messages(body.get('messages') or [])
    command = [
        binary, '-p', '--model', settings.AI_TEST_CLI_MODEL, '--output-format', 'json',
        '--tools', '', '--no-session-persistence', '--setting-sources', '', '--disable-slash-commands',
    ]
    if system:
        command += ['--system-prompt', system]
    try:
        # Own empty working folder: no project memory file or repository is picked up.
        with tempfile.TemporaryDirectory() as workdir:
            done = subprocess.run(
                command, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=workdir, check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError('The claude CLI timed out.') from exc
    if done.returncode != 0:
        raise OSError(f'The claude CLI exited with {done.returncode}: {(done.stderr or "")[:300]}')
    return _cli_payload(done.stdout, body)


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _cli_payload(stdout, body):
    """Gateway-shaped payload from the CLI's JSON result. ValueError when it is not one."""
    result = json.loads(stdout)  # JSONDecodeError is a ValueError
    if not isinstance(result, dict) or not isinstance(result.get('result'), str):
        raise ValueError('The claude CLI returned no result text.')
    if result.get('is_error'):
        raise OSError(f'The claude CLI reported an error: {result["result"][:300]}')
    used = result.get('usage') if isinstance(result.get('usage'), dict) else {}
    cached = _count(used.get('cache_read_input_tokens'))
    prompt_tokens = _count(used.get('input_tokens')) + _count(used.get('cache_creation_input_tokens')) + cached
    completion_tokens = _count(used.get('output_tokens'))
    return {
        'model': body.get('model') or active_model(''),
        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': result['result']}}],
        'usage': {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': prompt_tokens + completion_tokens,
            'prompt_tokens_details': {'cached_tokens': cached},
        },
    }
