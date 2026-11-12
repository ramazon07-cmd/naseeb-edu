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


def confirm_student(lang):
    return _markup([[_button(t(lang, 'add_yes'), 'add:yes'), _button(t(lang, 'add_no'), 'add:no')]])


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


def list_markup(lang, numbered, page, pages, sort, flt):
    """Student number buttons, prev/next, and the sort and filter toggles.

    Every callback carries the whole view (page, sort, filter), so a tap re-renders from fresh data and
    nothing has to be remembered between messages.
    """
    view = f'{page}:{sort}:{flt}'
    rows = [
        [_button(str(number), f'd:{student_id}:{view}') for number, student_id in numbered[i:i + 4]]
        for i in range(0, len(numbered), 4)
    ]
    nav = []
    if page > 0:
        nav.append(_button('⬅', f'l:{page - 1}:{sort}:{flt}'))
    if pages > 1:
        nav.append(_button(f'{page + 1}/{pages}', 'noop'))
    if page < pages - 1:
        nav.append(_button('➡', f'l:{page + 1}:{sort}:{flt}'))
    if nav:
        rows.append(nav)
    other_sort = 'z' if sort == 'a' else 'a'
    other_filter = 'i' if flt == 'a' else 'a'
    rows.append([
        _button(t(lang, 'btn_sort_attention' if sort == 'z' else 'btn_sort_az'), f'l:0:{other_sort}:{flt}'),
        _button(t(lang, 'btn_filter_all' if flt == 'i' else 'btn_filter_inactive'), f'l:0:{sort}:{other_filter}'),
    ])
    return _markup(rows)


def back_to_list(lang, page, sort, flt):
    return _markup([[_button(t(lang, 'btn_back'), f'l:{page}:{sort}:{flt}')]])


def student_detail(lang, student_id, page, sort, flt):
    return _markup([
        [_button(t(lang, 'btn_new_password'), f'rp:{student_id}')],
        [_button(t(lang, 'btn_back'), f'l:{page}:{sort}:{flt}')],
    ])


def pick_student(lang, students):
    rows = [[_button(f"{row['full_name']} ({row['username']})"[:60], f"rp:{row['id']}")] for row in students]
    rows.append([_button(t(lang, 'add_no'), 'rp:x')])
    return _markup(rows)


def confirm_reset(lang, student_id):
    return _markup([[_button(t(lang, 'reset_yes'), f'rpy:{student_id}'), _button(t(lang, 'add_no'), 'rp:x')]])


def new_code(lang):
    return _markup([[_button(t(lang, 'btn_new_code'), f'scode:{lang}')]])
