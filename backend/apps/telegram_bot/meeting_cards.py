"""Meeting "cards" in Telegram: a few plain lines and the buttons that fit the meeting's state.

Counselor card (a student booked, moved, cancelled or answered an invitation):

    📅 New meeting request
    Sardor Abdumanobov
    Sun 22 Nov, 18:00 (Tashkent) · 45 min
    Telegram: @username
    Slots left: 14

Student card (their own booking, or what the counselor did):

    ✅ Meeting requested
    Avazbek Khamidov
    Sun 22 Nov, 18:00 (Tashkent) · 45 min
    Status: waiting for confirmation

Buttons come from ``buttons_for``; pressing one calls ``perform_action``, which runs the website's own
booking actions (so notices, emails, freed slots and ``cancelled_by_role`` are the website's).
"""
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.admissions.meetings import window_summary
from apps.admissions.models import Booking
from apps.users.models import User

from .models import StudentTelegram, TelegramLink, TelegramOutbox
from .services import Refused, resolve_link

CALLBACK_PREFIX = 'mt'
ACTIONS = ('confirm', 'decline', 'cancel')

WEEKDAYS = {
    'en': ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'),
    'ru': ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'),
    'uz': ('Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya'),
}
MONTHS = {
    'en': ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'),
    'ru': ('янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'),
    'uz': ('yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek'),
}

CARDS = {
    # Card headers.
    'h_new': {'uz': '📅 Yangi uchrashuv so\'rovi', 'ru': '📅 Новый запрос на встречу', 'en': '📅 New meeting request'},
    'h_requested': {'uz': '✅ Uchrashuv so\'raldi', 'ru': '✅ Встреча запрошена', 'en': '✅ Meeting requested'},
    'h_move_requested': {'uz': '🔁 Vaqtni o\'zgartirish so\'raldi', 'ru': '🔁 Запрошен перенос', 'en': '🔁 Reschedule requested'},
    'h_moved': {'uz': '🔁 Uchrashuv vaqti o\'zgardi', 'ru': '🔁 Время встречи изменено', 'en': '🔁 Meeting moved'},
    'h_confirmed': {'uz': '✅ Uchrashuv tasdiqlandi', 'ru': '✅ Встреча подтверждена', 'en': '✅ Meeting confirmed'},
    'h_declined': {'uz': '❌ So\'rov rad etildi', 'ru': '❌ Запрос отклонён', 'en': '❌ Request declined'},
    'h_cancelled': {'uz': '🚫 Uchrashuv bekor qilindi', 'ru': '🚫 Встреча отменена', 'en': '🚫 Meeting cancelled'},
    'h_invited': {'uz': '📅 Uchrashuvga taklif', 'ru': '📅 Приглашение на встречу', 'en': '📅 Meeting invitation'},
    'h_accepted': {'uz': '✅ Taklif qabul qilindi', 'ru': '✅ Приглашение принято', 'en': '✅ Invitation accepted'},
    'h_rejected': {'uz': '❌ Taklif rad etildi', 'ru': '❌ Приглашение отклонено', 'en': '❌ Invitation declined'},
    # Lines.
    'when': {'uz': '{day}, {clock} (Toshkent) · {minutes} daqiqa', 'ru': '{day}, {clock} (Ташкент) · {minutes} мин', 'en': '{day}, {clock} (Tashkent) · {minutes} min'},
    'telegram': {'uz': 'Telegram: @{username}', 'ru': 'Telegram: @{username}', 'en': 'Telegram: @{username}'},
    'telegram_none': {'uz': 'Telegram: ulanmagan', 'ru': 'Telegram: не подключён', 'en': 'Telegram: not linked'},
    'telegram_nouser': {'uz': 'Telegram: ulangan, username yo\'q', 'ru': 'Telegram: подключён, без username', 'en': 'Telegram: linked, no username'},
    'slots_left': {'uz': 'Bo\'sh vaqtlar: {free}', 'ru': 'Свободных слотов: {free}', 'en': 'Slots left: {free}'},
    'status': {'uz': 'Holat: {status}', 'ru': 'Статус: {status}', 'en': 'Status: {status}'},
    's_waiting_you': {
        'uz': 'iltimos, saytda tasdiqlang', 'ru': 'пожалуйста, подтвердите на сайте', 'en': 'please confirm on the website',
    },
    's_waiting': {'uz': 'tasdiqlash kutilmoqda', 'ru': 'ожидает подтверждения', 'en': 'waiting for confirmation'},
    's_approved': {'uz': 'tasdiqlangan', 'ru': 'подтверждена', 'en': 'confirmed'},
    's_cancelled': {'uz': 'bekor qilingan', 'ru': 'отменена', 'en': 'cancelled'},
    's_cancelled_you': {'uz': 'siz bekor qildingiz', 'ru': 'отменена вами', 'en': 'cancelled by you'},
    's_rejected': {'uz': 'rad etilgan', 'ru': 'отклонена', 'en': 'declined'},
    's_completed': {'uz': 'o\'tkazilgan', 'ru': 'состоялась', 'en': 'completed'},
    # Buttons.
    'b_confirm': {'uz': '✅ Tasdiqlash', 'ru': '✅ Подтвердить', 'en': '✅ Confirm'},
    'b_decline': {'uz': '❌ Rad etish', 'ru': '❌ Отклонить', 'en': '❌ Decline'},
    'b_cancel': {'uz': '🚫 Bekor qilish', 'ru': '🚫 Отменить', 'en': '🚫 Cancel meeting'},
    'b_profile': {'uz': '👤 Profil', 'ru': '👤 Профиль', 'en': '👤 Profile'},
    'b_message': {'uz': '💬 Telegramda yozish', 'ru': '💬 Написать в Telegram', 'en': '💬 Message on Telegram'},
    'b_website': {'uz': '🌐 Saytda ochish', 'ru': '🌐 Открыть на сайте', 'en': '🌐 Open on website'},
    # Result lines added under a card after a button press.
    'r_confirmed': {'uz': '✅ Tasdiqlandi', 'ru': '✅ Подтверждено', 'en': '✅ Confirmed'},
    'r_declined': {'uz': '❌ Rad etildi', 'ru': '❌ Отклонено', 'en': '❌ Declined'},
    'r_cancelled': {'uz': '🚫 Siz bekor qildingiz', 'ru': '🚫 Отменено вами', 'en': '🚫 Cancelled by you'},
    'r_already_confirmed': {'uz': 'Allaqachon tasdiqlangan', 'ru': 'Уже подтверждено', 'en': 'Already confirmed'},
    'r_already_declined': {'uz': 'Allaqachon rad etilgan', 'ru': 'Уже отклонено', 'en': 'Already declined'},
    'r_already_cancelled': {'uz': 'Allaqachon bekor qilingan', 'ru': 'Уже отменено', 'en': 'Already cancelled'},
    'r_unavailable': {
        'uz': 'Bu uchrashuvni endi o\'zgartirib bo\'lmaydi', 'ru': 'Эту встречу уже нельзя изменить',
        'en': 'This meeting can no longer be changed',
    },
    'r_expired': {'uz': 'Bu so\'rov muddati o\'tgan', 'ru': 'Срок этого запроса истёк', 'en': 'This request has expired'},
    'forbidden': {'uz': 'Bu amal sizga mavjud emas', 'ru': 'Это действие вам недоступно', 'en': 'This action is not available to you'},
}

