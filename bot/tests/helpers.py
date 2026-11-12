from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    AnswerCallbackQuery, DeleteMessage, EditMessageReplyMarkup, EditMessageText, GetMe, SendChatAction, SendMessage, SetMyCommands,
)
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot.api import ApiError
from bot.cache import TtlCache
from bot.handlers import router

TOKEN = '123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
SECRET_PASSWORD = 'S3cret-Passw0rd!'


class MockedSession(BaseSession):
    """Records every Telegram call (in one shared event list with the fake API); never touches the network."""

    def __init__(self, events):
        super().__init__()
        self.events = events
        self.calls = []
        self.failures = {}
        self._ids = 1000

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        yield b''

    def of(self, kind):
        return [call for call in self.calls if call[0] == kind]

    def texts(self):
        return [call[1].get('text') for call in self.calls if call[0] in ('SendMessage', 'EditMessageText')]

    async def make_request(self, bot, method, timeout=None):
        kind = type(method).__name__
        data = method.model_dump()
        self.calls.append((kind, data))
        self.events.append(('tg', kind, data))
        queue = self.failures.get(kind)
        if queue:
            raise queue.pop(0)
        if isinstance(method, (SendMessage, EditMessageText)):
            self._ids += 1
            chat_id = data['chat_id']
            return Message(
                message_id=data.get('message_id') or self._ids, date=datetime.now(),
                chat=Chat(id=chat_id, type='private'), text=data['text'],
            )
        if isinstance(method, GetMe):
            return User(id=123456789, is_bot=True, first_name='Bot', username='test_bot')
        if isinstance(method, (DeleteMessage, AnswerCallbackQuery, SendChatAction, EditMessageReplyMarkup, SetMyCommands)):
            return True
        raise AssertionError(f'unexpected Telegram method {kind}')


class FakeApi:
    def __init__(self, events):
        self.events = events
        self.calls = []
        self.linked = False
        self.link = {
            'full_name': 'Dilnoza Karimova', 'role': 'counselor', 'language': 'en', 'notify_time': None,
            'prefs': {'essays': True, 'streak': True, 'application': True}, 'enabled': True,
        }
        self.card = {
            'pending_token': 'pending-token-1', 'full_name': 'Dilnoza Karimova',
            'email': 'dilnoza@example.com', 'phone': '+998901112233', 'role': 'counselor',
        }
        self.students_data = {'total': 2, 'groups': [
            {'grade': '9', 'count': 1, 'students': ['Ali Valiyev']},
            {'grade': '10', 'count': 1, 'students': ['Sara Nazarova']},
        ]}
        self.digest_data = {'date': '2026-11-08', 'total_students': 0, 'omitted': 0, 'students': []}
        self.errors = {}
        # What whoami answers for a chat that is not linked as a counselor.
        self.who = {'kind': 'staff_allowed', 'site_url': 'https://naseeb.example/meetings'}
        self.due_items = []
        self.outbox_items = []
        self.found = {'students': [{'id': 7, 'full_name': 'Ali Valiyev', 'username': 'ali-valiyev'}], 'more': False}

    def _record(self, name, **args):
        self.calls.append((name, args))
        self.events.append(('api', name, args))
        error = self.errors.get(name)
        if error:
            raise error

    def names(self, name):
        return [args for call, args in self.calls if call == name]

    async def login(self, chat_id, username, password, telegram_username=None):
        self._record('login', chat_id=chat_id, username=username, password=password, telegram_username=telegram_username)
        return self.card

    async def whoami(self, chat_id, telegram_username=None):
        self._record('whoami', chat_id=chat_id, telegram_username=telegram_username)
        if self.linked:
            return {'kind': 'staff_linked', 'name': self.link['full_name'], 'site_url': self.who['site_url']}
        return self.who

    async def confirm(self, chat_id, pending_token, language):
        self._record('confirm', chat_id=chat_id, pending_token=pending_token, language=language)
        self.linked = True
        self.link = {**self.link, 'language': language}
        return self.link

    async def students(self, chat_id):
        self._record('students', chat_id=chat_id)
        return self.students_data

    async def digest(self, chat_id):
        self._record('digest', chat_id=chat_id)
        return self.digest_data

    async def add_student(self, chat_id, full_name, email, phone):
        self._record('add_student', chat_id=chat_id, full_name=full_name, email=email, phone=phone)
        return {
            'full_name': full_name, 'username': 'saydazimova-sofiya', 'phone': '+998910076825',
            'temporary_password': 'Tmp-Pass-42', 'expires_at': '2026-11-13T16:14:20+00:00',
            'login_url': 'https://naseeb.example/login',
        }

    async def student_link(self, chat_id, token, language):
        self._record('student_link', chat_id=chat_id, token=token, language=language)
        return {'full_name': 'Ali <Valiyev> & Co', 'language': language}

    async def student_outbox(self):
        self._record('student_outbox')
        items, self.outbox_items = self.outbox_items, []
        return items

    async def student_outbox_ack(self, sent, blocked):
        self._record('student_outbox_ack', sent=sent, blocked=blocked)
        return {'sent': len(sent)}

    async def find_students(self, chat_id, query):
        self._record('find_students', chat_id=chat_id, query=query)
        return self.found

    async def reset_password(self, chat_id, student_id):
        self._record('reset_password', chat_id=chat_id, student_id=student_id)
        return {
            'full_name': 'Ali Valiyev', 'username': 'ali-valiyev', 'temporary_password': 'New-Pass-77',
            'expires_at': '2026-11-13T16:14:20+00:00', 'login_url': 'https://naseeb.example/login',
        }

    async def get_settings(self, chat_id):
        self._record('get_settings', chat_id=chat_id)
        if not self.linked:
            raise ApiError(404, 'not_linked')
        return self.link

    async def update_settings(self, chat_id, **changes):
        self._record('update_settings', chat_id=chat_id, **changes)
        prefs = {**self.link['prefs'], **changes.pop('prefs', {})}
        self.link = {**self.link, **changes, 'prefs': prefs}
        return self.link

    async def scheduled_jobs(self):
        self._record('scheduled_jobs')
        return {'ok': True}

    async def due(self):
        self._record('due')
        items, self.due_items = self.due_items, []
        return items

    async def mark_sent(self, chat_id, slot_date):
        self._record('mark_sent', chat_id=chat_id, slot_date=slot_date)
        return {'marked': True}

    async def logout(self, chat_id):
        self._record('logout', chat_id=chat_id)
        self.linked = False

    async def unlink(self, chat_id):
        self._record('unlink', chat_id=chat_id)
        self.linked = False


