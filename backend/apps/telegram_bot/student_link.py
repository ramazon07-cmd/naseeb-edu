"""Students' Telegram: linking a chat with a one-time link, and the meeting messages sent to it.

1. The student presses "Connect Telegram" on Meetings; ``issue_token`` returns a ``t.me`` link whose
   start payload holds a one-time token (only its HMAC is stored, 15 minutes, newest replaces older).
2. The student opens it and presses Start; the bot calls ``consume_token``, which ties that chat to them.

From then on meeting events and reminders are written to ``TelegramOutbox``; the bot asks for
them every minute (``pending_messages``) and reports back what it sent (``acknowledge``).
"""
import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.admissions.models import Booking
from apps.users.cache_safety import count_hit
from apps.users.models import User

from .models import StudentLinkToken, StudentTelegram, TelegramLink, TelegramOutbox
from .services import Refused

TOKEN_PREFIX = 's_'
TOKEN_TTL = timedelta(minutes=15)
# Wrong or stale tokens a chat may present per hour (a real token is 256 bits: this only stops floods).
ATTEMPTS_PER_HOUR = 30
TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{16,62}$')
LANGUAGES = {choice for choice, _ in TelegramLink.Language.choices}
# Reminder steps, in minutes before the start; 0 is "the meeting has started".
REMINDER_STEPS = (24 * 60, 5 * 60, 4 * 60, 3 * 60, 2 * 60, 60, 30, 0)
# A step is sent only this long after its moment: after downtime, or for a meeting booked an hour
# ahead, the student gets the latest step, not every step they missed.
REMINDER_GRACE = timedelta(minutes=15)
# Unsent messages older than this are dropped rather than delivered late.
OUTBOX_MAX_AGE = timedelta(hours=1)
CLAIM_LEASE = timedelta(minutes=2)
BATCH = 200


def telegram_link_enabled():
    """Meetings asks students to connect Telegram only when the website can point them at the bot."""
    return bool(settings.TELEGRAM_BOT_USERNAME)


def is_linked(user):
    return StudentTelegram.objects.filter(user=user, is_active=True).exists()


def link_status(user):
    return {'enabled': telegram_link_enabled(), 'linked': is_linked(user)}


def _hash(token):
    return hmac.new(settings.SECRET_KEY.encode(), f'student-link-token:{token}'.encode(), hashlib.sha256).hexdigest()


def _language(value):
    value = str(value or '')[:2].lower()
    return value if value in LANGUAGES else TelegramLink.Language.UZ


# --- bot side -------------------------------------------------------------------------------

def meetings_url():
    return f'{settings.FRONTEND_URL}/meetings'


def _invalid_token():
    # The site address lets the bot tell the student where to press the button again.
    return Refused('invalid_token', 400, site_url=meetings_url())


def consume_token(chat_id, token, language=None):
    """Link ``chat_id`` to the student the token was issued for. The token works once."""
    hits = count_hit(f'tgbot-student-link:{chat_id}', 3600)
    if hits is not None and hits[0] > ATTEMPTS_PER_HOUR:
        raise Refused('too_many', 429)
    token = str(token or '')
    if not TOKEN_PATTERN.match(token):
        raise _invalid_token()
    language = _language(language)
    now = timezone.now()
    with transaction.atomic():
        pending = (
            StudentLinkToken.objects.select_for_update().select_related('user')
            .filter(token_hash=_hash(token), expires_at__gt=now).first()
        )
        user = pending.user if pending else None
        if user is None or not user.is_active or user.role != User.Role.STUDENT:
            raise _invalid_token()
        pending.delete()
        # One chat per student and one student per chat: whatever either was linked to before is replaced.
        # When the chat changes owner, the previous owner's unsent messages are dropped so the new owner
        # never receives them.
        # Anything still unsent on a chat this student does not already own was addressed to whoever had
        # it before (a current owner, or one who has since moved away and left leased rows behind), so it
        # is dropped whatever its lease state: a chat only ever receives its own student's messages.
        if not StudentTelegram.objects.filter(chat_id=chat_id, user=user).exists():
            TelegramOutbox.objects.filter(chat_id=chat_id, sent_at__isnull=True).delete()
        StudentTelegram.objects.filter(chat_id=chat_id).exclude(user=user).delete()
        # Locked so the old chat cannot change owner while its waiting rows are moved: another
        # student's link to that chat first deletes this row and so waits for this transaction.
        previous = StudentTelegram.objects.select_for_update().filter(user=user).exclude(chat_id=chat_id).first()
        if previous:
            # The same student moved to a new chat: what was still waiting for them follows them there.
            # Rows the bot has already leased stay put (it is sending them to this student's old chat),
            # so an acknowledgement never marks a moved row as delivered.
            TelegramOutbox.objects.filter(
                chat_id=previous.chat_id, sent_at__isnull=True, claimed_at__isnull=True,
            ).update(chat_id=chat_id)
        try:
            StudentTelegram.objects.update_or_create(
                user=user, defaults={'chat_id': chat_id, 'language': language, 'is_active': True},
            )
        except IntegrityError:
            raise _invalid_token()
    StudentLinkToken.objects.filter(expires_at__lte=now).delete()
    return {'full_name': user.get_full_name().strip() or user.username, 'language': language}


