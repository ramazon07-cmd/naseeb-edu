import logging
import re
from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, ChatMemberUpdatedFilter, KICKED
from aiogram.filters.exception import ExceptionTypeFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ChatMemberUpdated, ErrorEvent, Message

from . import keyboards
from .api import ApiError, ApiUnavailable
from .delivery import list_message, send_digest
from .i18n import DEFAULT, LANGUAGES, t
from .render import SORT_AZ, contacts, render_detail

log = logging.getLogger('bot.handlers')
router = Router()
router.message.filter(F.chat.type == 'private')
router.callback_query.filter(F.message.chat.type == 'private')

COMMAND_PATTERN = re.compile(r'^/(start|help|now|students|settings|logout)(@\w+)?(\s|$)')
TIME_PATTERN = re.compile(r'^\s*(\d{1,2})[:.](\d{2})\s*$')
LIST_BUTTON = re.compile(r'^l:(\d{1,4}):([az]):([ai])$')
DETAIL_BUTTON = re.compile(r'^d:(\d{1,12}):(\d{1,4}):([az]):([ai])$')


class Login(StatesGroup):
    language = State()
    username = State()
    password = State()
    confirm = State()


class Setup(StatesGroup):
    custom_time = State()


async def _delete(message):
    with suppress(TelegramAPIError):
        await message.delete()


async def _edit(bot, chat_id, message_id, text, markup=None):
    with suppress(TelegramBadRequest):
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)


async def get_link(api, cache, chat_id, *, fresh=False):
    """The chat's settings (which hold its language), or None when the chat is not linked."""
    key = ('settings', chat_id)
    if not fresh:
        cached = cache.get(key)
        if cached is not None:
            return cached
    try:
        link = await api.get_settings(chat_id)
    except ApiError as exc:
        if exc.code == 'not_linked':
            cache.drop_chat(chat_id)
            return None
        raise
    cache.set(key, link)
    return link


async def language_of(state, cache, chat_id):
    data = await state.get_data()
    if data.get('lang'):
        return data['lang']
    cached = cache.get(('settings', chat_id))
    return cached['language'] if cached else DEFAULT


