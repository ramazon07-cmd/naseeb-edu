"""The one place a Naseeb AI check reaches a model: the AI Gateway, or (local testing only) the Claude CLI.

`chat(body, timeout)` takes the gateway request body (`model`, `messages`, ...) and returns the payload
shape the gateway returns: `choices[0].message.content` plus a `usage` block. Callers keep their own
validation, usage capture and error handling, so a provider switch changes nothing for them.

- `gateway` (default): the HTTPS call to AI_GATEWAY_URL with AI_GATEWAY_API_KEY.
- `claude_cli`: runs `claude -p --model AI_TEST_CLI_MODEL --output-format json` so the owner can test with a
  Claude subscription instead of an API key. Allowed when APP_ENV is development or test, or in production
  only while AI_CLI_ALLOW_PRODUCTION is on (a temporary bridge until the API key is set): settings refuse
  to start otherwise (core/environment.py) and `chat` refuses again at call time.

Every CLI call takes one of AI_CLI_MAX_CONCURRENT slots shared by all gunicorn workers on the machine
(a file lock each), so a burst of students never starts more Claude processes than the memory can hold.
A call that finds no free slot within AI_CLI_SLOT_WAIT_SECONDS fails like a gateway timeout: the caller
refunds the budget and tells the student to try again.

Errors match the gateway path, so callers' failure, refund and usage handling is unchanged: a timeout is
TimeoutError, a non-zero exit, a CLI error result or a missing binary is OSError, unreadable output is
ValueError.

The CLI cannot pin temperature or a token ceiling, and its reply is not strictly JSON-mode; a model name
from a calibration run is `claude-cli/<model>`, so a result checked here never counts for another model.
"""

import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request

from django.conf import settings

GATEWAY = 'gateway'
CLAUDE_CLI = 'claude_cli'
PROVIDERS = (GATEWAY, CLAUDE_CLI)
CLI_ENVIRONMENTS = ('development', 'test')
CLI_BINARY = 'claude'


def provider(override=''):
    """The provider a call uses: `override` (a per-feature setting; blank follows AI_PROVIDER)."""
    override = (override or '').strip().lower()
    return override if override in PROVIDERS else settings.AI_PROVIDER


def uses_cli(override=''):
    return provider(override) == CLAUDE_CLI


def cli_allowed():
    return settings.APP_ENV in CLI_ENVIRONMENTS or settings.AI_CLI_ALLOW_PRODUCTION


def _cli_binary():
    """AI_CLI_PATH when it is an executable file (the Render disk install), else `claude` on PATH."""
    path = settings.AI_CLI_PATH
    if path:
        return path if os.path.isfile(path) and os.access(path, os.X_OK) else None
    return shutil.which(CLI_BINARY)


def cli_available():
    return _cli_binary() is not None


def active_model(gateway_model, override=''):
    """The model name a call carries: the gateway model, or `claude-cli/<model>` for the CLI."""
    return f'claude-cli/{settings.AI_TEST_CLI_MODEL}' if uses_cli(override) else gateway_model


def configured(override=''):
    """Whether a real provider can be called (not the outbound switch: callers check that themselves)."""
    if uses_cli(override):
        return cli_allowed() and cli_available()
    return bool(settings.AI_GATEWAY_API_KEY)


def chat(body, timeout, *, override='', slot_wait=None, reserve=0):
    """Send `body` through the active provider; returns the gateway-shaped payload.

    `override` picks the provider for one feature. A background feature passes `slot_wait` (seconds it
    may wait for a CLI slot, default AI_CLI_SLOT_WAIT_SECONDS) and `reserve` (CLI slots it must leave
    free, so it never takes the last one from a student's request).
    """
    if uses_cli(override):
        if slot_wait is None and not reserve:
            return _claude_cli(body, timeout)
        return _claude_cli(body, timeout, slot_wait=slot_wait, reserve=reserve)
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


SLOT_POLL_SECONDS = 0.25


@contextlib.contextmanager
def _cli_slot(wait=None, reserve=0):
    """Hold one of AI_CLI_MAX_CONCURRENT machine-wide slots; TimeoutError when none frees up in time.

    The slots are lock files: every gunicorn worker and thread on this machine competes for the same
    ones, and the operating system releases a lock when its process dies, so a crash never leaks a slot.
    """
    folder = os.path.join(tempfile.gettempdir(), 'naseeb-ai-cli-slots')
    os.makedirs(folder, exist_ok=True)
    total = max(1, settings.AI_CLI_MAX_CONCURRENT)
    # A caller that leaves `reserve` slots free only tries the first ones; with a single slot it just waits briefly.
    count = total - reserve if total - reserve >= 1 else total
    wait = settings.AI_CLI_SLOT_WAIT_SECONDS if wait is None else wait
    deadline = time.monotonic() + max(0, wait)
    while True:
        for index in range(count):
            handle = open(os.path.join(folder, f'slot-{index}.lock'), 'w')  # noqa: SIM115 - closed below
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                handle.close()
                continue
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()
            return
        if time.monotonic() >= deadline:
            raise TimeoutError('Every Claude CLI slot stayed busy; try again shortly.')
        time.sleep(SLOT_POLL_SECONDS)


def _cli_environment():
    env = dict(os.environ)
    if settings.AI_CLI_HOME:
        env['HOME'] = settings.AI_CLI_HOME  # where the Render disk install keeps its login
    # No update checks, telemetry or other background traffic: a call does one thing and exits.
    env['DISABLE_AUTOUPDATER'] = '1'
    env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
    return env


def _claude_cli(body, timeout, slot_wait=None, reserve=0):
    if not cli_allowed():
        raise RuntimeError(
            'AI_PROVIDER=claude_cli is only allowed when APP_ENV is development or test, '
            'or while AI_CLI_ALLOW_PRODUCTION is on.',
        )
    binary = _cli_binary()
    if not binary:
        raise OSError('The claude CLI was not found (AI_CLI_PATH or PATH).')
    system, prompt = _split_messages(body.get('messages') or [])
    command = [
        binary, '-p', '--model', settings.AI_TEST_CLI_MODEL, '--output-format', 'json',
        '--tools', '', '--no-session-persistence', '--setting-sources', '', '--disable-slash-commands',
    ]
    if system:
        command += ['--system-prompt', system]
    with _cli_slot(slot_wait, reserve):
        try:
            # Own empty working folder: no project memory file or repository is picked up.
            with tempfile.TemporaryDirectory() as workdir:
                done = subprocess.run(
                    command, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=workdir,
                    env=_cli_environment(), check=False,
                )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError('The claude CLI timed out.') from exc
    if done.returncode != 0:
        raise OSError(f'The claude CLI exited with {done.returncode}: {(done.stderr or done.stdout or "")[:300]}')
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
