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
from aiogram.types import BotCommand, BotCommandScopeChat, CallbackQuery, ChatMemberUpdated, ErrorEvent, Message

from . import keyboards
from .api import ApiError, ApiUnavailable
from .delivery import list_message, send_digest
from .i18n import DEFAULT, LANGUAGES, MENU_STUDENT, t
from .render import SORT_AZ, contacts, render_detail
from .students import format_expiry, is_complete, parse_student

log = logging.getLogger('bot.handlers')
router = Router()
router.message.filter(F.chat.type == 'private')
router.callback_query.filter(F.message.chat.type == 'private')

COMMAND_PATTERN = re.compile(r'^/(start|help|now|students|add|reset|cancel|settings|logout)(@\w+)?(\s|$)')
LANGUAGE_PROMPT = 'Til / Язык / Language'
STUDENT_START = r'^/start(@\w+)?\s+s_([A-Za-z0-9_-]{1,62})\s*$'
STAFF_KINDS = ('staff_linked', 'staff_allowed')
TIME_PATTERN = re.compile(r'^\s*(\d{1,2})[:.](\d{2})\s*$')
LIST_BUTTON = re.compile(r'^l:(\d{1,4}):([az]):([ai])$')
DETAIL_BUTTON = re.compile(r'^d:(\d{1,12}):(\d{1,4}):([az]):([ai])$')
RESET_PICK = re.compile(r'^rp:(\d{1,12})$')
RESET_YES = re.compile(r'^rpy:(\d{1,12})$')


class Login(StatesGroup):
    language = State()
    username = State()
    password = State()
    confirm = State()


class Setup(StatesGroup):
    custom_time = State()


class AddStudent(StatesGroup):
    details = State()
    confirm = State()


class ResetPassword(StatesGroup):
    query = State()


# Chats with a password reset on its way to the backend: a second tap waits for the first.
_resetting = set()


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


def _telegram_language(user):
    code = (getattr(user, 'language_code', None) or '')[:2].lower()
    return code if code in LANGUAGES else DEFAULT


def _username(user):
    return getattr(user, 'username', None) or None


async def _unknown_reply(bot, chat_id, user, who, edit_message_id=None):
    """Who the bot is for, shown to a chat that is neither a counselor nor a student."""
    lang = _telegram_language(user)
    text = t(lang, 'unknown_user', url=escape(who.get('site_url') or ''))
    if not _username(user):
        text += '\n\n' + t(lang, 'unknown_no_username')
    if edit_message_id is not None:
        await _edit(bot, chat_id, edit_message_id, text)
    else:
        await bot.send_message(chat_id, text)


async def _staff_gate(bot, api, chat_id, user, edit_message_id=None):
    """True when this chat may use the counselor login; otherwise it is told who the bot is for."""
    who = await api.whoami(chat_id, _username(user))
    if who.get('kind') in STAFF_KINDS:
        return True
    await _unknown_reply(bot, chat_id, user, who, edit_message_id)
    return False


async def _set_student_menu(bot, chat_id, lang):
    # Students only need /start: hide the counselor commands from this chat's menu.
    commands = [BotCommand(command=name, description=text) for name, text in MENU_STUDENT[lang]]
    with suppress(TelegramAPIError):
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=chat_id))


@router.message(Command('start'), F.text.regexp(STUDENT_START))
async def start_student(message: Message, state: FSMContext, bot, api):
    # Opened from the website's Meetings page: the one-time link of a student connecting their Telegram.
    await state.clear()
    chat_id = message.chat.id
    lang = _telegram_language(message.from_user)
    token = re.match(STUDENT_START, message.text).group(2)
    try:
        result = await api.student_link(chat_id, token, lang)
    except ApiError as exc:
        if exc.code not in ('invalid_token', 'too_many'):
            raise
        if exc.code == 'invalid_token':
            await message.answer(t(lang, 'student_link_invalid', url=escape(exc.extra.get('site_url', ''))))
        else:
            await message.answer(t(lang, 'error'))
        return
    await message.answer(t(lang, 'student_linked', name=escape(result['full_name'])))
    await _set_student_menu(bot, chat_id, lang)