def _minutes(error):
    return max(1, int(error.extra.get('retry_after', 900)) // 60)


def _time_text(link, lang):
    return link['notify_time'] if link['enabled'] and link['notify_time'] else t(lang, 'time_off')


async def _panel(bot, chat_id, message_id, link):
    lang = link['language']
    text = t(lang, 'settings_title', time=_time_text(link, lang)) + '\n\n' + t(lang, 'setup_parts')
    markup = keyboards.settings_panel(lang, link['prefs'], _time_text(link, lang) if link['enabled'] else None)
    if message_id is None:
        await bot.send_message(chat_id, text, reply_markup=markup)
    else:
        await _edit(bot, chat_id, message_id, text, markup)


async def _change(api, cache, chat_id, **changes):
    link = await api.update_settings(chat_id, **changes)
    cache.drop_chat(chat_id)
    cache.set(('settings', chat_id), link)
    return link


@router.message(Command('start'))
async def start(message: Message, state: FSMContext, api, cache):
    await state.clear()
    chat_id = message.chat.id
    link = await get_link(api, cache, chat_id, fresh=True)
    if link:
        lang = link['language']
        await message.answer(
            t(lang, 'already_linked', name=escape(link['full_name'])), reply_markup=keyboards.already_linked(lang),
        )
        return
    await state.set_state(Login.language)
    await message.answer('Til / Язык / Language', reply_markup=keyboards.languages())


@router.callback_query(F.data == 'login:again')
async def login_again(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(Login.language)
    await callback.message.edit_text('Til / Язык / Language', reply_markup=keyboards.languages())


@router.callback_query(Login.language, F.data.startswith('lang:'))
async def pick_language(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    lang = callback.data.split(':', 1)[1]
    if lang not in LANGUAGES:
        return
    await state.update_data(lang=lang, prompt_id=callback.message.message_id)
    await state.set_state(Login.username)
    await callback.message.edit_text(t(lang, 'welcome'))


@router.message(Login.username, F.text, ~F.text.regexp(COMMAND_PATTERN))
async def got_username(message: Message, state: FSMContext, bot):
    username = message.text.strip()
    await _delete(message)
    data = await state.get_data()
    lang = data.get('lang', DEFAULT)
    await state.update_data(username=username)
    await state.set_state(Login.password)
    await _edit(bot, message.chat.id, data.get('prompt_id'), t(lang, 'ask_password'))


@router.message(Login.password, ~F.text.regexp(COMMAND_PATTERN))
async def got_password(message: Message, state: FSMContext, bot, api):
    # Nothing else may run before the password message is gone.
    password = message.text
    await _delete(message)
    chat_id = message.chat.id
    data = await state.get_data()
    lang, prompt_id, username = data.get('lang', DEFAULT), data.get('prompt_id'), data.get('username')
    if not password or not username:
        await _edit(bot, chat_id, prompt_id, t(lang, 'ask_password'))
        return
    await _edit(bot, chat_id, prompt_id, t(lang, 'checking'))
    await bot.send_chat_action(chat_id, 'typing')
    try:
        card = await api.login(chat_id, username, password)
    except ApiError as exc:
        await _login_refused(bot, state, chat_id, prompt_id, lang, exc)
        return
    finally:
        del password
    await state.update_data(pending=card['pending_token'], username=None)
    await state.set_state(Login.confirm)
    text = t(lang, 'card', name=escape(card['full_name']), contacts=contacts(card['email'], card['phone']))
    await state.update_data(card_text=text)
    await _edit(bot, chat_id, prompt_id, text, keyboards.confirm_card(lang))


async def _login_refused(bot, state, chat_id, prompt_id, lang, exc):
    if exc.code == 'invalid_credentials':
        await state.update_data(username=None)
        await state.set_state(Login.username)
        text = t(lang, 'bad_credentials')
    else:
        await state.clear()
        text = {
            'locked': lambda: t(lang, 'locked', minutes=_minutes(exc)),
            'role_not_allowed': lambda: t(lang, 'role_refused'),
            'password_change_required': lambda: t(lang, 'password_change_required'),
            'account_unavailable': lambda: t(lang, 'account_unavailable'),
        }.get(exc.code, lambda: t(lang, 'error'))()
    await _edit(bot, chat_id, prompt_id, text)


@router.callback_query(Login.confirm, F.data == 'login:cancel')
async def login_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    lang = (await state.get_data()).get('lang', DEFAULT)
    await state.clear()
    await callback.message.edit_text(t(lang, 'cancelled'))


@router.callback_query(Login.confirm, F.data == 'login:confirm')
async def login_confirm(callback: CallbackQuery, state: FSMContext, bot, api, cache):
    await callback.answer()
    chat_id = callback.message.chat.id
    data = await state.get_data()
    lang = data.get('lang', DEFAULT)
    await callback.message.edit_text(t(lang, 'checking'))
    try:
        link = await api.confirm(chat_id, data.get('pending', ''), lang)
    except ApiError:
        await state.clear()
        await callback.message.edit_text(t(lang, 'pending_expired'))
        return
    except ApiUnavailable:
        # The token is still good for 10 minutes: give the card and its buttons back.
        if data.get('card_text'):
            await _edit(bot, chat_id, callback.message.message_id, data['card_text'], keyboards.confirm_card(lang))
        raise
    await state.clear()
    cache.drop_chat(chat_id)
    cache.set(('settings', chat_id), link)
    linked = t(lang, 'linked', name=escape(link['full_name']))
    try:
        linked += '\n\n' + t(lang, 'students_count', total=(await api.students(chat_id))['total'])
    except (ApiError, ApiUnavailable):
        pass
    await callback.message.edit_text(linked)
    await bot.send_message(chat_id, t(lang, 'setup_time'), reply_markup=keyboards.time_picker(lang))


@router.message(Command('help'))
async def help_command(message: Message, state: FSMContext, api, cache):
    lang = await language_of(state, cache, message.chat.id)
    await message.answer(t(lang, 'help'))


async def _require_link(message, api, cache, state):
    link = await get_link(api, cache, message.chat.id)
    if link is None:
        lang = await language_of(state, cache, message.chat.id)
        await message.answer(t(lang, 'not_linked'))
    return link


async def _load_digest(api, cache, chat_id):
    key = ('digest', chat_id)
    data = cache.get(key)
    if data is None:
        data = await api.digest(chat_id)
        cache.set(key, data)
    return data


@router.message(Command('students'))
async def students_command(message: Message, state: FSMContext, bot, api, cache):
    link = await _require_link(message, api, cache, state)
    if link is None:
        return
    chat_id, lang = message.chat.id, link['language']
    await bot.send_chat_action(chat_id, 'typing')
    await send_digest(bot, chat_id, await _load_digest(api, cache, chat_id), lang, sort=SORT_AZ)


@router.message(Command('now'))
async def now_command(message: Message, state: FSMContext, bot, api, cache):
    link = await _require_link(message, api, cache, state)
    if link is None:
        return
    chat_id, lang = message.chat.id, link['language']
    await bot.send_chat_action(chat_id, 'typing')
    placeholder = await message.answer(t(lang, 'preparing'))
    try:
        data = await _load_digest(api, cache, chat_id)
    except ApiError as exc:
        if exc.code == 'not_linked':
            await _edit(bot, chat_id, placeholder.message_id, t(lang, 'not_linked'))
            return
        raise
    await send_digest(bot, chat_id, data, lang, edit_message_id=placeholder.message_id)


@router.callback_query(F.data == 'noop')
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.regexp(LIST_BUTTON))
async def list_page(callback: CallbackQuery, bot, api, cache):
    await callback.answer()
    chat_id = callback.message.chat.id
    link = await get_link(api, cache, chat_id)
    if link is None:
        await bot.send_message(chat_id, t(DEFAULT, 'not_linked'))
        return
    page, sort, flt = LIST_BUTTON.match(callback.data).groups()
    text, markup = list_message(await _load_digest(api, cache, chat_id), link['language'], int(page), sort, flt)
    await _edit(bot, chat_id, callback.message.message_id, text, markup)


@router.callback_query(F.data.regexp(DETAIL_BUTTON))
async def student_detail(callback: CallbackQuery, bot, api, cache):
    chat_id = callback.message.chat.id
    link = await get_link(api, cache, chat_id)
    if link is None:
        await callback.answer()
        await bot.send_message(chat_id, t(DEFAULT, 'not_linked'))
        return
    lang = link['language']
    student_id, page, sort, flt = DETAIL_BUTTON.match(callback.data).groups()
    data = await _load_digest(api, cache, chat_id)
    item = next((student for student in data['students'] if student.get('id') == int(student_id)), None)
    if item is None:
        await callback.answer(t(lang, 'student_gone'), show_alert=True)
        return
    await callback.answer()
    await _edit(
        bot, chat_id, callback.message.message_id, render_detail(item, lang),
        keyboards.back_to_list(lang, int(page), sort, flt),
    )


@router.message(Command('settings'))
async def settings_command(message: Message, state: FSMContext, bot, api, cache):
    link = await _require_link(message, api, cache, state)
    if link is not None:
        await _panel(bot, message.chat.id, None, link)


@router.callback_query(F.data.startswith('part:'))
async def toggle_part(callback: CallbackQuery, bot, api, cache):
    await callback.answer()
    chat_id = callback.message.chat.id
    part = callback.data.split(':', 1)[1]
    link = await get_link(api, cache, chat_id)
    if link is None or part not in keyboards.PARTS:
        return
    link = await _change(api, cache, chat_id, prefs={part: not link['prefs'].get(part, True)})
    await _panel(bot, chat_id, callback.message.message_id, link)


@router.callback_query(F.data == 'set:time')
async def open_time(callback: CallbackQuery, api, cache):
    await callback.answer()
    link = await get_link(api, cache, callback.message.chat.id)
    lang = link['language'] if link else DEFAULT
    await callback.message.edit_text(t(lang, 'setup_time'), reply_markup=keyboards.time_picker(lang))


@router.callback_query(F.data.startswith('time:'))
async def pick_time(callback: CallbackQuery, state: FSMContext, bot, api, cache):
    await callback.answer()
    chat_id, value = callback.message.chat.id, callback.data.split(':', 1)[1]
    link = await get_link(api, cache, chat_id)
    if link is None:
        return
    lang = link['language']
    if value == 'custom':
        await state.set_state(Setup.custom_time)
        await state.update_data(prompt_id=callback.message.message_id)
        await callback.message.edit_text(t(lang, 'ask_custom_time'))
        return
    if value == 'off':
        link = await _change(api, cache, chat_id, notify_time=None, enabled=True)
    elif TIME_PATTERN.match(value):
        link = await _change(api, cache, chat_id, notify_time=value, enabled=True)
    else:
        return
    await _panel(bot, chat_id, callback.message.message_id, link)


@router.message(Setup.custom_time, F.text)
async def custom_time(message: Message, state: FSMContext, bot, api, cache):
    chat_id = message.chat.id
    link = await get_link(api, cache, chat_id)
    if link is None:
        await state.clear()
        return
    match = TIME_PATTERN.match(message.text)
    hour, minute = (int(match.group(1)), int(match.group(2))) if match else (99, 99)
    if hour > 23 or minute > 59:
        await message.answer(t(link['language'], 'bad_time'))
        return
    data = await state.get_data()
    await state.clear()
    link = await _change(api, cache, chat_id, notify_time=f'{hour:02d}:{minute:02d}', enabled=True)
    await _panel(bot, chat_id, data.get('prompt_id'), link)


@router.callback_query(F.data == 'set:lang')
async def open_language(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text('Til / Язык / Language', reply_markup=keyboards.languages('setlang'))


@router.callback_query(F.data.startswith('setlang:'))
async def change_language(callback: CallbackQuery, bot, api, cache):
    await callback.answer()
    lang = callback.data.split(':', 1)[1]
    chat_id = callback.message.chat.id
    if lang not in LANGUAGES or await get_link(api, cache, chat_id) is None:
        return
    link = await _change(api, cache, chat_id, language=lang)
    await _panel(bot, chat_id, callback.message.message_id, link)


@router.callback_query(F.data == 'set:done')
async def settings_done(callback: CallbackQuery, api, cache):
    await callback.answer()
    link = await get_link(api, cache, callback.message.chat.id)
    if link is None:
        return
    lang = link['language']
    await callback.message.edit_text(t(lang, 'saved', time=_time_text(link, lang)))


@router.message(Command('logout'))
async def logout(message: Message, state: FSMContext, api, cache):
    chat_id = message.chat.id
    lang = await language_of(state, cache, chat_id)
    link = cache.get(('settings', chat_id))
    if link is None:
        with suppress(ApiError):
            link = await get_link(api, cache, chat_id)
    if link:
        lang = link['language']
    await api.logout(chat_id)
    await state.clear()
    cache.drop_chat(chat_id)
    await message.answer(t(lang, 'logged_out'))


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def blocked(event: ChatMemberUpdated, api, cache):
    chat_id = event.chat.id
    with suppress(ApiError, ApiUnavailable):
        await api.unlink(chat_id)
    cache.drop_chat(chat_id)


@router.message(F.text)
async def stray_text(message: Message, state: FSMContext, api, cache):
    # No step expects text here. After a restart a password may arrive this way, so it is not left in the chat.
    await _delete(message)
    lang = await language_of(state, cache, message.chat.id)
    await message.answer(t(lang, 'help'))


@router.callback_query()
async def stale_button(callback: CallbackQuery):
    await callback.answer(t(DEFAULT, 'expired'))


@router.errors(ExceptionTypeFilter(ApiUnavailable))
async def backend_down(event: ErrorEvent, bot, cache, state: FSMContext):
    update = event.update
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if update.callback_query:
        with suppress(TelegramAPIError):
            await update.callback_query.answer()
    if message:
        cached = cache.get(('settings', message.chat.id))
        lang = (await state.get_data()).get('lang') or (cached['language'] if cached else DEFAULT)
        if await state.get_state() == Login.password.state:
            await state.clear()
        with suppress(TelegramAPIError):
            await bot.send_message(message.chat.id, t(lang, 'unavailable'))
    log.warning('backend unavailable: %s', event.exception)
    return True


@router.errors(ExceptionTypeFilter(ApiError))
async def backend_refused(event: ErrorEvent, bot, cache, state: FSMContext):
    update = event.update
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if update.callback_query:
        with suppress(TelegramAPIError):
            await update.callback_query.answer()
    if message:
        chat_id = message.chat.id
        lang = await language_of(state, cache, chat_id)
        if event.exception.code == 'not_linked':
            cache.drop_chat(chat_id)
            text = t(lang, 'not_linked')
        else:
            text = t(lang, 'error')
        with suppress(TelegramAPIError):
            await bot.send_message(chat_id, text)
    log.warning('backend refused: %s', event.exception)
    return True
