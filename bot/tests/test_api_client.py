import logging

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from bot.api import ApiClient, ApiError, ApiUnavailable
from bot.cache import TtlCache
from bot.config import ConfigError, load_config
from bot.main import RedactingFormatter


@pytest.fixture
async def backend():
    seen = []

    async def handler(request):
        body = await request.json() if request.can_read_body else None
        seen.append((request.method, request.path, dict(request.query), request.headers.get('X-Bot-Service-Key'), body))
        name = request.path.strip('/').split('/')[-1]
        if name == 'login':
            return web.json_response({'code': 'locked', 'detail': 'x', 'retry_after': 900}, status=429)
        if name == 'students':
            return web.json_response({'detail': 'Unauthorized.'}, status=401)
        if name == 'digest':
            return web.Response(text='oops', status=502)
        if name == 'confirm':
            return web.Response(text='<html>captive portal</html>', content_type='text/html')
        if name == 'logout':
            return web.json_response(['nope'], status=400)
        if name == 'due':
            return web.json_response({'chats': [{'chat_id': 5}]})
        if name == 'settings':
            return web.json_response({'language': 'uz'})
        return web.json_response({'ok': True})

    app = web.Application()
    app.router.add_route('*', '/api/bot/{name}/', handler)
    server = TestServer(app)
    await server.start_server()
    session = aiohttp.ClientSession()
    yield ApiClient(str(server.make_url('')).rstrip('/'), 'key-123', session), seen
    await session.close()
    await server.close()


async def test_sends_the_service_key_and_json(backend):
    api, seen = backend
    assert await api.due() == [{'chat_id': 5}]
    assert await api.get_settings(7) == {'language': 'uz'}
    assert seen[0][3] == 'key-123'
    assert seen[1][:3] == ('GET', '/api/bot/settings/', {'chat_id': '7'})


async def test_error_codes_and_extra_fields_are_mapped(backend):
    api, _ = backend
    with pytest.raises(ApiError) as caught:
        await api.login(1, 'u', 'p')
    assert (caught.value.status, caught.value.code, caught.value.extra) == (429, 'locked', {'retry_after': 900})
    with pytest.raises(ApiError) as caught:
        await api.students(1)
    assert (caught.value.status, caught.value.code) == (401, '')


async def test_server_errors_and_dead_backends_are_unavailable(backend):
    api, _ = backend
    with pytest.raises(ApiUnavailable):
        await api.digest(1)
    dead = ApiClient('http://127.0.0.1:1', 'k', api._session)
    with pytest.raises(ApiUnavailable) as caught:
        await dead.login(1, 'user', 'my-password-value')
    assert 'my-password-value' not in repr(caught.value) and caught.value.__cause__ is None


def test_ttl_cache_expires_and_drops_by_chat():
    now = {'t': 0.0}
    cache = TtlCache(5, clock=lambda: now['t'])
    cache.set(('digest', 1), 'a')
    cache.set(('students', 2), 'b')
    assert cache.get(('digest', 1)) == 'a'
    cache.drop_chat(1)
    assert cache.get(('digest', 1)) is None and cache.get(('students', 2)) == 'b'
    now['t'] = 5.1
    assert cache.get(('students', 2)) is None


def test_config_requires_all_three_variables(monkeypatch):
    for name in ('BOT_TOKEN', 'BACKEND_URL', 'BOT_SERVICE_KEY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr('bot.config.load_env_file', lambda path: None)
    with pytest.raises(ConfigError) as caught:
        load_config()
    assert 'BOT_TOKEN' in str(caught.value)
    monkeypatch.setenv('BOT_TOKEN', '123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')
    monkeypatch.setenv('BACKEND_URL', 'https://example.test/')
    monkeypatch.setenv('BOT_SERVICE_KEY', 'k')
    assert load_config().backend_url == 'https://example.test'


def test_log_lines_never_carry_the_token_or_the_key():
    formatter = RedactingFormatter(['svc-key-xyz'], '%(message)s')
    message = 'GET /bot123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/getMe key=svc-key-xyz'
    record = logging.LogRecord('x', logging.ERROR, __file__, 1, message, None, None)
    line = formatter.format(record)
    assert 'AAAA' not in line and 'svc-key-xyz' not in line


async def test_a_due_answer_without_a_chats_list_is_unavailable_not_a_crash(backend):
    api, _ = backend

    async def empty(*args, **kwargs):
        return {}

    api._call = empty
    with pytest.raises(ApiUnavailable):
        await api.due()


async def test_a_non_json_success_body_is_unavailable(backend):
    api, _ = backend
    with pytest.raises(ApiUnavailable):
        await api.confirm(1, 'token', 'en')


async def test_a_non_object_error_body_is_an_api_error_not_a_crash(backend):
    api, _ = backend
    with pytest.raises(ApiError) as caught:
        await api.logout(1)
    assert (caught.value.status, caught.value.code) == (400, '')
