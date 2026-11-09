from bot.delivery import send_digest, send_next_page
from bot.i18n import LANGUAGES, STRINGS
from bot.render import TELEGRAM_LIMIT, render_digest_pages, render_students
from bot.cache import TtlCache

from .helpers import Harness


def student(name, **extra):
    base = {
        'name': name, 'grade': '10',
        'essays': {'total': 3, 'edited_today': 1, 'words_today': None},
        'streak': {'days': None},
        'application': {
            'percent': 58, 'sections': {'personal': True, 'academics': False, 'tests': True, 'goal': False,
                                        'activities': True, 'honors': False},
            'activities': 2, 'honors': 0, 'applications': {'done': 1, 'total': 3},
            'documents': {'done': 2, 'total': 5}, 'recommendations': {'done': 0, 'total': 2},
        },
    }
    return {**base, **extra}


def digest(students, streak_available=False):
    return {'date': '2026-11-08', 'total_students': len(students), 'streak_available': streak_available,
            'students': students}


def test_one_scannable_block_per_student():
    page = render_digest_pages(digest([student('Ali Valiyev')]), 'en')[0]
    assert 'Daily update' in page and '8 Nov' in page and '1 students' in page
    assert '<b>Ali Valiyev</b> - Grade 10' in page
    assert 'Essays: 3, edited today: 1' in page
    assert 'Streak: not available yet' in page
    assert 'Application: 58%' in page
    assert '✅ Personal' in page and '❌ Academics' in page
    assert 'documents 2/5' in page


def test_streak_days_and_words_are_shown_when_available():
    item = student('Ali Valiyev', streak={'days': 6}, essays={'total': 1, 'edited_today': 1, 'words_today': 250})
    page = render_digest_pages(digest([item], streak_available=True), 'en')[0]
    assert '\U0001F525 Streak: 6 days' in page
    assert 'words typed today: 250' in page


def test_zero_streak_and_disabled_parts():
    item = student('Ali', streak={'days': 0})
    assert 'No streak' in render_digest_pages(digest([item], True), 'en')[0]
    bare = {'name': 'Ali', 'grade': ''}
    page = render_digest_pages(digest([bare]), 'en')[0]
    assert 'Essays' not in page and 'Streak' not in page and 'Application' not in page
    assert 'No grade set' in page


def test_names_are_escaped():
    page = render_digest_pages(digest([student('<b>Evil</b> & Co')]), 'en')[0]
    assert '<b>&lt;b&gt;Evil&lt;/b&gt; &amp; Co</b>' in page


def test_long_lists_split_into_pages_under_the_telegram_limit():
    students = [student(f'Student Number {i} ' + 'X' * 40) for i in range(120)]
    for lang in LANGUAGES:
        pages = render_digest_pages(digest(students), lang)
        assert len(pages) > 1
        assert all(len(page) <= TELEGRAM_LIMIT for page in pages)
        assert sum(page.count('Student Number') for page in pages) == 120


def test_empty_digest_is_the_friendly_line():
    assert render_digest_pages(digest([]), 'en') == ['No students yet.']
    assert render_students({'total': 0, 'groups': []}, 'uz') == ["Hozircha o'quvchilar yo'q."]


def test_every_string_exists_in_all_languages_with_the_same_placeholders():
    import string

    def fields(text):
        return {name for _, name, _, _ in string.Formatter().parse(text) if name}

    for key, entry in STRINGS.items():
        assert set(entry) == set(LANGUAGES), key
        assert len({frozenset(fields(entry[lang])) for lang in LANGUAGES}) == 1, key


async def test_show_more_sends_the_remaining_pages_one_by_one():
    harness = Harness()
    try:
        students = [student(f'Student Number {i} ' + 'X' * 40) for i in range(120)]
        pages = TtlCache(1800)
        await send_digest(harness.bot, 1, digest(students), 'en', pages)
        first = harness.session.of('SendMessage')[0][1]
        assert first['reply_markup']['inline_keyboard'][0][0]['callback_data'] == 'more'
        total = len(render_digest_pages(digest(students), 'en'))
        sent = 1
        while await send_next_page(harness.bot, 1, 'en', pages):
            sent += 1
        assert sent == total
        assert not await send_next_page(harness.bot, 1, 'en', pages)
        assert harness.session.of('SendMessage')[-1][1]['reply_markup'] is None
    finally:
        harness.close()


async def test_show_more_button_in_the_chat(h):
    h.api.linked = True
    h.api.digest_data = digest([student(f'Student Number {i} ' + 'X' * 40) for i in range(120)])
    await h.say('/now')
    assert h.session.of('EditMessageText')[-1][1]['reply_markup'] is not None
    await h.tap('more')
    assert h.session.of('EditMessageReplyMarkup')
    assert 'Student Number' in h.session.texts()[-1]
    h.pages.drop_chat(1)
    await h.tap('more')
    assert 'expired' in h.session.texts()[-1]


def test_a_long_student_list_is_split_into_pages_under_the_telegram_limit():
    names = [f'Student Number {i} ' + 'Y' * 40 for i in range(300)]
    data = {'total': 300, 'groups': [{'grade': '10', 'count': 300, 'students': names}]}
    pages = render_students(data, 'en')
    assert len(pages) > 1
    assert all(len(page) <= TELEGRAM_LIMIT for page in pages)
    assert sum(page.count('Student Number') for page in pages) == 300


def test_a_student_without_a_shared_essay_says_so_instead_of_unavailable():
    item = student('Ali', streak={'days': None, 'shared': False})
    page = render_digest_pages(digest([item], True), 'en')[0]
    assert 'no essay shared' in page and 'not available' not in page
