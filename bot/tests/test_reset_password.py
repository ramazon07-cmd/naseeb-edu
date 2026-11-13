from bot.api import ApiError, ApiUnavailable
from bot.handlers import _resetting

from .test_render import digest, many


def buttons(call):
    return [b['callback_data'] for row in call[1]['reply_markup']['inline_keyboard'] for b in row]


def last_markup_call(h):
    return [c for c in h.session.calls if c[0] in ('SendMessage', 'EditMessageText') and c[1].get('reply_markup')][-1]


async def test_reset_asks_whom_then_confirms_then_resets(h):
    await h.log_in()
    await h.say('/reset')
    assert "Who needs a new password" in h.session.texts()[-1]
    await h.say('ali')
    assert h.api.names('find_students') == [{'chat_id': 1, 'query': 'ali'}]
    card = h.session.of('SendMessage')[-1]
    assert 'Ali Valiyev' in card[1]['text'] and 'ali-valiyev' in card[1]['text']
    assert buttons(card) == ['rpy:7', 'rp:x']
    assert h.api.names('reset_password') == []

    await h.tap('rpy:7')
    assert h.api.names('reset_password') == [{'chat_id': 1, 'student_id': 7}]
    done = h.session.texts()[-1]
    assert 'New-Pass-77' in done and 'ali-valiyev' in done and '13.11.2026 21:14' in done
    assert 'https://naseeb.example/login' in done


async def test_name_can_follow_the_command(h):
    await h.log_in()
    await h.say('/reset Ali Valiyev')
    assert h.api.names('find_students') == [{'chat_id': 1, 'query': 'Ali Valiyev'}]
    assert buttons(h.session.of('SendMessage')[-1]) == ['rpy:7', 'rp:x']


async def test_several_matches_offer_a_choice(h):
    await h.log_in()
    h.api.found = {'students': [
        {'id': 7, 'full_name': 'Ali Valiyev', 'username': 'ali-valiyev'},
        {'id': 8, 'full_name': 'Ali Karimov', 'username': 'ali-karimov'},
    ], 'more': True}
    await h.say('/reset ali')
    pick = h.session.of('SendMessage')[-1]
    assert buttons(pick) == ['rp:7', 'rp:8', 'rp:x']
    assert 'Not all are shown' in pick[1]['text']
    await h.tap('rp:8')
    card = last_markup_call(h)
    assert 'Ali Karimov' in card[1]['text'] and buttons(card) == ['rpy:8', 'rp:x']
    await h.tap('rpy:8')
    assert h.api.names('reset_password') == [{'chat_id': 1, 'student_id': 8}]


async def test_no_match_asks_again(h):
    await h.log_in()
    h.api.found = {'students': [], 'more': False}
    await h.say('/reset zzz')
    assert 'No student of yours matches' in h.session.texts()[-1]
    h.api.found = {'students': [{'id': 9, 'full_name': 'Zara Aliyeva', 'username': 'zara'}], 'more': False}
    await h.say('zara')
    assert buttons(h.session.of('SendMessage')[-1]) == ['rpy:9', 'rp:x']


async def test_cancel_changes_nothing(h):
    await h.log_in()
    await h.say('/reset ali')
    await h.tap('rp:x')
    assert h.api.names('reset_password') == []
    assert 'password was not changed' in h.session.texts()[-1]
    await h.say('/reset')
    await h.say('/cancel')
    assert 'password was not changed' in h.session.texts()[-1]


async def test_student_card_has_a_new_password_button(h):
    await h.log_in()
    h.api.digest_data = digest(many(5))
    await h.tap('rp:3')
    card = h.session.of('SendMessage')[-1]
    assert 'Student Number 002' in card[1]['text'] and buttons(card) == ['rpy:3', 'rp:x']
    await h.tap('rpy:3')
    assert h.api.names('reset_password') == [{'chat_id': 1, 'student_id': 3}]


async def test_a_student_no_longer_listed_is_explained(h):
    await h.log_in()
    h.api.errors['reset_password'] = ApiError(404, 'student_not_found')
    await h.tap('rpy:7')
    assert 'no longer on your list' in h.session.texts()[-1]


async def test_rate_limit_is_explained(h):
    await h.log_in()
    h.api.errors['reset_password'] = ApiError(429, 'too_many')
    await h.tap('rpy:7')
    assert 'Too many passwords' in h.session.texts()[-1]


async def test_backend_down_gives_the_card_back(h):
    await h.log_in()
    h.api.errors['reset_password'] = ApiUnavailable('timeout')
    await h.tap('rpy:7')
    assert buttons(last_markup_call(h)) == ['rpy:7', 'rp:x']
    assert 'temporarily unavailable' in h.session.texts()[-1]
    assert not _resetting


async def test_unlinked_chat_cannot_reset(h):
    await h.say('/reset ali')
    assert h.api.names('find_students') == []
    await h.tap('rpy:7')
    assert h.api.names('reset_password') == []


async def test_a_tap_while_a_reset_is_running_is_ignored(h):
    await h.log_in()
    _resetting.add(1)
    try:
        await h.tap('rpy:7')
    finally:
        _resetting.discard(1)
    assert h.api.names('reset_password') == []


async def test_menu_lists_the_commands_in_each_language():
    from bot.main import set_menu

    calls = []

    class FakeBot:
        async def set_my_commands(self, commands, language_code=None):
            calls.append((language_code, [c.command for c in commands]))

    await set_menu(FakeBot())
    assert [code for code, _ in calls] == [None, 'ru', 'en']
    assert all(names[:2] == ['add', 'reset'] for _, names in calls)
    assert all('code' not in names for _, names in calls)


async def test_a_reset_tap_keeps_a_waiting_add_card(h):
    from .test_add_student import SOFIYA

    await h.log_in()
    await h.say(SOFIYA)
    await h.tap('rpy:7')
    await h.tap('add:yes')
    assert len(h.api.names('add_student')) == 1
