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
An interactive call waits only a few seconds for a slot (AI_CLI_SLOT_WAIT_SECONDS, never more than
MAX_INTERACTIVE_SLOT_WAIT) so web threads are not parked behind the queue; with no slot it fails like a
gateway timeout: the caller refunds the budget and tells the student to try again.

One absolute deadline covers a call: `timeout` is the total from the moment `chat` is called (or the
caller's own `deadline`, whichever is earlier), shared by the slot wait and the process, so a slot wait
never lengthens the call past what the browser waits for.

The CLI runs with MCP switched off (empty strict MCP config), built-in tools off, and an allowlisted
environment (no backend secrets), in its own process group that is killed on timeout or error.

Errors match the gateway path, so callers' failure, refund and usage handling is unchanged: a timeout is
TimeoutError, a non-zero exit, a CLI error result or a missing binary is OSError, unreadable output is
ValueError. The CLI ones are the subclasses CliTimeout / CliBusy / CliError / CliOutputError, which
`gateway_errors.is_unbilled` recognises (a CLI failure costs no per-call money, so the budget unit goes back).

The CLI cannot pin temperature or a token ceiling, and its reply is not strictly JSON-mode; a model name
from a calibration run is `claude-cli/<model>`, so a result checked here never counts for another model.
"""

import contextlib
import fcntl
import json
import os
import shutil
import signal
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
# An interactive call (a student waiting on a web thread) never waits longer than this for a CLI slot.
MAX_INTERACTIVE_SLOT_WAIT = 8
# Least time worth starting a CLI process for; below it the call fails as a timeout.
MIN_CLI_SECONDS = 1.0
# Environment variables the child may see: no backend secrets (database, gateway key, Django secret, ...).
CLI_ENV_ALLOWLIST = (
    'PATH', 'HOME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TMPDIR', 'TZ', 'USER', 'LOGNAME',
    'SSL_CERT_FILE', 'SSL_CERT_DIR', 'NODE_EXTRA_CA_CERTS',
    'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY', 'https_proxy', 'http_proxy', 'no_proxy',
    # How the CLI logs in: its config folder or a subscription token. ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN are
    # left out on purpose: they would switch the CLI to per-call API billing, and CLI failures are refunded as unbilled.
    'CLAUDE_CONFIG_DIR', 'CLAUDE_CODE_OAUTH_TOKEN',
)
EMPTY_MCP_CONFIG = '{"mcpServers":{}}'


class CliTimeout(TimeoutError):
    """The claude CLI ran out of its deadline."""


class CliBusy(TimeoutError):
    """No CLI slot freed up in time: no process ran."""


class CliError(OSError):
    """The claude CLI is missing, exited non-zero or reported an error."""


class CliOutputError(ValueError):
    """The claude CLI's output could not be read."""


def extract_json(text, required_keys=()):
    """The first non-empty JSON object in ``text`` (code fences and prose around it are ignored).

    One extractor for every feature: the CLI has no JSON mode, so a reply may come as "Here is the result:"
    plus a fenced object, or mention an empty `{}` first. With ``required_keys`` only an object holding all of
    them counts. Objects nested inside one already read are not candidates. ValueError when none fits.
    """
    text = str(text or '')
    decoder = json.JSONDecoder()
    wanted = tuple(required_keys)
    start = text.find('{')
    while start != -1:
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            value, end = None, start + 1
        if isinstance(value, dict) and value and all(key in value for key in wanted):
            return value
        start = text.find('{', end if isinstance(value, dict) else start + 1)
    raise ValueError('No JSON object in the reply.')


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


def chat(body, timeout, *, override='', slot_wait=None, reserve=0, deadline=None):
    """Send `body` through the active provider; returns the gateway-shaped payload.

    `override` picks the provider for one feature. A background feature passes `slot_wait` (seconds it
    may wait for a CLI slot, default AI_CLI_SLOT_WAIT_SECONDS) and `reserve` (CLI slots it must leave
    free, so it never takes the last one from a student's request). `deadline` is an absolute
    `time.monotonic()` value the call must finish by (the slot wait and the process both count).
    """
    if uses_cli(override):
        return _claude_cli(body, timeout, slot_wait=slot_wait, reserve=reserve, deadline=deadline)
    if deadline is not None:
        left = deadline - time.monotonic()
        if left <= 0:
            raise CliTimeout('The deadline passed before the call started.')
        timeout = min(timeout, left)
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
    """Hold one of AI_CLI_MAX_CONCURRENT machine-wide slots; CliBusy when none frees up in time.

    The slots are lock files: every gunicorn worker and thread on this machine competes for the same
    ones, and the operating system releases a lock when its process dies, so a crash never leaks a slot.
    """
    folder = os.path.join(tempfile.gettempdir(), 'naseeb-ai-cli-slots')
    os.makedirs(folder, exist_ok=True)
    total = max(1, settings.AI_CLI_MAX_CONCURRENT)
    # A caller with `reserve` takes a slot only while at least that many others stay free (so students are
    # never starved by background work); with too few slots for that it just waits briefly like everyone else.
    reserve = reserve if total - reserve >= 1 else 0
    wait = settings.AI_CLI_SLOT_WAIT_SECONDS if wait is None else wait
    deadline = time.monotonic() + max(0, wait)
    while True:
        for index in range(total):
            handle = _try_slot(folder, index)
            if handle is None:
                continue
            if reserve and _free_slots(folder, total, skip=index) < reserve:
                _drop_slot(handle)
                continue
            try:
                yield
            finally:
                _drop_slot(handle)
            return
        if time.monotonic() >= deadline:
            raise CliBusy('Every Claude CLI slot stayed busy; try again shortly.')
        time.sleep(min(SLOT_POLL_SECONDS, max(0.0, deadline - time.monotonic())))


def _try_slot(folder, index):
    handle = open(os.path.join(folder, f'slot-{index}.lock'), 'w')  # noqa: SIM115 - closed by _drop_slot
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _drop_slot(handle):
    fcntl.flock(handle, fcntl.LOCK_UN)
    handle.close()


def _free_slots(folder, total, skip):
    """How many slots other than ``skip`` are free right now (each is probed and released at once; best effort)."""
    free = 0
    for index in range(total):
        if index == skip:
            continue
        probe = _try_slot(folder, index)
        if probe is not None:
            _drop_slot(probe)
            free += 1
    return free


def _cli_environment():
    """The child's environment: only the allowlisted variables, never the backend's own secrets."""
    env = {name: os.environ[name] for name in CLI_ENV_ALLOWLIST if name in os.environ}
    if settings.AI_CLI_HOME:
        env['HOME'] = settings.AI_CLI_HOME  # where the Render disk install keeps its login
    # No update checks, telemetry or other background traffic: a call does one thing and exits.
    env['DISABLE_AUTOUPDATER'] = '1'
    env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
    return env


def _kill_group(process):
    """Kill the CLI and everything it started (it leads its own process group); never raises."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        pass


def _run_process(command, prompt, timeout):
    """(returncode, stdout, stderr). The CLI leads its own session so the whole group dies on a timeout,
    an error or the end of the call; CliTimeout when it outlives ``timeout``."""
    with tempfile.TemporaryDirectory() as workdir:  # own empty folder: no project memory file or repository
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=workdir, env=_cli_environment(), start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _kill_group(process)
            with contextlib.suppress(Exception):
                process.communicate(timeout=5)
            raise CliTimeout('The claude CLI timed out.') from exc
        except BaseException:
            _kill_group(process)
            with contextlib.suppress(Exception):
                process.communicate(timeout=5)
            raise
        finally:
            _kill_group(process)  # anything the CLI left running in its group
    return process.returncode, stdout, stderr


def cli_command(system=''):
    """The argv of one CLI call: pinned model, JSON envelope, no built-in tools, no MCP (empty strict config),
    no session, no settings files or slash commands."""
    command = [
        _cli_binary(), '-p', '--model', settings.AI_TEST_CLI_MODEL, '--output-format', 'json',
        '--tools', '', '--strict-mcp-config', '--mcp-config', EMPTY_MCP_CONFIG,
        '--no-session-persistence', '--setting-sources', '', '--disable-slash-commands',
    ]
    if system:
        command += ['--system-prompt', system]
    return command


def _claude_cli(body, timeout, slot_wait=None, reserve=0, deadline=None):
    started = time.monotonic()
    if not cli_allowed():
        raise RuntimeError(
            'AI_PROVIDER=claude_cli is only allowed when APP_ENV is development or test, '
            'or while AI_CLI_ALLOW_PRODUCTION is on.',
        )
    if not _cli_binary():
        raise CliError('The claude CLI was not found (AI_CLI_PATH or PATH).')
    limit = started + timeout if deadline is None else min(started + timeout, deadline)
    system, prompt = _split_messages(body.get('messages') or [])
    command = cli_command(system)
    if slot_wait is None:
        slot_wait = min(settings.AI_CLI_SLOT_WAIT_SECONDS, MAX_INTERACTIVE_SLOT_WAIT)
    with _cli_slot(max(0.0, min(slot_wait, limit - time.monotonic())), reserve):
        remaining = limit - time.monotonic()  # the slot wait came out of the same deadline
        if remaining < MIN_CLI_SECONDS:
            raise CliTimeout('The claude CLI had no time left after waiting for a slot.')
        returncode, stdout, stderr = _run_process(command, prompt, remaining)
    if returncode != 0:
        raise CliError(f'The claude CLI exited with {returncode}: {(stderr or stdout or "")[:300]}')
    return _cli_payload(stdout, body)


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _cli_payload(stdout, body):
    """Gateway-shaped payload from the CLI's JSON result. ValueError when it is not one."""
    try:
        result = json.loads(stdout)
    except ValueError as exc:
        raise CliOutputError('The claude CLI output was not JSON.') from exc
    if not isinstance(result, dict) or not isinstance(result.get('result'), str):
        raise CliOutputError('The claude CLI returned no result text.')
    if result.get('is_error'):
        raise CliError(f'The claude CLI reported an error: {result["result"][:300]}')
    used = result.get('usage') if isinstance(result.get('usage'), dict) else {}
    cached = _count(used.get('cache_read_input_tokens'))
    prompt_tokens = _count(used.get('input_tokens')) + _count(used.get('cache_creation_input_tokens')) + cached
    completion_tokens = _count(used.get('output_tokens'))
    models_used = result.get('modelUsage') if isinstance(result.get('modelUsage'), dict) else {}
    cost = result.get('total_cost_usd')
    return {
        'model': body.get('model') or active_model(''),
        # What the CLI itself reported, kept apart from the requested alias: the models that really ran and the
        # cost it computed (for a subscription it is only an estimate).
        'cli': {
            'models': sorted(str(name)[:120] for name in models_used)[:5],
            'total_cost_usd': cost if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
        },
        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': result['result']}}],
        'usage': {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': prompt_tokens + completion_tokens,
            'prompt_tokens_details': {'cached_tokens': cached},
        },
    }
