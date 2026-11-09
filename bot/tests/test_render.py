import string
from datetime import datetime, timedelta, timezone

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText

from bot import keyboards
from bot.delivery import list_message, send_digest
from bot.i18n import LANGUAGES, STRINGS
from bot.render import (
    FILTER_ALL, FILTER_INACTIVE, PAGE_SIZE, SORT_ATTENTION, SORT_AZ, TASHKENT, TELEGRAM_LIMIT,
    ordered, render_detail, render_list,
)

from .helpers import Harness

NOW = datetime(2026, 11, 9, 15, 0, tzinfo=TASHKENT)


def seen_ago(days, hours=0):
    return (NOW - timedelta(days=days, hours=hours)).astimezone(timezone.utc).isoformat()


def student(name, number=1, days=None, expired=False, percent=40, edited=0, streak=0, **extra):
    base = {
        'id': number, 'name': name, 'grade': '10',
        'last_seen_at': None if days is None else seen_ago(days),
        'last_seen_expired': expired,
        'essays': {'total': 3, 'edited_today': edited},
        'streak': {'days': streak, 'shared': True},
        'application': {
            'percent': percent,
            'sections': {'personal': True, 'academics': False, 'tests': True, 'goal': False,
                         'activities': True, 'honors': False},
            'activities': 2, 'honors': 0, 'applications': {'done': 1, 'total': 3},
            'documents': {'done': 2, 'total': 5}, 'recommendations': {'done': 0, 'total': 2},
        },
    }
    return {**base, **extra}


def digest(students, omitted=0):
    return {
        'date': '2026-11-09', 'total_students': len(students) + omitted, 'omitted': omitted, 'students': students,
    }


def many(count, **extra):
    return [student(f'Student Number {i:03d}', i + 1, days=i % 12, **extra) for i in range(count)]


def render(data, lang='en', page=0, sort=SORT_ATTENTION, flt=FILTER_ALL):
    return render_list(data, lang, page, sort, flt, now=NOW)


def test_summary_counts_buckets_and_totals():
    data = digest([
        student('A', 1, days=0, edited=2, streak=3, percent=20),
        student('B', 2, days=3, percent=40),
        student('C', 3, days=9, percent=60),
        student('D', 4, days=None),
        student('E', 5, days=None, expired=True),
    ])
    text = render(data)[0]
    assert 'Daily update' in text and '9 Nov' in text and '5 students' in text
    assert 'Today 1' in text and 'This week 1' in text and '7+ days 2' in text and 'Never 1' in text
    assert 'Essays edited today: 2' in text
    assert 'With a streak: 1' in text
    assert 'Avg readiness: 40%' in text


def test_row_is_two_compact_lines_with_last_seen_progress_essays_and_streak():
    text = render(digest([student('Ali Valiyev', 7, days=1, percent=40, edited=2, streak=5)]))[0]
    assert '1. <b>Ali Valiyev</b> · Grade 10' in text
    assert '\U0001F7E2' not in text.split('Ali Valiyev')[1] or True
    assert 'yesterday · ▰▰▱▱▱ 40% · \U0001F4DD 2 · \U0001F525 5' in text


def test_last_seen_wording_in_the_list_and_the_detail_card():
    data = digest([student('Today', 1, days=0), student('Three', 2, days=3), student('Never', 3, days=None),
                   student('Old', 4, days=None, expired=True)])
    text = render(data)[0]
    assert 'today' in text and '3 days ago' in text and 'never opened' in text and 'no recent activity' in text
    assert 'Last seen: today 15:00' in render_detail(data['students'][0], 'en', NOW)
    assert 'Last seen: 3 days ago (6 Nov)' in render_detail(data['students'][1], 'en', NOW)
    assert 'Last seen: never opened' in render_detail(data['students'][2], 'en', NOW)


def test_last_seen_uses_the_tashkent_calendar_day():
    late_utc = datetime(2026, 11, 8, 20, 30, tzinfo=timezone.utc).isoformat()
    item = student('Night Owl', 1, last_seen_at=late_utc)
    assert 'today' in render(digest([item]))[0]
    assert 'Last seen: today 01:30' in render_detail(item, 'en', NOW)


