from bot.api import ApiError, ApiUnavailable
from bot.students import format_expiry, is_complete, parse_student

SOFIYA = 'Saydazimova Sofiya \n@saidazimova.safiiya@gmail.com\n+998 91 007 68 25'


def buttons(call):
    return [b['callback_data'] for row in call[1]['reply_markup']['inline_keyboard'] for b in row]


def test_parser_reads_the_shapes_counselors_send():
    assert parse_student(SOFIYA) == {
        'full_name': 'Saydazimova Sofiya', 'email': 'saidazimova.safiiya@gmail.com', 'phone': '+998 91 007 68 25',
    }
    assert parse_student('Full Name: Abdukarimov Muhsinbek\nEmail: mok.mar76@gmail.com\nPhone Number: +998941011558') == {
        'full_name': 'Abdukarimov Muhsinbek', 'email': 'mok.mar76@gmail.com', 'phone': '+998941011558',
    }
    assert parse_student('1. Ism: Karimova Dilnoza\n2. Telefon: (90) 123 45 67\n3. Pochta: dil@mail.ru') == {
        'full_name': 'Karimova Dilnoza', 'email': 'dil@mail.ru', 'phone': '(90) 123 45 67',
    }
    assert parse_student("O'ktamov Jobir, jobir@gmail.com, +998 (91) 104-70-06")['full_name'] == "O'ktamov Jobir"


def test_parser_does_not_mistake_a_password_or_chat_for_a_student():
    assert not is_complete(parse_student('S3cret-Passw0rd!'))
    assert not is_complete(parse_student('hello how are you'))
    assert not is_complete(parse_student('ali@x.uz +998901234567'))  # no name


def test_expiry_is_shown_in_tashkent_time():
    assert format_expiry('2026-11-13T16:14:20.123+00:00') == '13.11.2026 21:14'
    assert format_expiry(None) == '' and format_expiry('garbage') == ''


async def test_add_command_asks_then_confirms_then_creates(h):
    await h.log_in()
    await h.say('/add')
    assert 'one message' in h.session.texts()[-1]
    await h.say(SOFIYA)
    card = h.session.of('SendMessage')[-1]
    assert 'Saydazimova Sofiya' in card[1]['text'] and 'saidazimova.safiiya@gmail.com' in card[1]['text']
    assert buttons(card) == ['add:yes', 'add:no']
    assert h.api.names('add_student') == []

    await h.tap('add:yes')
    assert h.api.names('add_student') == [{
        'chat_id': 1, 'full_name': 'Saydazimova Sofiya', 'email': 'saidazimova.safiiya@gmail.com',
        'phone': '+998 91 007 68 25',
    }]
    done = h.session.texts()[-1]
    assert 'saydazimova-sofiya' in done and 'Tmp-Pass-42' in done and '13.11.2026 21:14' in done
    assert 'https://naseeb.example/login' in done


async def test_pasting_details_without_a_command_offers_the_card(h):
    await h.log_in()
    await h.say(SOFIYA, message_id=88)
    assert buttons(h.session.of('SendMessage')[-1]) == ['add:yes', 'add:no']
    # The pasted details are not deleted like stray text.
    assert 88 not in [data['message_id'] for kind, data in h.session.calls if kind == 'DeleteMessage']


async def test_details_can_follow_the_command(h):
    await h.log_in()
    await h.say('/add Ali Valiyev ali@x.uz +998 90 123 45 67')
    assert buttons(h.session.of('SendMessage')[-1]) == ['add:yes', 'add:no']


async def test_a_second_tap_does_not_add_twice(h):
    await h.log_in()
    await h.say(SOFIYA)
    await h.tap('add:yes')
    await h.tap('add:yes')
    assert len(h.api.names('add_student')) == 1


async def test_cancel_adds_nothing(h):
    await h.log_in()
    await h.say(SOFIYA)
    await h.tap('add:no')
    assert h.api.names('add_student') == []
    assert 'Nothing was added' in h.session.texts()[-1]


async def test_missing_parts_are_named(h):
    await h.log_in()
    await h.say('/add')
    await h.say('Ali Valiyev ali@x.uz')
    assert 'Missing: phone' in h.session.texts()[-1]
    assert h.api.names('add_student') == []


async def test_unlinked_chat_cannot_add(h):
    await h.say('/add')
    assert h.api.names('add_student') == []
    await h.say(SOFIYA, message_id=91)
    # Not linked: treated as stray text, so it is deleted and nothing is offered.
    assert 91 in [data['message_id'] for kind, data in h.session.calls if kind == 'DeleteMessage']
    assert all('add:yes' not in repr(call) for call in h.session.of('SendMessage'))


async def test_existing_student_is_reported(h):
    await h.log_in()
    h.api.errors['add_student'] = ApiError(409, 'student_exists', full_name='Saydazimova Sofiya', username='sofiya-1')
    await h.say(SOFIYA)
    await h.tap('add:yes')
    assert 'already exists' in h.session.texts()[-1] and 'sofiya-1' in h.session.texts()[-1]


async def test_seat_limit_is_explained(h):
    await h.log_in()
    h.api.errors['add_student'] = ApiError(403, 'seat_limit')
    await h.say(SOFIYA)
    await h.tap('add:yes')
    assert 'no free student seats' in h.session.texts()[-1]


async def test_backend_down_gives_the_card_back(h):
    await h.log_in()
    h.api.errors['add_student'] = ApiUnavailable('timeout')
    await h.say(SOFIYA)
    await h.tap('add:yes')
    assert 'temporarily unavailable' in h.session.texts()[-1]
    restored = [call for call in h.session.of('EditMessageText') if 'Saydazimova Sofiya' in call[1]['text']]
    assert restored and buttons(restored[-1]) == ['add:yes', 'add:no']
    h.api.errors.pop('add_student')
    await h.tap('add:yes')
    assert len(h.api.names('add_student')) == 2
    assert 'Tmp-Pass-42' in h.session.texts()[-1]
