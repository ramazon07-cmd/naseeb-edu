import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.base import StorageKey

from bot.api import ApiError, ApiUnavailable

from .helpers import SECRET_PASSWORD


async def start_flow(h, language='en'):
    await h.say('/start')
    await h.tap(f'lang:{language}')


def index_of(events, predicate):
    return next(i for i, event in enumerate(events) if predicate(event))


async def test_start_asks_for_language_then_username(h):
    await h.say('/start')
    assert 'Til' in h.session.texts()[-1]
    await h.tap('lang:uz')
    assert 'foydalanuvchi nomingizni' in h.session.texts()[-1]


async def test_username_and_password_messages_are_deleted_before_anything_else(h):
    await start_flow(h)
    await h.say('dilnoza', message_id=66)
    await h.say(SECRET_PASSWORD, message_id=77)

    deleted = [data['message_id'] for kind, data in h.session.calls if kind == 'DeleteMessage']
    assert deleted == [66, 77]
    events = h.events
    delete_user = index_of(events, lambda e: e[1] == 'DeleteMessage' and e[2]['message_id'] == 66)
    delete_pw = index_of(events, lambda e: e[1] == 'DeleteMessage' and e[2]['message_id'] == 77)
    login = index_of(events, lambda e: e[0] == 'api' and e[1] == 'login')
    assert delete_user < delete_pw < login
    # between the two deletions only the prompt edit happened; after the password arrived the delete is the first call
    assert [e[1] for e in events[delete_user + 1:delete_pw]] == ['EditMessageText']
    assert [e[1] for e in events[delete_pw:login]] == ['DeleteMessage', 'EditMessageText', 'SendChatAction']


async def test_password_is_sent_to_the_backend_exactly_once_and_nowhere_else(h, caplog):
    caplog.set_level(logging.DEBUG)
    await start_flow(h)
    await h.say('dilnoza', message_id=66)
    await h.say(SECRET_PASSWORD, message_id=77)
    await h.tap('login:confirm')
    await h.say('/settings')
    await h.say('/now')

    api_calls_with_password = [name for name, args in h.api.calls if SECRET_PASSWORD in repr(args)]
    assert api_calls_with_password == ['login']
    assert SECRET_PASSWORD not in repr(h.session.calls)
    for record in caplog.records:
        assert SECRET_PASSWORD not in record.getMessage()
        assert SECRET_PASSWORD not in repr(record.args)
        assert SECRET_PASSWORD not in (record.exc_text or '')
    assert SECRET_PASSWORD not in caplog.text
    storage = h.dp.fsm.storage
    assert SECRET_PASSWORD not in repr(storage.storage)


async def test_password_survives_in_no_fsm_data_even_while_waiting_for_confirm(h):
    await start_flow(h)
    await h.say('dilnoza')
    await h.say(SECRET_PASSWORD)
    assert SECRET_PASSWORD not in repr(h.dp.fsm.storage.storage)


async def test_confirmation_card_shows_name_and_contacts_with_buttons(h):
    await start_flow(h)
    await h.say('dilnoza')
    await h.say(SECRET_PASSWORD)
    edit = h.session.of('EditMessageText')[-1][1]
    assert 'Dilnoza Karimova' in edit['text']
    assert 'dilnoza@example.com' in edit['text'] and '+998901112233' in edit['text']
    buttons = [b['callback_data'] for row in edit['reply_markup']['inline_keyboard'] for b in row]
    assert buttons == ['login:confirm', 'login:cancel']
    assert not h.api.names('confirm')