@router.message(Command('start'))
async def start(message: Message, state: FSMContext, bot, api, cache):
    await state.clear()
    chat_id = message.chat.id
    who = await api.whoami(chat_id, _username(message.from_user))
    kind = who.get('kind')
    if kind == 'staff_linked':
        link = await get_link(api, cache, chat_id, fresh=True)
        if link:
            lang = link['language']
            await message.answer(
                t(lang, 'already_linked', name=escape(link['full_name'])), reply_markup=keyboards.already_linked(lang),
            )
            return
    elif kind == 'student':
        lang = _telegram_language(message.from_user)
        await message.answer(t(lang, 'student_connected', name=escape(who.get('name') or '')))
        await _set_student_menu(bot, chat_id, lang)
        return
    elif kind != 'staff_allowed':
        await _unknown_reply(bot, chat_id, message.from_user, who)
        return
    await state.set_state(Login.language)
    await message.answer(LANGUAGE_PROMPT, reply_markup=keyboards.languages())


@router.callback_query(F.data == 'login:again')
async def login_again(callback: CallbackQuery, state: FSMContext, bot, api):
    await callback.answer()
    await state.clear()
    chat_id = callback.message.chat.id
    if not await _staff_gate(bot, api, chat_id, callback.from_user, callback.message.message_id):
        return
    await state.set_state(Login.language)
    await callback.message.edit_text(LANGUAGE_PROMPT, reply_markup=keyboards.languages())


@router.callback_query(Login.language, F.data.startswith('lang:'))
async def pick_language(callback: CallbackQuery, state: FSMContext, bot, api):
    await callback.answer()
    lang = callback.data.split(':', 1)[1]
    if lang not in LANGUAGES:
        return
    # The allowlist may have changed since /start: re-check before asking for any credentials.
    if not await _staff_gate(bot, api, callback.message.chat.id, callback.from_user, callback.message.message_id):
        await state.clear()
        return
    await state.update_data(lang=lang, prompt_id=callback.message.message_id)
    await state.set_state(Login.username)
    await callback.message.edit_text(t(lang, 'welcome'))


@router.message(Login.username, F.text, ~F.text.regexp(COMMAND_PATTERN))
async def got_username(message: Message, state: FSMContext, bot, api):
    username = message.text.strip()
    await _delete(message)
    if not await _staff_gate(bot, api, message.chat.id, message.from_user):
        await state.clear()
        return
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
        card = await api.login(chat_id, username, password, _username(message.from_user))
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
            'telegram_not_allowed': lambda: t(lang, 'staff_not_allowed'),
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
        keyboards.student_detail(lang, item['id'], int(page), sort, flt),
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


@router.message(Command('add'))
async def add_command(message: Message, state: FSMContext, api, cache):
    await state.clear()
    link = await _require_link(message, api, cache, state)
    if link is None:
        return
    lang = link['language']
    # Details may come with the command itself: "/add Ali Valiyev ali@x.com +998...".
    details = parse_student(message.text.partition(' ')[2])
    if is_complete(details):
        await _show_student_card(message, state, api, lang, details)
        return
    await state.set_state(AddStudent.details)
    await state.update_data(lang=lang)
    await message.answer(t(lang, 'add_prompt'))


@router.message(Command('cancel'))
async def cancel_command(message: Message, state: FSMContext, cache):
    lang = await language_of(state, cache, message.chat.id)
    resetting = await state.get_state() == ResetPassword.query.state
    await state.clear()
    await message.answer(t(lang, 'reset_cancelled' if resetting else 'add_cancelled'))


@router.message(AddStudent.details, F.text, ~F.text.regexp(COMMAND_PATTERN))
async def got_student_details(message: Message, state: FSMContext, api, cache):
    lang = await language_of(state, cache, message.chat.id)
    details = parse_student(message.text)
    if not is_complete(details):
        missing = ', '.join(t(lang, f'field_{key}') for key in ('full_name', 'email', 'phone') if not details[key])
        await message.answer(t(lang, 'add_missing', missing=missing))
        return
    await _show_student_card(message, state, api, lang, details)


async def _show_student_card(message, state, api, lang, details):
    await state.clear()
    await state.set_state(AddStudent.confirm)
    try:
        preview = await api.preview_student(message.chat.id, details['full_name'])
    except (ApiError, ApiUnavailable):
        # An older backend (or a hiccup): the card still works, just without the school and name split.
        preview = {}
    school, first, last = (str(preview.get(key) or '') for key in ('school', 'first_name', 'last_name'))
    if school and first:
        text = t(
            lang, 'add_card', first=escape(first), last=escape(last or '-'), email=escape(details['email']),
            phone=escape(details['phone']), school=escape(school),
        )
    else:
        text = t(
            lang, 'add_card_plain', name=escape(details['full_name']), email=escape(details['email']),
            phone=escape(details['phone']),
        )
    await state.update_data(lang=lang, student=details, card_text=text)
    await message.answer(text, reply_markup=keyboards.confirm_student(lang))


