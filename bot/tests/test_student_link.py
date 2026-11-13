from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from bot.api import ApiError
from bot.scheduler import RateLimiter, deliver_student_messages


def buttons(call):
    return [b['callback_data'] for row in call[1]['reply_markup']['inline_keyboard'] for b in row]


TOKEN = 'Tk3-abcdEFGH_ijkl0123456789MNOPqrstuvwxyz1'


async def test_start_with_a_token_connects_the_student_in_their_telegram_language(h):
    h.language_code = 'ru'
    await h.say(f'/start s_{TOKEN}')
    assert h.api.names('student_link') == [{'chat_id': 1, 'token': TOKEN, 'language': 'ru'}]
    text = h.session.texts()[-1]
    # The name is escaped for HTML mode and the reply is in Russian.
    assert 'Подключено: <b>Ali &lt;Valiyev&gt; &amp; Co</b>' in text
    # No counselor flow is started and no code is involved.
    assert h.api.names('get_settings') == [] and h.api.names('whoami') == []
    assert h.session.of('SetMyCommands')


async def test_token_start_works_for_each_language_and_defaults_to_uzbek(h):
    for code, expected in (('en', 'Connected: <b>'), ('uz', 'Ulandi: <b>'), ('de', 'Ulandi: <b>'), (None, 'Ulandi: <b>')):
        h.language_code = code
        await h.say(f'/start s_{TOKEN}')
        assert expected in h.session.texts()[-1], code


async def test_an_expired_or_used_link_says_so_and_points_to_the_website(h):
    h.language_code = 'en'
    h.api.errors['student_link'] = ApiError(400, 'invalid_token', site_url='https://naseeb.example/meetings')
    await h.say(f'/start s_{TOKEN}')
    text = h.session.texts()[-1]
    assert 'expired or was already used' in text and 'https://naseeb.example/meetings' in text
    assert 'Connect Telegram' in text


async def test_too_many_attempts_gets_the_generic_error(h):
    h.language_code = 'en'
    h.api.errors['student_link'] = ApiError(429, 'too_many')
    await h.say(f'/start s_{TOKEN}')
    assert 'Something went wrong' in h.session.texts()[-1]


async def test_the_old_student_deep_link_and_unknown_payloads_are_a_plain_start(h):
    h.language_code = 'en'
    h.api.who = {'kind': 'unknown', 'site_url': 'https://naseeb.example/meetings'}
    for text in ('/start student', '/start whatever', '/start s_', '/start s_bad token'):
        await h.say(text)
    assert h.api.names('student_link') == []
    assert len(h.api.names('whoami')) == 4


async def test_plain_start_for_an_unknown_user_explains_who_the_bot_is_for(h):
    h.language_code = 'en'
    h.api.who = {'kind': 'unknown', 'site_url': 'https://naseeb.example/meetings'}
    await h.say('/start')
    text = h.session.texts()[-1]
    assert 'Naseeb students and counselors' in text
    assert "press 'Connect Telegram': https://naseeb.example/meetings" in text
    assert 'send your Telegram username to the administrator' in text
    # Has a username: no extra line, and no login flow, no language picker.
    assert 'set a Telegram username' not in text
    assert 'reply_markup' not in h.session.of('SendMessage')[-1][1] or not h.session.of('SendMessage')[-1][1]['reply_markup']
    assert h.api.names('whoami') == [{'chat_id': 1, 'telegram_username': 'dilnoza_k'}]


async def test_unknown_user_without_a_telegram_username_is_told_to_set_one(h):
    h.language_code = 'ru'
    h.username = None
    h.api.who = {'kind': 'unknown', 'site_url': 'https://naseeb.example/meetings'}
    await h.say('/start')
    text = h.session.texts()[-1]
    assert 'Этот бот для учеников и консультантов' in text and 'username в настройках Telegram' in text
    assert h.api.names('whoami') == [{'chat_id': 1, 'telegram_username': None}]


async def test_plain_start_for_a_linked_student_says_who_they_are(h):
    h.language_code = 'en'
    h.api.who = {'kind': 'student', 'name': 'Sara <N>', 'site_url': 'https://naseeb.example/meetings'}
    await h.say('/start')
    assert "You're connected as <b>Sara &lt;N&gt;</b>. Meeting messages come here." in h.session.texts()[-1]
    assert h.session.of('SetMyCommands')
    assert h.api.names('get_settings') == []


