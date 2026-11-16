from bot.api import ApiError
from bot.render import MAX_MEETING_LINES, render_meetings


def meeting(day, time, name, status='approved', waiting=None, minutes=30):
    return {'id': 1, 'name': name, 'date': day, 'time': time, 'duration_minutes': minutes, 'status': status,
            'waiting_for': waiting, 'topic': 'x'}


STAFF = {
    'role': 'staff', 'timezone': 'Asia/Tashkent',
    'meetings': [
        meeting('2026-11-18', '10:00', 'Ali <Valiyev>'),
        meeting('2026-11-18', '11:00', 'Sara Nazarova', 'pending', 'staff', 45),
        meeting('2026-11-19', '09:30', 'Bobur Aliev', 'pending', 'student'),
    ],
    'counts': {'booked': 3, 'waiting_for_you': 1, 'waiting_for_student': 1, 'cancelled_week': 2},
    'free_slots': 12,
    'booking_url': 'https://app.example.com/meetings?book=7',
    'settings': {'duration_minutes': 30, 'min_notice_hours': 6, 'window_mode': 'rolling', 'window_days': 30,
                 'window_start': None, 'window_end': None},
}


async def test_meetings_command_shows_counts_days_status_and_settings(h):
    h.api.linked = True
    h.api.meetings_data = STAFF
    await h.say('/meetings')
    assert h.api.names('meetings') == [{'chat_id': 1}]
    text = h.session.texts()[-1]
    assert 'Booked: 3 · waiting: 2 · cancelled in 7 days: 2 · free slots: 12' in text
    assert '<b>18 Nov</b>' in text and '<b>19 Nov</b>' in text
    assert '✅ 10:00 · 30 min · Ali &lt;Valiyev&gt;' in text
    assert '⏳ 11:00 · 45 min · Sara Nazarova (waiting for you)' in text
    assert '(waiting for student)' in text
    assert 'Settings: 30 min · 6 h notice · next 30 days' in text
    assert 'Your booking link: https://app.example.com/meetings?book=7' in text


async def test_meetings_in_russian_and_range_settings(h):
    h.api.linked = True
    h.api.link = {**h.api.link, 'language': 'ru'}
    h.api.meetings_data = {**STAFF, 'settings': {**STAFF['settings'], 'window_mode': 'range',
                                                  'window_start': '2026-11-20', 'window_end': '2026-12-05'}}
    await h.say('/meetings')
    text = h.session.texts()[-1]
    assert 'Встречи' in text and 'ждёт вашего ответа' in text and '20 ноя – 5 дек' in text


def test_a_long_list_is_cut_to_the_line_limit_with_a_count_of_the_rest():
    many = {**STAFF, 'meetings': [meeting(f'2026-12-{day:02d}', f'{hour}:00', f'Student {day}-{hour}')
                                  for day in range(1, 20) for hour in (10, 11)]}
    text = render_meetings(many, 'en')
    assert len(text.splitlines()) <= MAX_MEETING_LINES
    assert any(line.startswith('… and') for line in text.splitlines())


async def test_no_meetings_says_so(h):
    h.api.linked = True
    await h.say('/meetings')
    assert 'No upcoming meetings.' in h.session.texts()[-1]


async def test_a_student_chat_gets_its_own_list_in_the_telegram_language(h):
    h.language_code = 'en'
    h.api.meetings_data = {'role': 'student', 'timezone': 'Asia/Tashkent', 'meetings': [
        meeting('2026-11-18', '10:00', 'Dilnoza Karimova', 'pending', 'staff')]}
    await h.say('/meetings')
    text = h.session.texts()[-1]
    assert 'Dilnoza Karimova' in text and 'waiting for confirmation' in text and 'Booked:' not in text


async def test_an_unlinked_chat_is_told_so(h):
    h.language_code = 'en'
    h.api.errors['meetings'] = ApiError(404, 'not_linked')
    await h.say('/meetings')
    assert h.session.texts()


async def test_help_and_menu_list_meetings(h):
    from bot.i18n import MENU, t
    for lang in ('uz', 'ru', 'en'):
        assert '/meetings' in t(lang, 'help')
        assert 'meetings' in [name for name, _ in MENU[lang]]


def test_the_telegram_username_is_shown_next_to_the_name():
    data = {**STAFF, 'meetings': [{**meeting('2026-11-18', '10:00', 'Ali', 'pending', 'staff'), 'telegram_username': 'ali_v'}]}
    assert '⏳ 10:00 · 30 min · Ali · @ali_v (waiting for you)' in render_meetings(data, 'en')