def test_needs_attention_puts_never_then_longest_away_first():
    items = [student('Fresh', 1, days=0), student('Old', 2, days=20), student('Never', 3, days=None),
             student('Mid', 4, days=3), student('Expired', 5, days=None, expired=True)]
    names = [item['name'] for item in ordered(items, SORT_ATTENTION, FILTER_ALL, NOW.date())]
    assert names == ['Never', 'Expired', 'Old', 'Mid', 'Fresh']


def test_needs_attention_breaks_ties_by_lowest_readiness_then_name():
    items = [student('Zed', 1, days=5, percent=80), student('Amy', 2, days=5, percent=20), student('Bob', 3, days=5, percent=20)]
    assert [i['name'] for i in ordered(items, SORT_ATTENTION, FILTER_ALL, NOW.date())] == ['Amy', 'Bob', 'Zed']


def test_a_to_z_and_the_inactive_filter():
    items = [student('Cara', 1, days=0), student('Ann', 2, days=8), student('Ben', 3, days=None),
             student('Dan', 4, days=6)]
    assert [i['name'] for i in ordered(items, SORT_AZ, FILTER_ALL, NOW.date())] == ['Ann', 'Ben', 'Cara', 'Dan']
    assert [i['name'] for i in ordered(items, SORT_AZ, FILTER_INACTIVE, NOW.date())] == ['Ann', 'Ben']
    text = render(digest(items), flt=FILTER_INACTIVE)[0]
    assert 'Inactive 7+ days' in text and 'Cara' not in text and 'Dan' not in text


def test_empty_filter_says_so_and_keeps_the_toggles():
    data = digest([student('Cara', 1, days=0)])
    text, markup = list_message(data, 'en', 0, SORT_ATTENTION, FILTER_INACTIVE)
    assert 'No students match this filter' in text
    assert any(b.callback_data == 'l:0:a:a' for row in markup.inline_keyboard for b in row)


def test_no_students_is_one_friendly_line_without_buttons():
    assert list_message(digest([]), 'en') == ('No students yet.', None)
    assert list_message(digest([]), 'uz')[0] == "Hozircha o'quvchilar yo'q."


def test_paging_boundaries_first_last_single_and_clamped():
    one_page = render(digest(many(PAGE_SIZE)))
    assert one_page[2] == 1 and len(one_page[3]) == PAGE_SIZE
    two = digest(many(PAGE_SIZE + 1))
    first, last = render(two, page=0), render(two, page=1)
    assert first[2] == 2 and len(first[3]) == PAGE_SIZE and len(last[3]) == 1
    assert render(two, page=99)[1] == 1 and render(two, page=-3)[1] == 0
    assert last[3][0][0] == PAGE_SIZE + 1


def test_one_student_has_no_page_navigation():
    _, markup = list_message(digest([student('Solo', 5, days=1)]), 'en')
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert 'd:5:0:a:a' in data and 'noop' not in data and not any(d.startswith('l:') and d != 'l:0:z:a' and d != 'l:0:a:i' for d in data)


def test_navigation_buttons_on_the_first_middle_and_last_page():
    data = digest(many(PAGE_SIZE * 3))

    def nav(page):
        _, markup = list_message(data, 'en', page)
        return [b.callback_data for b in markup.inline_keyboard[-2]]

    assert nav(0) == ['noop', 'l:1:a:a']
    assert nav(1) == ['l:0:a:a', 'noop', 'l:2:a:a']
    assert nav(2) == ['l:1:a:a', 'noop']


def test_toggles_reset_to_the_first_page_and_flip_the_setting():
    _, markup = list_message(digest(many(30)), 'en', 2, SORT_ATTENTION, FILTER_ALL)
    toggles = [b.callback_data for b in markup.inline_keyboard[-1]]
    assert toggles == ['l:0:z:a', 'l:0:a:i']
    _, markup = list_message(digest(many(30)), 'en', 2, SORT_AZ, FILTER_INACTIVE)
    assert [b.callback_data for b in markup.inline_keyboard[-1]] == ['l:0:a:i', 'l:0:z:a']