async def test_plain_start_for_an_allowed_counselor_opens_the_language_picker(h):
    await h.say('/start')
    call = h.session.of('SendMessage')[-1]
    assert 'Til' in call[1]['text']
    assert buttons(call) == ['lang:uz', 'lang:ru', 'lang:en']


async def test_plain_start_for_a_linked_counselor_keeps_the_existing_behaviour(h):
    await h.log_in()
    h.session.calls.clear()
    await h.say('/start')
    assert 'Dilnoza Karimova' in h.session.texts()[-1]
    assert buttons(h.session.of('SendMessage')[-1]) == ['login:again']


async def test_students_menu_has_no_counselor_commands():
    from bot.i18n import MENU, MENU_STUDENT

    for lang in ('uz', 'ru', 'en'):
        assert [name for name, _ in MENU_STUDENT[lang]] == ['start']
        assert 'code' not in [name for name, _ in MENU[lang]]


async def test_the_code_command_is_gone(h):
    await h.say('/code')
    assert h.api.names('student_link') == []
    assert 'Your code' not in ' '.join(h.session.texts())


async def test_outbox_messages_are_sent_and_acknowledged(h):
    h.api.outbox_items = [
        {'id': 1, 'chat_id': 10, 'text': 'Reminder A'},
        {'id': 2, 'chat_id': 11, 'text': 'Reminder B'},
    ]
    result = await deliver_student_messages(bot=h.bot, api=h.api, limiter=RateLimiter(per_second=1000))
    assert result == {'sent': 2, 'blocked': 0}
    assert [c[1]['text'] for c in h.session.of('SendMessage')] == ['Reminder A', 'Reminder B']
    assert h.api.names('student_outbox_ack') == [{'sent': [1, 2], 'blocked': []}]


async def test_blocked_chat_is_reported_and_skipped(h):
    h.session.failures['SendMessage'] = [TelegramForbiddenError(method=SendMessage(chat_id=10, text='x'), message='blocked')]
    h.api.outbox_items = [
        {'id': 1, 'chat_id': 10, 'text': 'A'},
        {'id': 2, 'chat_id': 10, 'text': 'B'},
        {'id': 3, 'chat_id': 11, 'text': 'C'},
    ]
    result = await deliver_student_messages(bot=h.bot, api=h.api, limiter=RateLimiter(per_second=1000))
    assert result == {'sent': 1, 'blocked': 1}
    assert h.api.names('student_outbox_ack') == [{'sent': [3], 'blocked': [10]}]


async def test_nothing_to_send_makes_no_ack(h):
    await deliver_student_messages(bot=h.bot, api=h.api, limiter=RateLimiter(per_second=1000))
    assert h.api.names('student_outbox_ack') == []


async def test_a_failed_ack_is_reported_first_next_minute(h):
    from bot.api import ApiUnavailable

    unacked = {'sent': [], 'blocked': set()}
    limiter = RateLimiter(per_second=1000)
    h.api.outbox_items = [{'id': 1, 'chat_id': 10, 'text': 'A'}]
    h.api.errors['student_outbox_ack'] = ApiUnavailable('timeout')
    await deliver_student_messages(bot=h.bot, api=h.api, limiter=limiter, unacked=unacked)
    assert unacked['sent'] == [1]
    # Still down: nothing new is fetched (and so nothing is sent twice) until the old sends are reported.
    await deliver_student_messages(bot=h.bot, api=h.api, limiter=limiter, unacked=unacked)
    assert len(h.api.names('student_outbox')) == 1
    del h.api.errors['student_outbox_ack']
    h.api.outbox_items = [{'id': 2, 'chat_id': 11, 'text': 'B'}]
    await deliver_student_messages(bot=h.bot, api=h.api, limiter=limiter, unacked=unacked)
    assert h.api.names('student_outbox_ack')[-2:] == [{'sent': [1], 'blocked': []}, {'sent': [2], 'blocked': []}]
    assert unacked == {'sent': [], 'blocked': set()}
    assert [c[1]['text'] for c in h.session.of('SendMessage')] == ['A', 'B']