def pending_messages(now=None):
    """Due reminders are queued, then up to BATCH unsent messages are leased to this caller."""
    now = now or timezone.now()
    TelegramOutbox.objects.filter(sent_at__isnull=True, created_at__lt=now - OUTBOX_MAX_AGE).delete()
    queue_reminders(now)
    with transaction.atomic():
        rows = list(
            TelegramOutbox.objects.select_for_update(skip_locked=True)
            .filter(sent_at__isnull=True)
            .exclude(claimed_at__gt=now - CLAIM_LEASE)
            .order_by('created_at', 'id')[:BATCH]
        )
        # Bookings are read apart: FOR UPDATE cannot lock across the nullable booking join on Postgres.
        bookings = Booking.objects.in_bulk({row.booking_id for row in rows if row.key and row.booking_id})
        stale = [row.pk for row in rows if _stale_reminder(row, bookings)]
        TelegramOutbox.objects.filter(pk__in=stale).delete()
        rows = [row for row in rows if row.pk not in stale]
        TelegramOutbox.objects.filter(pk__in=[row.pk for row in rows]).update(claimed_at=now)
    return {'messages': [{'id': row.pk, 'chat_id': row.chat_id, 'text': row.text} for row in rows]}


def _stale_reminder(row, bookings):
    """A reminder still waiting for a meeting that was since cancelled or moved: never sent."""
    if not (row.key or '').startswith('meeting:'):
        return False
    booking = bookings.get(row.booking_id)
    if booking is None or booking.status != Booking.Status.APPROVED:
        return True
    return row.key.split(':')[2] != str(int(booking.starts_at.timestamp()))


def acknowledge(sent_ids, blocked_chats):
    now = timezone.now()
    sent = TelegramOutbox.objects.filter(pk__in=sent_ids, sent_at__isnull=True).update(sent_at=now)
    if blocked_chats:
        StudentTelegram.objects.filter(chat_id__in=blocked_chats).update(is_active=False, updated_at=now)
        TelegramOutbox.objects.filter(chat_id__in=blocked_chats, sent_at__isnull=True).delete()
    # Sent rows are kept two days for reminder de-duplication (a step is never sent twice), then cleared.
    TelegramOutbox.objects.filter(sent_at__lt=now - timedelta(days=2)).delete()
    return {'sent': sent}


# --- website side ---------------------------------------------------------------------------

def issue_token(user):
    """The link a signed-in student opens to connect their Telegram; replaces any earlier one."""
    if user.role != User.Role.STUDENT:
        raise Refused('role_not_allowed', 403)
    if not telegram_link_enabled():
        raise Refused('telegram_disabled', 404)
    token = secrets.token_urlsafe(32)
    now = timezone.now()
    StudentLinkToken.objects.filter(expires_at__lte=now).delete()
    StudentLinkToken.objects.update_or_create(
        user=user, defaults={'token_hash': _hash(token), 'expires_at': now + TOKEN_TTL},
    )
    return {
        'url': f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={TOKEN_PREFIX}{token}',
        'expires_in': int(TOKEN_TTL.total_seconds()),
    }


