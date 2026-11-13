import asyncio
import logging

import aiohttp

log = logging.getLogger('bot.api')
JOBS_TIMEOUT = 110
# Sending queued meeting emails: the backend stops starting new sends after ~25 s.
MAIL_TIMEOUT = 60


class ApiError(Exception):
    """The backend answered with an error. ``code`` is its machine-readable reason ('' when it gave none)."""

    def __init__(self, status, code='', **extra):
        super().__init__(f'{status} {code}'.strip())
        self.status = status
        self.code = code
        self.extra = extra


class ApiUnavailable(Exception):
    """Timeout, connection failure or a 5xx: worth retrying later."""


class ApiClient:
    def __init__(self, base_url, service_key, session):
        self._base = base_url
        self._headers = {'X-Bot-Service-Key': service_key}
        self._session = session

    async def _call(self, method, path, *, json=None, params=None, timeout=None):
        # `timeout` (seconds) overrides the session's for one slow call.
        extra = {'timeout': aiohttp.ClientTimeout(total=timeout)} if timeout else {}
        try:
            async with self._session.request(
                method, f'{self._base}/api/bot/{path}/', json=json, params=params, headers=self._headers, **extra,
            ) as response:
                try:
                    body = await response.json(content_type=None)
                except ValueError:
                    body = None
                status = response.status
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            # Only the exception type: the request body of a login holds a password.
            raise ApiUnavailable(type(exc).__name__) from None
        if status >= 500:
            raise ApiUnavailable(str(status))
        if not isinstance(body, dict):
            if status < 400:
                raise ApiUnavailable('bad_body')
            body = {}
        if status >= 400:
            if status == 401 and not (body or {}).get('code'):
                log.error('backend rejected the service key (check BOT_SERVICE_KEY)')
            extra = {k: v for k, v in (body or {}).items() if k not in ('code', 'detail')}
            raise ApiError(status, (body or {}).get('code', ''), **extra)
        return body

    async def login(self, chat_id, username, password, telegram_username=None):
        return await self._call('POST', 'login', json={
            'chat_id': chat_id, 'username': username, 'password': password, 'telegram_username': telegram_username,
        })

    async def whoami(self, chat_id, telegram_username=None):
        return await self._call('POST', 'whoami', json={'chat_id': chat_id, 'telegram_username': telegram_username})

    async def confirm(self, chat_id, pending_token, language):
        return await self._call('POST', 'confirm', json={
            'chat_id': chat_id, 'pending_token': pending_token, 'language': language,
        })

    async def students(self, chat_id):
        return await self._call('POST', 'students', json={'chat_id': chat_id})

    async def digest(self, chat_id):
        return await self._call('POST', 'digest', json={'chat_id': chat_id})

    async def add_student(self, chat_id, full_name, email, phone):
        return await self._call('POST', 'add-student', json={
            'chat_id': chat_id, 'full_name': full_name, 'email': email, 'phone': phone,
        })

    async def find_students(self, chat_id, query):
        return await self._call('POST', 'find-students', json={'chat_id': chat_id, 'query': query})

    async def reset_password(self, chat_id, student_id):
        return await self._call('POST', 'reset-password', json={'chat_id': chat_id, 'student_id': student_id})

    async def student_link(self, chat_id, token, language):
        return await self._call('POST', 'student-link', json={'chat_id': chat_id, 'token': token, 'language': language})

    async def student_outbox(self):
        body = await self._call('POST', 'student-outbox', json={})
        messages = body.get('messages') if isinstance(body, dict) else None
        if not isinstance(messages, list):
            raise ApiUnavailable('outbox answer has no messages list')
        return messages

    async def student_outbox_ack(self, sent, blocked):
        return await self._call('POST', 'student-outbox/ack', json={'sent': sent, 'blocked': blocked})

    async def get_settings(self, chat_id):
        return await self._call('GET', 'settings', params={'chat_id': chat_id})

    async def update_settings(self, chat_id, **changes):
        return await self._call('PUT', 'settings', json={'chat_id': chat_id, **changes})

    async def scheduled_jobs(self):
        # The backend answers when the due jobs are done; just under gunicorn's 120 s.
        return await self._call('POST', 'scheduled-jobs', json={}, timeout=JOBS_TIMEOUT)

    async def send_meeting_emails(self):
        # The backend sends what the website and the reminder job queued, for a bounded time.
        return await self._call('POST', 'meeting-emails', json={}, timeout=MAIL_TIMEOUT)

    async def due(self):
        body = await self._call('POST', 'due', json={})
        chats = body.get('chats') if isinstance(body, dict) else None
        if not isinstance(chats, list):
            raise ApiUnavailable('due answer has no chats list')
        return chats

    async def mark_sent(self, chat_id, slot_date):
        return await self._call('POST', 'mark-sent', json={'chat_id': chat_id, 'slot_date': slot_date})

    async def logout(self, chat_id):
        return await self._call('POST', 'logout', json={'chat_id': chat_id})

    async def unlink(self, chat_id):
        return await self._call('POST', 'unlink', json={'chat_id': chat_id})