# Student-side event -> card header. Staff-side: what the student did.
STUDENT_HEADERS = {
    'requested': 'h_requested', 'booked': 'h_requested', 'confirmed': 'h_confirmed', 'declined': 'h_declined',
    'cancelled': 'h_cancelled', 'move_requested': 'h_move_requested', 'moved': 'h_moved', 'invited': 'h_invited',
}
STAFF_HEADERS = {
    'booked': 'h_new', 'moved': 'h_move_requested', 'cancelled': 'h_cancelled', 'accepted': 'h_accepted',
    'declined': 'h_rejected',
}


def card_text(language, key, **values):
    entry = CARDS[key]
    return (entry.get(language) or entry['uz']).format(**values)


def _escape(value):
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _name(user):
    return (user.get_full_name().strip() or user.username) if user else '—'


def when_line(booking, language):
    start = timezone.localtime(booking.starts_at)
    language = language if language in WEEKDAYS else 'uz'
    day = f'{WEEKDAYS[language][start.weekday()]} {start.day} {MONTHS[language][start.month - 1]}'
    return card_text(language, 'when', day=day, clock=start.strftime('%H:%M'), minutes=booking.duration_minutes)


def _is_open(booking):
    return booking.status in Booking.OPEN_STATUSES and not booking.has_started


def _student_telegram(booking):
    return StudentTelegram.objects.filter(user_id=booking.student.user_id).first()


def student_username(booking):
    link = _student_telegram(booking)
    return link.telegram_username if link and link.telegram_username else ''