def unlink(user):
    for link in StudentTelegram.objects.filter(user=user):
        TelegramOutbox.objects.filter(chat_id=link.chat_id, sent_at__isnull=True).delete()
    StudentTelegram.objects.filter(user=user).delete()
    return link_status(user)


# --- meeting messages -----------------------------------------------------------------------

def _when(moment):
    return timezone.localtime(moment).strftime('%d.%m.%Y %H:%M')


def _other(booking):
    person = booking.participant
    return (person.get_full_name().strip() or person.username) if person else '—'


def _meeting_text(link, booking, key):
    return text(
        link.language, key, topic=_escape(booking.topic), other=_escape(_other(booking)),
        time=_when(booking.starts_at), minutes=booking.duration_minutes, url=f'{settings.FRONTEND_URL}/meetings',
    )


def queue_event(booking, recipient, event):
    """A message about a change to `booking` for the student `recipient`, if their Telegram is linked."""
    link = StudentTelegram.objects.filter(user=recipient, is_active=True).first()
    if link is None or f'event_{event}' not in TEXTS:
        return False
    TelegramOutbox.objects.create(chat_id=link.chat_id, booking=booking, text=_meeting_text(link, booking, f'event_{event}'))
    return True


def queue_own_action(booking, action):
    """The student's own confirmation of what they just did ('booked', 'cancelled', 'moved'), if their Telegram is linked."""
    link = StudentTelegram.objects.filter(user_id=booking.student.user_id, is_active=True).first()
    if link is None:
        return False
    if action == 'cancelled':
        key = 'own_cancelled'
    else:
        waiting = booking.status == Booking.Status.PENDING
        key = f'own_{action}_{"waiting" if waiting else "confirmed"}'
    TelegramOutbox.objects.create(chat_id=link.chat_id, booking=booking, text=_meeting_text(link, booking, key))
    return True


def _step(booking, now):
    """The reminder step due now for `booking`, or None."""
    passed = [step for step in REMINDER_STEPS if now >= booking.starts_at - timedelta(minutes=step)]
    if not passed:
        return None
    step = min(passed)
    if now - (booking.starts_at - timedelta(minutes=step)) > REMINDER_GRACE:
        return None
    return step


def queue_reminders(now=None):
    now = now or timezone.now()
    bookings = (
        Booking.objects.filter(
            status=Booking.Status.APPROVED,
            starts_at__gt=now - REMINDER_GRACE,
            starts_at__lte=now + timedelta(minutes=REMINDER_STEPS[0]) + REMINDER_GRACE,
            student__user__student_telegram__is_active=True,
        )
        .select_related('student__user__student_telegram', 'participant')
    )
    queued = 0
    for booking in bookings:
        step = _step(booking, now)
        if step is None:
            continue
        link = booking.student.user.student_telegram
        key = f'meeting:{booking.pk}:{int(booking.starts_at.timestamp())}:{step}'
        name = 'reminder_started' if step == 0 else 'reminder_day' if step == REMINDER_STEPS[0] else 'reminder_before'
        before = f'{step // 60}' if step >= 60 else f'{step}'
        values_key = 'hours' if step >= 60 else 'minutes_left'
        body = text(
            link.language, name, topic=_escape(booking.topic), other=_escape(_other(booking)),
            time=_when(booking.starts_at), minutes=booking.duration_minutes, url=f'{settings.FRONTEND_URL}/meetings',
            left=text(link.language, values_key, n=before),
        )
        _, created = TelegramOutbox.objects.get_or_create(
            key=key, defaults={'chat_id': link.chat_id, 'booking': booking, 'text': body},
        )
        queued += created
    return queued


def _escape(value):
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def text(language, key, **values):
    entry = TEXTS[key]
    return (entry.get(language) or entry['uz']).format(**values)


_DETAILS = {
    'uz': '\n\n<b>{topic}</b>\n{other}\n🕒 {time} (Toshkent), {minutes} daqiqa\n{url}',
    'ru': '\n\n<b>{topic}</b>\n{other}\n🕒 {time} (Ташкент), {minutes} мин\n{url}',
    'en': '\n\n<b>{topic}</b>\n{other}\n🕒 {time} (Tashkent), {minutes} min\n{url}',
}