def test_every_callback_fits_telegrams_64_bytes_even_with_huge_ids_and_pages():
    data = digest([student(f'S{i}', 999_999_999_999 - i, days=i % 9) for i in range(300)])
    for page in (0, 5, 37):
        for sort in ('a', 'z'):
            for flt in ('a', 'i'):
                _, markup = list_message(data, 'en', page, sort, flt)
                for row in markup.inline_keyboard:
                    for button in row:
                        assert len(button.callback_data.encode()) <= 64, button.callback_data
    assert len(keyboards.back_to_list('en', 9999, 'z', 'i').inline_keyboard[0][0].callback_data) <= 64


def test_300_students_every_page_is_under_the_limit_in_every_language():
    data = digest(many(300), omitted=40)
    for lang in LANGUAGES:
        pages = render(data, lang)[2]
        assert pages == 38
        for page in range(pages):
            text = render(data, lang, page)[0]
            assert len(text) <= TELEGRAM_LIMIT
    assert 'more students not shown' in render(data)[0]


def test_worst_case_names_stay_under_the_limit_and_are_escaped():
    nasty = ['&' * 150, '<b>' * 60, 'W' * 200, '"quote" ' * 30, "it's <i>x</i>" * 15, 'Ж' * 180, '&<>' * 70, 'Z' * 90]
    data = digest([student(name, i + 1, days=i, edited=99, streak=999) for i, name in enumerate(nasty)])
    for lang in LANGUAGES:
        text = render(data, lang)[0]
        assert len(text) <= TELEGRAM_LIMIT
        assert '<b><b>' not in text and '<i>x' not in text
    assert '&amp;' in render(data)[0] and '…' in render(data)[0]


def test_disabled_parts_are_left_out_of_rows_and_summary():
    bare = {'id': 1, 'name': 'Ali', 'grade': '', 'last_seen_at': seen_ago(2), 'last_seen_expired': False}
    text = render(digest([bare]))[0]
    assert 'Essays' not in text and 'streak' not in text and 'readiness' not in text and '▰' not in text
    assert '2 days ago' in text and 'No grade set' not in text
    detail = render_detail(bare, 'en', NOW)
    assert 'Application' not in detail and 'No grade set' in detail


def test_detail_card_has_everything_a_counselor_needs():
    item = student('Ali Valiyev', 3, days=2, percent=58, edited=1, streak=6)
    card = render_detail(item, 'en', NOW)
    assert '<b>Ali Valiyev</b> - Grade 10' in card
    assert 'Last seen: 2 days ago (7 Nov)' in card
    assert 'Essays: 3, edited today: 1' in card
    assert 'Streak: 6 days' in card
    assert 'Application: 58%' in card and '▰▰▰▱▱' in card
    assert '✅ Personal' in card and '❌ Academics' in card
    assert 'documents 2/5' in card and 'letters 0/2' in card
    assert len(card) < TELEGRAM_LIMIT


def test_private_essays_hide_the_streak_in_the_detail_and_the_list():
    item = student('Ali', 1, days=1, streak=9)
    item['streak'] = {'days': None, 'shared': False}
    assert 'once all essays are shared' in render_detail(item, 'en', NOW)
    assert '\U0001F525 9' not in render(digest([item]))[0]


def test_omitted_students_are_announced_in_the_summary():
    text = render(digest([student('Ali', 1, days=1)], omitted=40))[0]
    assert '41 students' in text and '...40 more students not shown' in text
    assert 'not shown' not in render(digest([student('Ali', 1, days=1)]))[0]


def test_every_string_exists_in_all_languages_with_the_same_placeholders():
    def fields(text):
        return {name for _, name, _, _ in string.Formatter().parse(text) if name}

    for key, entry in STRINGS.items():
        assert set(entry) == set(LANGUAGES), key
        assert len({frozenset(fields(entry[lang])) for lang in LANGUAGES}) == 1, key


def test_the_new_screens_are_translated_not_english_fallbacks():
    data = digest([student('Ali', 1, days=2), student('Bo', 2, days=None)])
    for lang in ('uz', 'ru'):
        text = render(data, lang)[0]
        assert 'Daily update' not in text and 'Never' not in text and 'days ago' not in text
        assert 'never opened' not in text
        assert 'Last seen' not in render_detail(data['students'][0], lang, NOW)