class Harness:
    def __init__(self):
        self.events = []
        self.session = MockedSession(self.events)
        self.bot = Bot(TOKEN, session=self.session)
        self.api = FakeApi(self.events)
        self.cache = TtlCache(5)
        self.dp = Dispatcher(storage=MemoryStorage(), api=self.api, cache=self.cache)
        self.dp.include_router(router)
        self._update_id = 0
        self._message_id = 0
        self.language_code = None
        self.username = 'dilnoza_k'

    def close(self):
        router._parent_router = None

    def _message(self, text, chat_id, message_id=None):
        self._message_id += 1
        return Message(
            message_id=message_id or self._message_id, date=datetime.now(), chat=Chat(id=chat_id, type='private'),
            from_user=User(
                id=chat_id, is_bot=False, first_name='Dilnoza', language_code=self.language_code, username=self.username,
            ), text=text,
        )

    async def say(self, text, chat_id=1, message_id=None):
        self._update_id += 1
        update = Update(update_id=self._update_id, message=self._message(text, chat_id, message_id))
        return await self.dp.feed_update(self.bot, update)

    async def tap(self, data, chat_id=1, message_id=500):
        self._update_id += 1
        callback = CallbackQuery(
            id=str(self._update_id), from_user=User(id=chat_id, is_bot=False, first_name='Dilnoza', username=self.username),
            chat_instance='x', message=self._message('menu', chat_id, message_id), data=data,
        )
        return await self.dp.feed_update(self.bot, Update(update_id=self._update_id, callback_query=callback))

    async def log_in(self, chat_id=1, language='en'):
        await self.say('/start', chat_id)
        await self.tap(f'lang:{language}', chat_id)
        await self.say('dilnoza', chat_id)
        await self.say(SECRET_PASSWORD, chat_id)
        await self.tap('login:confirm', chat_id)