def _with_details(entry):
    return {lang: value + _DETAILS[lang] for lang, value in entry.items()}


def _with_topic(entry):
    return {lang: value + '\n<b>{topic}</b>\n{url}' for lang, value in entry.items()}


TEXTS = {
    'hours': {'uz': '{n} soat', 'ru': '{n} ч', 'en': '{n} h'},
    'minutes_left': {'uz': '{n} daqiqa', 'ru': '{n} мин', 'en': '{n} min'},
    'event_requested': _with_details({
        'uz': '📅 Sizga yangi uchrashuv taklif qilindi.',
        'ru': '📅 Вам предложили новую встречу.',
        'en': '📅 A new meeting was requested with you.',
    }),
    'event_invited': _with_details({
        'uz': '📅 {other} sizni {time} ga uchrashuvga taklif qildi. Saytda tasdiqlang.',
        'ru': '📅 {other} приглашает вас на встречу ({time}). Подтвердите на сайте.',
        'en': '📅 {other} invited you to a meeting on {time}. Confirm it on the website.',
    }),
    'event_confirmed': _with_details({
        'uz': '✅ Uchrashuvingiz tasdiqlandi.',
        'ru': '✅ Ваша встреча подтверждена.',
        'en': '✅ Your meeting is confirmed.',
    }),
    'event_declined': _with_details({
        'uz': '❌ Uchrashuv so\'rovingiz rad etildi.',
        'ru': '❌ Ваш запрос на встречу отклонён.',
        'en': '❌ Your meeting request was declined.',
    }),
    'event_cancelled': _with_details({
        'uz': '🚫 Uchrashuv bekor qilindi.',
        'ru': '🚫 Встреча отменена.',
        'en': '🚫 The meeting was cancelled.',
    }),
    'event_move_requested': _with_details({
        'uz': '🔁 Uchrashuv vaqtini o\'zgartirish so\'raldi. Saytda tasdiqlang.',
        'ru': '🔁 Предложено перенести встречу. Подтвердите на сайте.',
        'en': '🔁 A new time was proposed for your meeting. Confirm it on the website.',
    }),
    'event_moved': _with_details({
        'uz': '🔁 Uchrashuv vaqti o\'zgardi.',
        'ru': '🔁 Время встречи изменено.',
        'en': '🔁 Your meeting was moved.',
    }),
    'own_booked_waiting': _with_topic({
        'uz': '✅ Band qilindi: {other}, {time} (Toshkent), {minutes} daqiqa — tasdiqlash kutilmoqda.',
        'ru': '✅ Записано: {other}, {time} (Ташкент), {minutes} мин — ожидает подтверждения.',
        'en': '✅ Booked: {other}, {time} Tashkent, {minutes} min — waiting for confirmation.',
    }),
    'own_booked_confirmed': _with_topic({
        'uz': '✅ Band qilindi: {other}, {time} (Toshkent), {minutes} daqiqa — tasdiqlandi.',
        'ru': '✅ Записано: {other}, {time} (Ташкент), {minutes} мин — подтверждено.',
        'en': '✅ Booked: {other}, {time} Tashkent, {minutes} min — confirmed.',
    }),
    'own_cancelled': _with_topic({
        'uz': '❌ Siz uchrashuvni bekor qildingiz: {other}, {time} (Toshkent), {minutes} daqiqa.',
        'ru': '❌ Вы отменили встречу: {other}, {time} (Ташкент), {minutes} мин.',
        'en': '❌ You cancelled your meeting: {other}, {time} Tashkent, {minutes} min.',
    }),
    'own_moved_waiting': _with_topic({
        'uz': '🔁 Uchrashuvni {time} (Toshkent) ga ko\'chirishni so\'radingiz ({other}, {minutes} daqiqa) — tasdiqlash kutilmoqda.',
        'ru': '🔁 Вы попросили перенести встречу на {time} (Ташкент) ({other}, {minutes} мин) — ожидает подтверждения.',
        'en': '🔁 You asked to move your meeting with {other} to {time} Tashkent, {minutes} min — waiting for confirmation.',
    }),
    'own_moved_confirmed': _with_topic({
        'uz': '🔁 Uchrashuv {time} (Toshkent) ga ko\'chirildi ({other}, {minutes} daqiqa) — tasdiqlandi.',
        'ru': '🔁 Встреча перенесена на {time} (Ташкент) ({other}, {minutes} мин) — подтверждено.',
        'en': '🔁 Your meeting with {other} moved to {time} Tashkent, {minutes} min — confirmed.',
    }),
    'staff_booked': {
        'uz': '📅 {student} uchrashuv band qildi.\n🕒 {time} (Toshkent), {minutes} daqiqa\n<b>{topic}</b>\n{tally}',
        'ru': '📅 {student} записал(а)ся на встречу.\n🕒 {time} (Ташкент), {minutes} мин\n<b>{topic}</b>\n{tally}',
        'en': '📅 {student} booked a meeting.\n🕒 {time} (Tashkent), {minutes} min\n<b>{topic}</b>\n{tally}',
    },
    'staff_cancelled': {
        'uz': '❌ {student} uchrashuvni bekor qildi.\n🕒 {time} (Toshkent), {minutes} daqiqa\n<b>{topic}</b>\n{tally}',
        'ru': '❌ {student} отменил(а) встречу.\n🕒 {time} (Ташкент), {minutes} мин\n<b>{topic}</b>\n{tally}',
        'en': '❌ {student} cancelled a meeting.\n🕒 {time} (Tashkent), {minutes} min\n<b>{topic}</b>\n{tally}',
    },
    'staff_moved': {
        'uz': '🔁 {student} uchrashuvni ko\'chirishni so\'radi.\n🕒 Yangi vaqt: {time} (Toshkent), {minutes} daqiqa\n<b>{topic}</b>\n{tally}',
        'ru': '🔁 {student} просит перенести встречу.\n🕒 Новое время: {time} (Ташкент), {minutes} мин\n<b>{topic}</b>\n{tally}',
        'en': '🔁 {student} asked to move a meeting.\n🕒 New time: {time} (Tashkent), {minutes} min\n<b>{topic}</b>\n{tally}',
    },
    'staff_accepted': {
        'uz': '✅ {student} taklifingizni qabul qildi.\n🕒 {time} (Toshkent), {minutes} daqiqa\n<b>{topic}</b>\n{tally}',
        'ru': '✅ {student} принял(а) ваше приглашение.\n🕒 {time} (Ташкент), {minutes} мин\n<b>{topic}</b>\n{tally}',
        'en': '✅ {student} accepted your invitation.\n🕒 {time} (Tashkent), {minutes} min\n<b>{topic}</b>\n{tally}',
    },
    'staff_declined': {
        'uz': '🚫 {student} taklifingizni rad etdi.\n🕒 {time} (Toshkent), {minutes} daqiqa\n<b>{topic}</b>\n{tally}',
        'ru': '🚫 {student} отклонил(а) ваше приглашение.\n🕒 {time} (Ташкент), {minutes} мин\n<b>{topic}</b>\n{tally}',
        'en': '🚫 {student} declined your invitation.\n🕒 {time} (Tashkent), {minutes} min\n<b>{topic}</b>\n{tally}',
    },
    'staff_tally': {
        'uz': 'Bu oynada: {booked} ta band · {free} ta bo\'sh vaqt qoldi',
        'ru': 'В этом окне: {booked} занято · {free} свободных слотов осталось',
        'en': 'This window: {booked} booked · {free} free slots left',
    },
    'reminder_day': _with_details({
        'uz': '⏰ Eslatma: ertaga shu vaqtda uchrashuvingiz bor.',
        'ru': '⏰ Напоминание: завтра в это время у вас встреча.',
        'en': '⏰ Reminder: you have a meeting this time tomorrow.',
    }),
    'reminder_before': _with_details({
        'uz': '⏰ Uchrashuvgacha {left} qoldi.',
        'ru': '⏰ До встречи осталось {left}.',
        'en': '⏰ Your meeting starts in {left}.',
    }),
    'reminder_started': _with_details({
        'uz': '▶️ Uchrashuv boshlandi! Kechikmang.',
        'ru': '▶️ Встреча началась! Не опаздывайте.',
        'en': '▶️ Your meeting has started! Join now.',
    }),
}