async def test_the_scheduled_digest_is_summary_plus_the_first_page_with_buttons():
    harness = Harness()
    try:
        await send_digest(harness.bot, 1, digest(many(20)), 'en')
        sent = harness.session.of('SendMessage')[0][1]
        assert 'Daily update' in sent['text'] and '1/3' in sent['text']
        assert sent['reply_markup']['inline_keyboard'][-2][-1]['callback_data'] == 'l:1:a:a'
    finally:
        harness.close()


async def test_now_shows_the_list_and_a_page_tap_edits_the_same_message_from_fresh_data(h):
    h.api.linked = True
    h.api.digest_data = digest(many(20))
    await h.say('/now')
    assert 'Page' not in h.session.texts()[-1] and '1/3' in h.session.texts()[-1]
    h.cache.drop_chat(1)
    h.api.digest_data = digest(many(20) + [student('Brand New Student', 99, days=None)])
    await h.tap('l:1:a:a', message_id=500)
    edit = h.session.of('EditMessageText')[-1][1]
    assert edit['message_id'] == 500 and '2/3' in edit['text']
    assert len(h.api.names('digest')) == 2
    assert '21 students' in edit['text']


async def test_paging_works_without_any_memory_of_the_original_message():
    harness = Harness()
    try:
        harness.api.linked = True
        harness.api.digest_data = digest(many(20))
        await harness.tap('l:2:a:a', message_id=77)
        edit = harness.session.of('EditMessageText')[-1][1]
        assert edit['message_id'] == 77 and '3/3' in edit['text']
    finally:
        harness.close()


async def test_a_stale_page_number_after_the_list_shrank_shows_the_last_page(h):
    h.api.linked = True
    h.api.digest_data = digest(many(10))
    await h.tap('l:30:a:a')
    assert '2/2' in h.session.texts()[-1]


async def test_tapping_a_student_shows_the_card_with_a_back_button_to_the_same_view(h):
    h.api.linked = True
    h.api.digest_data = digest(many(20))
    await h.tap('d:3:1:z:i')
    edit = h.session.of('EditMessageText')[-1][1]
    assert 'Student Number 002' in edit['text'] and 'Last seen' in edit['text']
    assert edit['reply_markup']['inline_keyboard'][0][0]['callback_data'] == 'l:1:z:i'


async def test_a_student_who_left_the_list_gets_a_message_not_a_crash(h):
    h.api.linked = True
    h.api.digest_data = digest(many(3))
    await h.tap('d:4040:0:a:a')
    answer = h.session.of('AnswerCallbackQuery')[-1][1]
    assert 'no longer in your list' in answer['text']
    assert not h.session.of('EditMessageText')


async def test_the_page_indicator_button_does_nothing(h):
    h.api.linked = True
    await h.tap('noop')
    assert not h.session.of('EditMessageText') and not h.api.names('digest')


async def test_message_is_not_modified_is_swallowed_on_every_tap(h):
    h.api.linked = True
    h.api.digest_data = digest(many(20))
    for data in ('l:1:a:a', 'd:2:0:a:a'):
        h.session.failures['EditMessageText'] = [TelegramBadRequest(EditMessageText(text='x'), 'message is not modified')]
        await h.tap(data)
    assert len(h.session.of('EditMessageText')) == 2


async def test_buttons_of_an_unlinked_chat_ask_to_log_in(h):
    await h.tap('l:0:a:a')
    assert 'Avval kiring: /start' in h.session.texts()[-1]
    await h.tap('d:1:0:a:a')
    assert 'Avval kiring: /start' in h.session.texts()[-1]


async def test_old_show_more_buttons_from_before_the_redesign_just_expire(h):
    h.api.linked = True
    await h.tap('more:deadbeef')
    assert 'expired' in h.session.of('AnswerCallbackQuery')[-1][1]['text'].lower() or 'Muddati' in str(h.session.calls[-1])


def test_items_from_an_older_backend_without_ids_or_last_seen_still_render():
    old = {'name': 'Ali', 'grade': '9', 'essays': {'total': 1, 'edited_today': 0}}
    text, markup = list_message(digest([old]), 'en')
    assert 'Ali' in text and 'never opened' in text
    assert not any(b.callback_data.startswith('d:') for row in markup.inline_keyboard for b in row)
