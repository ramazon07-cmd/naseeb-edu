from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from bot.api import ApiError
from bot.scheduler import RateLimiter, deliver_student_messages


def buttons(call):
    return [b['callback_data'] for row in call[1]['reply_markup']['inline_keyboard'] for b in row]


async def test_link_from_the_website_shows_a_code_in_the_students_language(h):
    h.language_code = 'ru'
    await h.say('/start student')
    assert h.api.names('student_code') == [{'chat_id': 1, 'language': 'ru'}]
    message = h.session.of('SendMessage')[-1]
    assert '482913' in message[1]['text'] and 'Meetings' in message[1]['text'] and 'Ваш код' in message[1]['text']
    assert buttons(message) == ['scode:ru']
    # No counselor login is started for a student.
    assert h.api.names('get_settings') == []


async def test_unknown_language_falls_back_to_uzbek_and_new_code_edits_the_message(h):
    h.language_code = 'de'
    await h.say('/code')
    assert h.api.names('student_code')[-1]['language'] == 'uz'
    await h.tap('scode:uz')
    assert len(h.api.names('student_code')) == 2
    assert '482913' in h.session.of('EditMessageText')[-1][1]['text']


async def test_plain_start_points_students_to_code(h):
    await h.say('/start')
    assert '/code' in h.session.texts()[-1]


async def test_too_many_codes_is_explained(h):
    h.api.errors['student_code'] = ApiError(429, 'too_many')
    await h.say('/code')
    assert 'Too many codes' in h.session.texts()[-1] or "ko'p kod" in h.session.texts()[-1]


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