async def test_confirm_links_shows_students_by_grade_then_asks_for_the_time(h):
    await h.log_in()
    assert h.api.names('confirm') == [{'chat_id': 1, 'pending_token': 'pending-token-1', 'language': 'en'}]
    linked = h.session.of('EditMessageText')[-1][1]['text']
    assert 'Students: 2' in linked
    assert 'Grade 9: 1' in linked and 'Ali Valiyev' in linked and 'Grade 10: 1' in linked
    last = h.session.of('SendMessage')[-1][1]
    assert 'What time each day' in last['text']
    times = [b['text'] for row in last['reply_markup']['inline_keyboard'] for b in row]
    assert '07:00' in times and '21:00' in times and 'Other time' in times


async def test_cancel_does_not_confirm(h):
    await start_flow(h)
    await h.say('dilnoza')
    await h.say(SECRET_PASSWORD)
    await h.tap('login:cancel')
    assert not h.api.names('confirm')
    assert 'Cancelled' in h.session.texts()[-1]
    await h.tap('login:confirm')
    assert not h.api.names('confirm')


async def test_wrong_credentials_return_to_the_username_step(h):
    h.api.errors['login'] = ApiError(401, 'invalid_credentials')
    await start_flow(h)
    await h.say('dilnoza')
    await h.say('wrong-password-1')
    assert 'Wrong username or password' in h.session.texts()[-1]
    h.api.errors.clear()
    await h.say('dilnoza')
    await h.say(SECRET_PASSWORD)
    assert 'Dilnoza Karimova' in h.session.texts()[-1]


async def test_refused_roles_get_a_polite_message_and_nothing_is_kept(h):
    h.api.errors['login'] = ApiError(403, 'role_not_allowed')
    await start_flow(h)
    await h.say('someone')
    await h.say(SECRET_PASSWORD)
    assert 'only for counselors' in h.session.texts()[-1]
    key = StorageKey(bot_id=123456789, chat_id=1, user_id=1)
    assert await h.dp.fsm.storage.get_state(key) is None
    await h.tap('login:confirm')
    assert not h.api.names('confirm')


async def test_lockout_message_names_the_wait(h):
    h.api.errors['login'] = ApiError(429, 'locked', retry_after=900)
    await start_flow(h)
    await h.say('dilnoza')
    await h.say('x')
    assert '15 min' in h.session.texts()[-1]


async def test_backend_down_during_login_says_so(h):
    h.api.errors['login'] = ApiUnavailable('timeout')
    await start_flow(h)
    await h.say('dilnoza')
    await h.say(SECRET_PASSWORD)
    assert 'temporarily unavailable' in h.session.texts()[-1]


async def test_a_failed_delete_does_not_stop_the_flow(h):
    h.session.failures['DeleteMessage'] = [TelegramBadRequest(method=None, message='message can\'t be deleted')] * 2
    await start_flow(h)
    await h.say('dilnoza')
    await h.say(SECRET_PASSWORD)
    assert h.api.names('login')


async def test_stray_text_after_a_restart_is_deleted(h):
    await h.say(SECRET_PASSWORD, message_id=91)
    assert [d['message_id'] for k, d in h.session.calls if k == 'DeleteMessage'] == [91]
    assert not h.api.names('login')


async def test_start_when_already_linked_offers_other_account(h):
    h.api.linked = True
    await h.say('/start')
    assert "You're logged in as Dilnoza Karimova" in h.session.texts()[-1]


async def test_start_when_already_linked_escapes_the_name(h):
    h.api.linked = True
    h.api.link['full_name'] = 'A<b>&Co'
    await h.say('/start')
    assert 'A&lt;b&gt;&amp;Co' in h.session.texts()[-1]


async def test_confirm_with_hundreds_of_students_still_asks_for_the_time(h):
    names = [f'Student Number {i} ' + 'Z' * 40 for i in range(300)]
    h.api.students_data = {'total': 300, 'groups': [{'grade': '10', 'count': 300, 'students': names}]}
    await h.log_in()
    texts = h.session.texts()
    assert all(len(text) <= 4096 for text in texts)
    assert 'What time each day' in h.session.of('SendMessage')[-1][1]['text']
    assert sum(text.count('Student Number') for text in texts) == 300
