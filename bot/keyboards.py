from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .i18n import LANGUAGE_NAMES, LANGUAGES, t

TIME_CHOICES = [f'{hour:02d}:00' for hour in range(7, 22)]
PARTS = ('essays', 'streak', 'application')


def _markup(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _button(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def languages(prefix='lang'):
    return _markup([[_button(LANGUAGE_NAMES[code], f'{prefix}:{code}') for code in LANGUAGES]])


def confirm_card(lang):
    return _markup([[_button(t(lang, 'confirm'), 'login:confirm'), _button(t(lang, 'cancel'), 'login:cancel')]])


def already_linked(lang):
    return _markup([[_button(t(lang, 'other_account'), 'login:again')]])


def time_picker(lang):
    rows = [
        [_button(value, f'time:{value}') for value in TIME_CHOICES[i:i + 4]]
        for i in range(0, len(TIME_CHOICES), 4)
    ]
    rows.append([_button(t(lang, 'custom_time'), 'time:custom'), _button(t(lang, 'skip_time'), 'time:off')])
    return _markup(rows)


def settings_panel(lang, prefs, notify_time):
    rows = [
        [_button(('✅ ' if prefs.get(part) else '⬜ ') + t(lang, f'part_{part}'), f'part:{part}')]
        for part in PARTS
    ]
    rows.append([
        _button('⏰ ' + t(lang, 'button_time', time=notify_time or t(lang, 'time_off')), 'set:time'),
        _button('\U0001F310 ' + t(lang, 'button_language'), 'set:lang'),
    ])
    rows.append([_button(t(lang, 'done'), 'set:done')])
    return _markup(rows)


def show_more(lang, left, token):
    return _markup([[_button(t(lang, 'show_more', left=left), f'more:{token}')]])