@router.callback_query(AddStudent.confirm, F.data == 'add:no')
async def add_cancel(callback: CallbackQuery, state: FSMContext, cache):
    await callback.answer()
    lang = await language_of(state, cache, callback.message.chat.id)
    await state.clear()
    await callback.message.edit_text(t(lang, 'add_cancelled'))


ADD_REFUSALS = {
    'invalid_name': 'add_invalid_name',
    'invalid_email': 'add_invalid_email',
    'invalid_phone': 'add_invalid_phone',
    'student_exists_elsewhere': 'add_exists_elsewhere',
    'seat_limit': 'add_seat_limit',
    'too_many': 'add_too_many',
}


@router.callback_query(AddStudent.confirm, F.data == 'add:yes')
async def add_confirm(callback: CallbackQuery, state: FSMContext, bot, api, cache):
    await callback.answer()
    chat_id = callback.message.chat.id
    data = await state.get_data()
    lang, details = data.get('lang', DEFAULT), data.get('student')
    # Cleared before the call, so a second tap on the same card cannot add the student twice.
    await state.clear()
    if not details:
        return
    await callback.message.edit_text(t(lang, 'add_adding'))
    try:
        result = await api.add_student(chat_id, details['full_name'], details['email'], details['phone'])
    except ApiUnavailable:
        # Nothing was added: give the card and its buttons back so the tap can be repeated.
        await state.set_state(AddStudent.confirm)
        await state.update_data(**data)
        await _edit(bot, chat_id, callback.message.message_id, data['card_text'], keyboards.confirm_student(lang))
        raise
    except ApiError as exc:
        if exc.code == 'student_exists':
            text = t(
                lang, 'add_exists', name=escape(str(exc.extra.get('full_name', ''))),
                username=escape(str(exc.extra.get('username', ''))),
            )
        elif exc.code in ADD_REFUSALS:
            text = t(lang, ADD_REFUSALS[exc.code])
        else:
            raise
        await callback.message.edit_text(text)
        return
    cache.drop_chat(chat_id)
    await callback.message.edit_text(t(
        lang, 'add_done', name=escape(result['full_name']), username=escape(result['username']),
        password=escape(result['temporary_password']), expires=format_expiry(result.get('expires_at')),
        url=escape(result.get('login_url') or ''),
        school_line=t(lang, 'add_done_school', school=escape(result['school'])) if result.get('school') else '',
    ))


@router.message(Command('reset'))
async def reset_command(message: Message, state: FSMContext, bot, api, cache):
    await state.clear()
    link = await _require_link(message, api, cache, state)
    if link is None:
        return
    lang = link['language']
    query = message.text.partition(' ')[2].strip()
    if query:
        await _search_students(message, state, api, lang, query)
        return
    await state.set_state(ResetPassword.query)
    await state.update_data(lang=lang)
    await message.answer(t(lang, 'reset_prompt'))


@router.message(ResetPassword.query, F.text, ~F.text.regexp(COMMAND_PATTERN))
async def got_reset_query(message: Message, state: FSMContext, api, cache):
    lang = await language_of(state, cache, message.chat.id)
    await _search_students(message, state, api, lang, message.text.strip())


async def _search_students(message, state, api, lang, query):
    try:
        result = await api.find_students(message.chat.id, query[:100])
    except ApiError as exc:
        if exc.code != 'invalid_query':
            raise
        await state.set_state(ResetPassword.query)
        await state.update_data(lang=lang)
        await message.answer(t(lang, 'reset_short'))
        return
    students = result.get('students') or []
    if not students:
        await state.set_state(ResetPassword.query)
        await state.update_data(lang=lang)
        await message.answer(t(lang, 'reset_none', query=escape(query[:100])))
        return
    await state.clear()
    # Remembered so the next tap can name the student on its card.
    await state.update_data(lang=lang, matches={str(row['id']): [row['full_name'], row['username']] for row in students})
    if len(students) == 1:
        row = students[0]
        await message.answer(
            _reset_card(lang, row['full_name'], row['username']), reply_markup=keyboards.confirm_reset(lang, row['id']),
        )
        return
    text = t(lang, 'reset_pick') + ('\n' + t(lang, 'reset_more') if result.get('more') else '')
    await message.answer(text, reply_markup=keyboards.pick_student(lang, students))


