from aiogram.types import ChatMemberUpdated, ChatMemberBanned, ChatMemberMember, Chat, Update, User
from datetime import datetime

from bot.api import ApiError, ApiUnavailable


def keyboard(call):
    return [(b['text'], b['callback_data']) for row in call[1]['reply_markup']['inline_keyboard'] for b in row]


async def test_settings_panel_shows_toggles_time_and_language(h):
    h.api.linked = True
    await h.say('/settings')
    buttons = dict(keyboard(h.session.of('SendMessage')[-1]))
    assert any(data == 'part:essays' for data in buttons.values())
    assert {'part:essays', 'part:streak', 'part:application', 'set:time', 'set:lang', 'set:done'} <= set(buttons.values())


async def test_toggle_flips_one_part_and_redraws(h):
    h.api.linked = True
    await h.tap('part:streak')
    assert h.api.names('update_settings') == [{'chat_id': 1, 'prefs': {'streak': False}}]
    edit = h.session.of('EditMessageText')[-1]
    labels = dict((data, text) for text, data in keyboard(edit))
    assert labels['part:streak'].startswith('⬜') and labels['part:essays'].startswith('✅')
    await h.tap('part:streak')
    assert h.api.names('update_settings')[-1]['prefs'] == {'streak': True}


async def test_unknown_part_is_ignored(h):
    h.api.linked = True
    await h.tap('part:everything')
    assert not h.api.names('update_settings')


async def test_picking_a_time_button_saves_time_and_enables(h):
    h.api.linked = True
    await h.tap('time:07:00')
    assert h.api.names('update_settings') == [{'chat_id': 1, 'notify_time': '07:00', 'enabled': True}]
    assert 'Update time: 07:00' in h.session.texts()[-1]


async def test_skip_time_pauses_the_daily_update(h):
    h.api.linked = True
    await h.tap('time:off')
    assert h.api.names('update_settings') == [{'chat_id': 1, 'notify_time': None, 'enabled': True}]


async def test_custom_time_accepts_hh_mm_and_rejects_nonsense(h):
    h.api.linked = True
    await h.tap('time:custom')
    for bad in ('25:00', 'noon', '9:75', '12'):
        await h.say(bad)
        assert "couldn't read that time" in h.session.texts()[-1]
    assert not h.api.names('update_settings')
    await h.say('9.05')
    assert h.api.names('update_settings') == [{'chat_id': 1, 'notify_time': '09:05', 'enabled': True}]


async def test_language_button_changes_language_and_redraws_in_it(h):
    h.api.linked = True
    await h.tap('set:lang')
    await h.tap('setlang:ru')
    assert h.api.names('update_settings') == [{'chat_id': 1, 'language': 'ru'}]
    assert 'Настройки' in h.session.texts()[-1]
    await h.tap('setlang:xx')
    assert len(h.api.names('update_settings')) == 1


async def test_done_confirms_the_saved_time(h):
    h.api.linked = True
    h.api.link['notify_time'] = '20:00'
    await h.tap('set:done')
    assert 'Update: 20:00' in h.session.texts()[-1]


async def test_every_button_is_answered_immediately(h):
    h.api.linked = True
    await h.tap('part:essays')
    await h.tap('set:time')
    await h.tap('totally-unknown')
    kinds = [call[0] for call in h.session.calls]
    assert kinds.count('AnswerCallbackQuery') == 3
    assert h.session.calls[0][0] == 'AnswerCallbackQuery'


async def test_commands_need_a_link(h):
    for command in ('/settings', '/now', '/students'):
        await h.say(command)
        assert 'Avval kiring: /start' in h.session.texts()[-1]
    assert not h.api.names('digest') and not h.api.names('students')


async def test_logout_wipes_and_confirms(h):
    h.api.linked = True
    await h.say('/logout')
    assert h.api.names('logout') == [{'chat_id': 1}]
    assert 'Logged out' in h.session.texts()[-1]
    await h.say('/students')
    assert 'Avval kiring: /start' in h.session.texts()[-1]


