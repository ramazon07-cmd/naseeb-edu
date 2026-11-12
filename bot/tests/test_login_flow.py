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
    assert [e[1] for e in events[delete_user + 1:delete_pw]] == ['whoami', 'EditMessageText']
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


async def test_confirm_links_shows_the_student_count_then_asks_for_the_time(h):
    await h.log_in()
    assert h.api.names('confirm') == [{'chat_id': 1, 'pending_token': 'pending-token-1', 'language': 'en'}]
    linked = h.session.of('EditMessageText')[-1][1]['text']
    assert 'You have 2 students' in linked
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


async def test_confirm_shows_the_student_count_and_asks_for_the_time(h):
    h.api.students_data = {'total': 300, 'groups': []}
    await h.log_in()
    linked = h.session.of('EditMessageText')[-1][1]['text']
    assert 'Account linked' in linked and 'You have 300 students' in linked
    assert 'What time each day' in h.session.of('SendMessage')[-1][1]['text']


async def test_the_time_picker_still_appears_when_the_student_count_cannot_be_loaded(h):
    from bot.api import ApiUnavailable

    h.api.errors['students'] = ApiUnavailable('502')
    await h.log_in()
    linked = h.session.of('EditMessageText')[-1][1]['text']
    assert 'Account linked' in linked and 'students' not in linked
    assert 'What time each day' in h.session.of('SendMessage')[-1][1]['text']


async def test_backend_down_on_confirm_gives_the_card_and_buttons_back(h):
    await start_flow(h)
    await h.say('dilnoza')
    await h.say(SECRET_PASSWORD)
    h.api.errors['confirm'] = ApiUnavailable('timeout')
    await h.tap('login:confirm')
    restored = h.session.of('EditMessageText')[-1]
    assert 'Dilnoza Karimova' in restored[1]['text']
    buttons = [b['callback_data'] for row in restored[1]['reply_markup']['inline_keyboard'] for b in row]
    assert 'login:confirm' in buttons and 'login:cancel' in buttons
    assert 'temporarily unavailable' in h.session.texts()[-1]
    h.api.errors.clear()
    await h.tap('login:confirm')
    assert len(h.api.names('confirm')) == 2


async def test_a_command_while_waiting_for_the_password_is_not_sent_as_the_password(h):
    await start_flow(h)
    await h.say('dilnoza')
    await h.say('/help')
    assert not h.api.names('login')
    assert '/logout' in h.session.texts()[-1]


# --- only Telegram users a superadmin allowed reach the counselor login -------------------------

UNKNOWN = {'kind': 'unknown', 'site_url': 'https://naseeb.example/meetings'}


async def test_the_chats_telegram_username_is_sent_with_the_login(h):
    await h.log_in()
    assert h.api.names('login')[0]['telegram_username'] == 'dilnoza_k'
    assert h.api.names('whoami')[0] == {'chat_id': 1, 'telegram_username': 'dilnoza_k'}


async def test_a_chat_that_is_not_allowed_never_gets_the_language_picker(h):
    h.api.who = UNKNOWN
    await h.say('/start')
    assert 'for Naseeb students and counselors' in ' '.join(h.session.texts()) or 'Naseeb' in h.session.texts()[-1]
    assert not h.session.of('SendMessage')[-1][1].get('reply_markup')
    # Nothing is waiting for a username or password: text is just answered with help and deleted.
    await h.say('dilnoza', message_id=70)
    await h.say(SECRET_PASSWORD, message_id=71)
    assert h.api.names('login') == []
    assert [d['message_id'] for k, d in h.session.calls if k == 'DeleteMessage'] == [70, 71]


async def test_stray_login_buttons_are_refused_for_a_chat_that_is_not_allowed(h):
    h.api.who = UNKNOWN
    await h.tap('login:again')
    assert 'Naseeb students and counselors' in h.session.texts()[-1] or 'Naseeb' in h.session.texts()[-1]
    await h.tap('lang:en')
    assert h.api.names('login') == []
    # The username step is not reachable afterwards either.
    await h.say('dilnoza')
    await h.say(SECRET_PASSWORD)
    assert h.api.names('login') == []


async def test_an_allowed_chat_removed_from_the_list_mid_flow_is_stopped_at_each_step(h):
    await h.say('/start')
    h.api.who = UNKNOWN
    await h.tap('lang:en')
    assert 'Naseeb' in h.session.texts()[-1]
    # A stale state after the list changed: the username step re-checks too.
    h.api.who = {'kind': 'staff_allowed', 'site_url': 'x'}
    await h.say('/start')
    await h.tap('lang:en')
    h.api.who = UNKNOWN
    await h.say('dilnoza', message_id=80)
    await h.say(SECRET_PASSWORD, message_id=81)
    assert h.api.names('login') == []
    assert [d['message_id'] for k, d in h.session.calls if k == 'DeleteMessage'] == [80, 81]


async def test_login_refused_by_the_backend_for_a_mismatched_account_explains_and_stores_nothing(h):
    h.api.errors['login'] = ApiError(403, 'telegram_not_allowed')
    await start_flow(h, 'en')
    await h.say('someone-else')
    await h.say(SECRET_PASSWORD)
    assert 'not allowed to log in' in h.session.texts()[-1]
    assert SECRET_PASSWORD not in ' '.join(str(t) for t in h.session.texts())
    # The flow is over: another password message does nothing.
    del h.api.errors['login']
    await h.say(SECRET_PASSWORD)
    assert len(h.api.names('login')) == 1


async def test_a_linked_counselor_can_switch_account_but_only_while_they_are_still_staff(h):
    await h.log_in()
    await h.tap('login:again')
    assert 'Til' in h.session.texts()[-1]