def _reset_card(lang, name, username):
    return t(lang, 'reset_card', name=escape(name), username=escape(username))


@router.callback_query(F.data == 'rp:x')
async def reset_cancel(callback: CallbackQuery, state: FSMContext, cache):
    await callback.answer()
    lang = await language_of(state, cache, callback.message.chat.id)
    await state.clear()
    await callback.message.edit_text(t(lang, 'reset_cancelled'))


@router.callback_query(F.data.regexp(RESET_PICK))
async def reset_pick(callback: CallbackQuery, state: FSMContext, bot, api, cache):
    chat_id = callback.message.chat.id
    link = await get_link(api, cache, chat_id)
    if link is None:
        await callback.answer()
        await bot.send_message(chat_id, t(DEFAULT, 'not_linked'))
        return
    lang = link['language']
    student_id = RESET_PICK.match(callback.data).group(1)
    found = ((await state.get_data()).get('matches') or {}).get(student_id)
    if found is None:
        # From a student's card in the list: the name comes from the same list.
        data = await _load_digest(api, cache, chat_id)
        item = next((row for row in data['students'] if str(row.get('id')) == student_id), None)
        if item is None:
            await callback.answer(t(lang, 'student_gone'), show_alert=True)
            return
        await callback.answer()
        await bot.send_message(
            chat_id, t(lang, 'reset_card_no_login', name=escape(item['name'])),
            reply_markup=keyboards.confirm_reset(lang, int(student_id)),
        )
        return
    await callback.answer()
    await _edit(
        bot, chat_id, callback.message.message_id, _reset_card(lang, *found),
        keyboards.confirm_reset(lang, int(student_id)),
    )


RESET_REFUSALS = {
    'student_not_found': 'reset_not_found',
    'too_many': 'reset_too_many',
}


@router.callback_query(F.data.regexp(RESET_YES))
async def reset_confirm(callback: CallbackQuery, state: FSMContext, bot, api, cache):
    chat_id = callback.message.chat.id
    if chat_id in _resetting:
        await callback.answer()
        return
    link = await get_link(api, cache, chat_id)
    if link is None:
        await callback.answer()
        await bot.send_message(chat_id, t(DEFAULT, 'not_linked'))
        return
    await callback.answer()
    lang = link['language']
    student_id = int(RESET_YES.match(callback.data).group(1))
    # An old card can come back as an inaccessible message, which has no text.
    card_text = callback.message.html_text if getattr(callback.message, 'text', None) else ''
    # Only a reset in progress is cleared; an /add card waiting in this chat stays usable.
    if await state.get_state() == ResetPassword.query.state:
        await state.clear()
    _resetting.add(chat_id)
    try:
        await _edit(bot, chat_id, callback.message.message_id, t(lang, 'reset_working'))
        try:
            result = await api.reset_password(chat_id, student_id)
        except ApiUnavailable:
            # Usually nothing changed; a timeout may come after the backend made a password nobody saw.
            # Either way the card comes back, and a repeat tap makes a fresh password that is shown.
            if card_text:
                await _edit(
                    bot, chat_id, callback.message.message_id, card_text, keyboards.confirm_reset(lang, student_id),
                )
            raise
        except ApiError as exc:
            if exc.code not in RESET_REFUSALS:
                raise
            await _edit(bot, chat_id, callback.message.message_id, t(lang, RESET_REFUSALS[exc.code]))
            return
    finally:
        _resetting.discard(chat_id)
    cache.drop_chat(chat_id)  # the student list shows the new password status
    await _edit(bot, chat_id, callback.message.message_id, t(
        lang, 'reset_done', name=escape(result['full_name']), username=escape(result['username']),
        password=escape(result['temporary_password']), expires=format_expiry(result.get('expires_at')),
        url=escape(result.get('login_url') or ''),
    ))


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
    # A pasted name + email + phone from a linked counselor is a new student to add.
    details = parse_student(message.text)
    if is_complete(details):
        link = await get_link(api, cache, message.chat.id)
        if link is not None:
            await _show_student_card(message, state, api, link['language'], details)
            return
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