def _status_key(booking, viewer):
    if booking.status == Booking.Status.PENDING:
        return 's_waiting_you' if viewer == 'student' and booking.staff_requested else 's_waiting'
    if booking.status == Booking.Status.CANCELLED:
        return 's_cancelled_you' if viewer == 'student' and booking.cancelled_by_role == 'student' else 's_cancelled'
    return {
        Booking.Status.APPROVED: 's_approved', Booking.Status.REJECTED: 's_rejected', Booking.Status.COMPLETED: 's_completed',
    }.get(booking.status, 's_waiting')


def _state_header(booking, viewer):
    """The header for a card re-drawn from the meeting's current state (after a button press)."""
    if booking.status == Booking.Status.PENDING:
        return 'h_invited' if viewer == 'student' and booking.staff_requested else 'h_new' if viewer == 'staff' else 'h_requested'
    if booking.status == Booking.Status.REJECTED:
        return 'h_declined'
    if booking.status == Booking.Status.CANCELLED:
        return 'h_cancelled'
    return 'h_confirmed'


def staff_card(booking, language, header):
    link = _student_telegram(booking)
    if link is None or (not link.is_active and not link.telegram_username):
        telegram = card_text(language, 'telegram_none')
    elif link.telegram_username:
        telegram = card_text(language, 'telegram', username=_escape(link.telegram_username))
    else:
        telegram = card_text(language, 'telegram_nouser')
    lines = [
        card_text(language, header), f'<b>{_escape(_name(booking.student.user))}</b>', when_line(booking, language), telegram,
    ]
    if booking.participant_id:
        lines.append(card_text(language, 'slots_left', free=window_summary(booking.participant)['free_slots']))
    return '\n'.join(lines)


def student_card(booking, language, header):
    return '\n'.join([
        card_text(language, header), f'<b>{_escape(_name(booking.participant))}</b>', when_line(booking, language),
        card_text(language, 'status', status=card_text(language, _status_key(booking, 'student'))),
    ])


def _url_ok(url):
    # Telegram refuses a button whose address is not https (a local dev site, for one).
    return url.startswith('https://')


def buttons_for(booking, viewer, language):
    """Rows of {'text', 'callback_data'|'url'} for `viewer` ('staff' or 'student').

    Staff get Confirm / Decline (a student's pending request) or Cancel (an open meeting), then Profile and
    Message links. Students get no action buttons: they answer and cancel on the website, so the only button
    is a link to it.
    """
    if viewer == 'student':
        site = f'{settings.FRONTEND_URL}/meetings'
        return [[{'text': card_text(language, 'b_website'), 'url': site}]] if _url_ok(site) else []
    rows = []
    row = []
    if _is_open(booking) and booking.status == Booking.Status.PENDING and not booking.staff_requested:
        row = [('confirm', 'b_confirm'), ('decline', 'b_decline')]
    elif _is_open(booking):
        row = [('cancel', 'b_cancel')]
    if row:
        rows.append([
            {'text': card_text(language, key), 'callback_data': f'{CALLBACK_PREFIX}:{action}:{booking.pk}'} for action, key in row
        ])
    links = []
    profile = f'{settings.FRONTEND_URL}/students/{booking.student_id}'
    if _url_ok(profile):
        links.append({'text': card_text(language, 'b_profile'), 'url': profile})
    username = student_username(booking)
    if username:
        links.append({'text': card_text(language, 'b_message'), 'url': f'https://t.me/{username}'})
    if links:
        rows.append(links)
    return rows


# --- queueing -------------------------------------------------------------------------------

def queue_staff_card(booking, action):
    """Tell the booking's staff participant what their student did ('booked', 'moved', 'cancelled',
    'accepted', 'declined'). False when nothing was queued."""
    if not booking.participant_id or action not in STAFF_HEADERS:
        return False
    link = TelegramLink.objects.filter(user_id=booking.participant_id, is_active=True).first()
    if link is None:
        return False
    TelegramOutbox.objects.create(
        chat_id=link.chat_id, booking=booking, text=staff_card(booking, link.language, STAFF_HEADERS[action]),
        buttons=buttons_for(booking, 'staff', link.language),
    )
    return True


def queue_student_card(booking, event):
    """A card for the booking's student, if their Telegram is linked. False when nothing was queued."""
    header = STUDENT_HEADERS.get(event)
    link = StudentTelegram.objects.filter(user_id=booking.student.user_id, is_active=True).first()
    if link is None or header is None:
        return False
    if event == 'moved' and booking.status == Booking.Status.PENDING:
        header = 'h_move_requested'
    TelegramOutbox.objects.create(
        chat_id=link.chat_id, booking=booking, text=student_card(booking, link.language, header),
        buttons=buttons_for(booking, 'student', link.language),
    )
    return True


