from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest

from . import keyboards
from .render import render_digest_pages

PAGES_TTL = 1800


async def send_digest(bot, chat_id, data, lang, pages_store, *, edit_message_id=None):
    """Send the first page (with a "show more" button when there are more) and keep the rest for the button."""
    pages = render_digest_pages(data, lang)
    first, rest = pages[0], pages[1:]
    markup = keyboards.show_more(lang, len(rest)) if rest else None
    pages_store.drop_chat(chat_id)
    if rest:
        pages_store.set(('pages', chat_id), rest, PAGES_TTL)
    if edit_message_id is not None:
        with suppress(TelegramBadRequest):
            await bot.edit_message_text(first, chat_id=chat_id, message_id=edit_message_id, reply_markup=markup)
            return
    await bot.send_message(chat_id, first, reply_markup=markup)


async def send_next_page(bot, chat_id, lang, pages_store):
    """Returns False when the stored pages are gone."""
    rest = pages_store.get(('pages', chat_id))
    if not rest:
        return False
    page, rest = rest[0], rest[1:]
    markup = None
    if rest:
        pages_store.set(('pages', chat_id), rest, PAGES_TTL)
        markup = keyboards.show_more(lang, len(rest))
    else:
        pages_store.drop_chat(chat_id)
    await bot.send_message(chat_id, page, reply_markup=markup)
    return True
