from contextlib import suppress

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from . import keyboards
from .render import SORT_ATTENTION, FILTER_ALL, render_list


def list_message(data, lang, page=0, sort=SORT_ATTENTION, flt=FILTER_ALL):
    text, page, pages, numbered = render_list(data, lang, page, sort, flt)
    markup = keyboards.list_markup(lang, numbered, page, pages, sort, flt) if data['total_students'] else None
    return text, markup


async def send_digest(bot, chat_id, data, lang, *, sort=SORT_ATTENTION, edit_message_id=None):
    """The summary and the first page of the list; the buttons turn pages by re-reading the data."""
    text, markup = list_message(data, lang, 0, sort)
    if edit_message_id is not None:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=markup)
            return
        except TelegramBadRequest as exc:
            if 'not modified' in str(exc):
                return
            with suppress(TelegramAPIError):
                await bot.delete_message(chat_id, edit_message_id)
    await bot.send_message(chat_id, text, reply_markup=markup)