async def test_logout_clears_the_chat_cache(h):
    h.api.linked = True
    await h.say('/students')
    await h.say('/logout')
    assert h.cache.get(('settings', 1)) is None and h.cache.get(('digest', 1)) is None


async def test_students_command_lists_a_to_z_and_caches_briefly(h):
    h.api.linked = True
    h.api.digest_data = {
        'date': '2026-11-08', 'total_students': 2, 'omitted': 0,
        'students': [
            {'id': 2, 'name': 'Sara Nazarova', 'grade': '10', 'last_seen_at': None, 'last_seen_expired': False},
            {'id': 1, 'name': 'Ali Valiyev', 'grade': '9', 'last_seen_at': None, 'last_seen_expired': False},
        ],
    }
    await h.say('/students')
    await h.say('/students')
    assert len(h.api.names('digest')) == 1
    text = h.session.texts()[-1]
    assert text.index('Ali Valiyev') < text.index('Sara Nazarova')
    assert 'A-Z' in text


async def test_no_students_is_one_short_friendly_message(h):
    h.api.linked = True
    h.api.digest_data = {**h.api.digest_data, 'total_students': 0}
    await h.say('/students')
    assert h.session.texts()[-1] == 'No students yet.'
    await h.say('/now')
    assert h.session.texts()[-1] == 'No students yet.'


async def test_now_shows_typing_then_edits_one_message(h):
    h.api.linked = True
    await h.say('/now')
    kinds = [c[0] for c in h.session.calls]
    assert 'SendChatAction' in kinds
    assert kinds.index('SendChatAction') < kinds.index('SendMessage') < kinds.index('EditMessageText')
    assert len(h.session.of('SendMessage')) == 1


async def test_backend_outage_gives_a_friendly_message(h):
    h.api.linked = True
    h.api.errors['digest'] = ApiUnavailable('timeout')
    await h.say('/students')
    assert 'temporarily unavailable' in h.session.texts()[-1]


async def test_blocking_the_bot_unlinks_the_chat(h):
    h.api.linked = True
    chat = Chat(id=1, type='private')
    user = User(id=1, is_bot=False, first_name='x')
    event = ChatMemberUpdated(
        chat=chat, from_user=user, date=datetime.now(),
        old_chat_member=ChatMemberMember(user=user), new_chat_member=ChatMemberBanned(user=user, until_date=datetime.now()),
    )
    await h.dp.feed_update(h.bot, Update(update_id=9, my_chat_member=event))
    assert h.api.names('unlink') == [{'chat_id': 1}]


async def test_a_wiped_link_tells_the_user_to_log_in_again(h):
    h.api.linked = True
    await h.say('/settings')
    h.api.errors['update_settings'] = ApiError(404, 'not_linked')
    await h.tap('part:streak')
    assert h.session.texts()[-1] == 'Please log in first: /start'
    assert h.cache.get(('settings', 1)) is None


async def test_other_backend_refusals_get_a_generic_message(h):
    h.api.linked = True
    h.api.errors['digest'] = ApiError(400, 'invalid_request')
    await h.say('/students')
    assert h.session.texts()[-1] == 'Something went wrong. Please try again.'


async def test_now_failing_on_the_edit_removes_the_placeholder_and_sends_the_update(h):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import EditMessageText
    h.api.linked = True
    h.session.failures['EditMessageText'] = [TelegramBadRequest(EditMessageText(text='x'), 'message to edit not found')]
    await h.say('/now')
    assert len(h.session.of('DeleteMessage')) == 1
    assert h.session.of('SendMessage')[-1][1]['text'] == 'No students yet.'


async def test_now_with_an_unmodified_edit_does_not_send_a_duplicate(h):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import EditMessageText
    h.api.linked = True
    h.session.failures['EditMessageText'] = [TelegramBadRequest(EditMessageText(text='x'), 'message is not modified')]
    await h.say('/now')
    assert not h.session.of('DeleteMessage')
    assert len(h.session.of('SendMessage')) == 1