# --- button presses -------------------------------------------------------------------------

def _actor(chat_id):
    """(user, 'staff'|'student', language) for the chat, or Refused('not_linked')."""
    if TelegramLink.objects.filter(chat_id=chat_id).exists():
        link = resolve_link(chat_id)
        return link.user, 'staff', link.language
    link = StudentTelegram.objects.select_related('user').filter(chat_id=chat_id, is_active=True, user__is_active=True).first()
    if link is None or link.user.role != User.Role.STUDENT:
        raise Refused('not_linked', 404)
    return link.user, 'student', link.language


def _own_booking(user, role, booking_id):
    """The booking only if this person is its participant (same school) or its student; None otherwise."""
    bookings = Booking.objects.select_related('student__user', 'participant')
    if role == 'staff':
        if not user.school_id:
            return None
        return bookings.filter(pk=booking_id, participant=user, student__school_id=user.school_id).first()
    return bookings.filter(pk=booking_id, student__user=user).first()


_VIEW_ACTIONS = {'confirm': 'approve', 'decline': 'reject', 'cancel': 'cancel'}
_TARGETS = {
    'confirm': (Booking.Status.APPROVED, 'r_already_confirmed', 'r_confirmed'),
    'decline': (Booking.Status.REJECTED, 'r_already_declined', 'r_declined'),
    'cancel': (Booking.Status.CANCELLED, 'r_already_cancelled', 'r_cancelled'),
}


def _answerer(booking):
    """Who answers a pending meeting: the student for one staff proposed, the staff participant otherwise."""
    return 'student' if booking.staff_requested else 'staff'


def _run_view(user, view_action, booking_id):
    from apps.admissions.views.portal import BookingViewSet

    request = APIRequestFactory().post(f'/api/bookings/{booking_id}/{view_action}/')
    force_authenticate(request, user=user)
    return BookingViewSet.as_view({'post': view_action})(request, pk=booking_id)


def _card(booking, role, language, line, header=None):
    if role == 'staff':
        text = staff_card(booking, language, header or _state_header(booking, 'staff'))
    else:
        text = student_card(booking, language, header or _state_header(booking, 'student'))
    return text + (f'\n\n{line}' if line else '')


def perform_action(chat_id, booking_id, action, telegram_username=None):
    """Run a card button for the chat's own meeting through the website's booking actions.

    Returns {'result', 'alert', 'text', 'buttons'}: the card redrawn from the meeting's state with a result
    line, and a short alert when nothing changed. A meeting the chat is not part of is a plain 404
    ('not_found'), whoever asks, so nothing about it leaks.
    """
    if action not in ACTIONS:
        raise Refused('invalid_action', 400)
    user, role, language = _actor(chat_id)
    if role == 'student':
        if telegram_username:
            StudentTelegram.objects.filter(chat_id=chat_id, user=user).exclude(telegram_username=telegram_username).update(
                telegram_username=telegram_username,
            )
        # Students answer and cancel on the website only.
        raise Refused('not_allowed', 403)
    booking = _own_booking(user, role, booking_id)
    if booking is None:
        raise Refused('not_found', 404)
    target, already_key, done_key = _TARGETS[action]

    def reply(result, key, alert=None, current=None):
        current = current or booking
        return {
            'result': result, 'alert': alert and card_text(language, alert),
            'text': _card(current, role, language, card_text(language, key)),
            'buttons': buttons_for(current, role, language),
        }

    if booking.status == target:
        return reply('already', already_key, alert=already_key)
    if action != 'cancel' and booking.status == Booking.Status.PENDING and _answerer(booking) != role:
        # Not this person's answer to give: the card is theirs, but the button is not.
        raise Refused('not_allowed', 403)
    if action == 'cancel':
        allowed = _is_open(booking)
    else:
        allowed = booking.status == Booking.Status.PENDING and _is_open(booking)
    if not allowed:
        key = 'r_expired' if booking.is_expired else 'r_unavailable'
        return reply('unavailable', key, alert=key)
    response = _run_view(user, _VIEW_ACTIONS[action], booking.pk)
    booking = Booking.objects.select_related('student__user', 'participant').get(pk=booking.pk)
    if response.status_code == 403:
        raise Refused('not_allowed', 403)
    if response.status_code >= 400:
        key = 'r_expired' if 'expired' in str(getattr(response, 'data', '')) else 'r_unavailable'
        return reply('unavailable', key, alert=key, current=booking)
    return reply('done', done_key, current=booking)
