"""Students' Telegram: linking a chat with a code, and the meeting messages sent to it.

1. The student taps "Connect Telegram" on Meetings, which opens the bot.
2. The bot asks ``issue_code`` for a 6-digit code and shows it in the chat.
3. The student types the code on the website; ``link_code`` ties that chat to their account.

From then on meeting events and reminders are written to ``TelegramOutbox``; the bot asks for
them every minute (``pending_messages``) and reports back what it sent (``acknowledge``).
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.admissions.models import Booking
from apps.users.cache_safety import count_hit
from apps.users.models import User

from .models import StudentLinkCode, StudentTelegram, TelegramLink, TelegramOutbox
from .services import Refused

CODE_DIGITS = 6
CODE_TTL = timedelta(minutes=10)
CODES_PER_HOUR = 10
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


def bot_url():
    return f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start=student' if telegram_link_enabled() else ''


def is_linked(user):
    return StudentTelegram.objects.filter(user=user, is_active=True).exists()


def link_status(user):
    return {'enabled': telegram_link_enabled(), 'linked': is_linked(user), 'bot_url': bot_url()}


def _hash(code):
    return hmac.new(settings.SECRET_KEY.encode(), f'student-link:{code}'.encode(), hashlib.sha256).hexdigest()


def _language(value):
    value = str(value or '')[:2].lower()
    return value if value in LANGUAGES else TelegramLink.Language.UZ


# --- bot side -------------------------------------------------------------------------------

def issue_code(chat_id, language=None):
    hits = count_hit(f'tgbot-student-code:{chat_id}', 3600)
    if hits is not None and hits[0] > CODES_PER_HOUR:
        raise Refused('too_many', 429)
    now = timezone.now()
    StudentLinkCode.objects.filter(expires_at__lte=now).delete()
    for _ in range(5):
        code = ''.join(secrets.choice('0123456789') for _ in range(CODE_DIGITS))
        digest = _hash(code)
        # Two live codes are never the same, so a typed code names exactly one chat.
        if not StudentLinkCode.objects.filter(code_hash=digest, expires_at__gt=now).exclude(chat_id=chat_id).exists():
            break
    StudentLinkCode.objects.update_or_create(
        chat_id=chat_id,
        defaults={'code_hash': digest, 'language': _language(language), 'expires_at': now + CODE_TTL},
    )
    linked = StudentTelegram.objects.filter(chat_id=chat_id, is_active=True).select_related('user').first()
    return {
        'code': code,
        'expires_minutes': int(CODE_TTL.total_seconds() // 60),
        'linked_name': (linked.user.get_full_name().strip() or linked.user.username) if linked else '',
        'site_url': f'{settings.FRONTEND_URL}/meetings',
    }


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
        TelegramOutbox.objects.filter(pk__in=[row.pk for row in rows]).update(claimed_at=now)
    return {'messages': [{'id': row.pk, 'chat_id': row.chat_id, 'text': row.text} for row in rows]}


def acknowledge(sent_ids, blocked_chats):
    now = timezone.now()
    sent = TelegramOutbox.objects.filter(pk__in=sent_ids, sent_at__isnull=True).update(sent_at=now)
    if blocked_chats:
        StudentTelegram.objects.filter(chat_id__in=blocked_chats).update(is_active=False, updated_at=now)
        TelegramOutbox.objects.filter(chat_id__in=blocked_chats, sent_at__isnull=True).delete()
    # Sent rows are kept a day for reminder de-duplication (a step is never sent twice), then cleared.
    TelegramOutbox.objects.filter(sent_at__lt=now - timedelta(days=2)).delete()
    return {'sent': sent}


# --- website side ---------------------------------------------------------------------------

def link_code(user, code):
    if user.role != User.Role.STUDENT:
        raise Refused('role_not_allowed', 403)
    code = ''.join(ch for ch in str(code or '') if ch.isdigit())
    if len(code) != CODE_DIGITS:
        raise Refused('invalid_code', 400)
    now = timezone.now()
    with transaction.atomic():
        pending = StudentLinkCode.objects.select_for_update().filter(code_hash=_hash(code), expires_at__gt=now).first()
        if pending is None:
            raise Refused('invalid_code', 400)
        chat_id, language = pending.chat_id, pending.language
        pending.delete()
        # One chat per student and one student per chat: whatever either was linked to before is replaced.
        StudentTelegram.objects.filter(chat_id=chat_id).exclude(user=user).delete()
        try:
            StudentTelegram.objects.update_or_create(
                user=user, defaults={'chat_id': chat_id, 'language': language, 'is_active': True},
            )
        except IntegrityError:
            raise Refused('invalid_code', 400)
        name = user.get_full_name().strip() or user.username
        TelegramOutbox.objects.create(chat_id=chat_id, text=text(language, 'linked', name=name))
    return link_status(user)


def unlink(user):
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


TEXTS = {
    'linked': {
        'uz': "✅ Telegram Naseeb hisobingizga ulandi: <b>{name}</b>.\nUchrashuv xabarlari va eslatmalar shu yerga keladi.",
        'ru': '✅ Telegram привязан к аккаунту Naseeb: <b>{name}</b>.\nСообщения и напоминания о встречах будут приходить сюда.',
        'en': '✅ Telegram is now linked to your Naseeb account: <b>{name}</b>.\nMeeting messages and reminders will come here.',
    },
    'hours': {'uz': '{n} soat', 'ru': '{n} ч', 'en': '{n} h'},
    'minutes_left': {'uz': '{n} daqiqa', 'ru': '{n} мин', 'en': '{n} min'},
    'event_requested': _with_details({
        'uz': '📅 Sizga yangi uchrashuv taklif qilindi.',
        'ru': '📅 Вам предложили новую встречу.',
        'en': '📅 A new meeting was requested with you.',
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
