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
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.admissions.models import Booking
from apps.users.cache_safety import count_hit
from apps.users.models import User

from .models import StudentLinkToken, StudentTelegram, TelegramLink, TelegramOutbox
from .followup import queue_followups
from .meeting_cards import staff_in_scope
from .services import Refused, link_allowed
from core.public_urls import public_url

TOKEN_PREFIX = 's_'
TOKEN_TTL = timedelta(minutes=15)
# Wrong or stale tokens a chat may present per hour (a real token is 256 bits: this only stops floods).
ATTEMPTS_PER_HOUR = 30
USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_]{1,32}$')
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


def clean_username(value):
    """A Telegram @username as stored: no '@', and only what Telegram allows (blank otherwise)."""
    value = str(value or '').strip().lstrip('@')
    return value if USERNAME_PATTERN.match(value) else ''


def remember_username(chat_id, telegram_username):
    """Keep a linked student's @username current whenever they talk to the bot (students who linked
    before usernames were stored get theirs this way). A missing username never clears a stored one."""
    username = clean_username(telegram_username)
    if not username:
        return 0
    return StudentTelegram.objects.filter(chat_id=chat_id).exclude(telegram_username=username).update(
        telegram_username=username,
    )


def _language(value):
    value = str(value or '')[:2].lower()
    return value if value in LANGUAGES else TelegramLink.Language.UZ


# --- bot side -------------------------------------------------------------------------------

def meetings_url():
    return public_url('/meetings')


def _invalid_token():
    # The site address lets the bot tell the student where to press the button again.
    return Refused('invalid_token', 400, site_url=meetings_url())


def consume_token(chat_id, token, language=None, telegram_username=None):
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
                user=user, defaults={
                    'chat_id': chat_id, 'language': language, 'is_active': True,
                    'telegram_username': clean_username(telegram_username),
                },
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
    queue_followups(now)
    with transaction.atomic():
        rows = list(
            TelegramOutbox.objects.select_for_update(skip_locked=True)
            .filter(sent_at__isnull=True)
            .exclude(claimed_at__gt=now - CLAIM_LEASE)
            .order_by('created_at', 'id')[:BATCH]
        )
        # Bookings are read apart: FOR UPDATE cannot lock across the nullable booking join on Postgres.
        bookings = Booking.objects.select_related('student', 'participant').in_bulk(
            {row.booking_id for row in rows if row.key and row.booking_id},
        )
        revoked = _revoked_chats({row.chat_id for row in rows})
        stale = [row.pk for row in rows if row.chat_id in revoked or _stale_reminder(row, bookings)]
        TelegramOutbox.objects.filter(pk__in=stale).delete()
        rows = [row for row in rows if row.pk not in stale]
        TelegramOutbox.objects.filter(pk__in=[row.pk for row in rows]).update(claimed_at=now)
    return {'messages': [
        {'id': row.pk, 'chat_id': row.chat_id, 'text': row.text, 'buttons': row.buttons or []} for row in rows
    ]}


def _revoked_chats(chat_ids):
    """Chats of staff links that may no longer be messaged (password changed, account deactivated): what is
    still unsent for them is dropped. A chat that is also an active student chat is left alone."""
    links = TelegramLink.objects.filter(chat_id__in=chat_ids).select_related(
        'user__school', 'user__supervising_counselor',
    )
    revoked = {link.chat_id for link in links if not link_allowed(link)}
    if revoked:
        revoked -= set(StudentTelegram.objects.filter(chat_id__in=revoked, is_active=True).values_list('chat_id', flat=True))
    return revoked


def _stale_reminder(row, bookings):
    """A reminder still waiting for a meeting that was since cancelled or moved: never sent."""
    if not (row.key or '').startswith('meeting:'):
        return False
    booking = bookings.get(row.booking_id)
    if booking is None or booking.status != Booking.Status.APPROVED:
        return True
    if row.key.endswith(':staff') and not staff_in_scope(booking):
        # The counselor moved schools since this was queued: the old school's meeting is not theirs to see.
        return True
    return row.key.split(':')[2] != str(int(booking.starts_at.timestamp()))


def acknowledge(sent_ids, blocked_chats):
    now = timezone.now()
    sent = TelegramOutbox.objects.filter(pk__in=sent_ids, sent_at__isnull=True).update(sent_at=now)
    if blocked_chats:
        StudentTelegram.objects.filter(chat_id__in=blocked_chats).update(is_active=False, updated_at=now)
        # A counselor's blocked chat stops getting reminders too; linking again creates a fresh link.
        TelegramLink.objects.filter(chat_id__in=blocked_chats, is_active=True).update(is_active=False, updated_at=now)
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


def _name(person):
    return (person.get_full_name().strip() or person.username) if person else '—'


def _other(booking):
    """The counselor, as the student's reminders name them."""
    return _name(booking.participant)


def queue_event(booking, recipient, event):
    """A card about a change to `booking` for the student `recipient`, if their Telegram is linked."""
    from .meeting_cards import queue_student_card

    if recipient is None or recipient.pk != booking.student.user_id:
        return False
    return queue_student_card(booking, event)


def queue_own_action(booking, action):
    """The student's own confirmation of what they just did ('booked', 'cancelled', 'moved'), if linked."""
    from .meeting_cards import queue_student_card

    return queue_student_card(booking, action)


def _step(booking, now):
    """The reminder step due now for `booking`, or None."""
    passed = [step for step in REMINDER_STEPS if now >= booking.starts_at - timedelta(minutes=step)]
    if not passed:
        return None
    step = min(passed)
    if now - (booking.starts_at - timedelta(minutes=step)) > REMINDER_GRACE:
        return None
    return step


def _active(parent, relation):
    """The booking person's active Telegram link (`relation` on `parent`), or None."""
    try:
        link = getattr(parent, relation)
    except ObjectDoesNotExist:
        return None
    return link if link.is_active else None


def queue_reminders(now=None):
    """Reminders for approved meetings: one row for the student's chat and one for the counselor's, each
    only if that person is linked (neither depends on the other)."""
    now = now or timezone.now()
    bookings = (
        Booking.objects.filter(
            Q(student__user__student_telegram__is_active=True) | Q(participant__telegram_link__is_active=True),
            status=Booking.Status.APPROVED,
            starts_at__gt=now - REMINDER_GRACE,
            starts_at__lte=now + timedelta(minutes=REMINDER_STEPS[0]) + REMINDER_GRACE,
        )
        .select_related(
            'student__user__student_telegram', 'participant__telegram_link', 'participant__school',
            'participant__supervising_counselor',
        )
    )
    queued = 0
    for booking in bookings:
        step = _step(booking, now)
        if step is None:
            continue
        base = f'meeting:{booking.pk}:{int(booking.starts_at.timestamp())}:{step}'
        student_link = _active(booking.student.user, 'student_telegram')
        if student_link:
            queued += _queue_reminder(booking, step, student_link, base, _other(booking))
        staff_link = _active(booking.participant, 'telegram_link') if booking.participant_id else None
        if staff_link and link_allowed(staff_link) and staff_in_scope(booking):
            queued += _queue_reminder(booking, step, staff_link, f'{base}:staff', _name(booking.student.user))
    return queued


def _queue_reminder(booking, step, link, key, other):
    name = 'reminder_started' if step == 0 else 'reminder_day' if step == REMINDER_STEPS[0] else 'reminder_before'
    before = f'{step // 60}' if step >= 60 else f'{step}'
    values_key = 'hours' if step >= 60 else 'minutes_left'
    body = text(
        link.language, name, topic=_escape(booking.topic), other=_escape(other),
        time=_when(booking.starts_at), minutes=booking.duration_minutes, url=public_url('/meetings'),
        left=text(link.language, values_key, n=before),
    )
    _, created = TelegramOutbox.objects.get_or_create(
        key=key, defaults={'chat_id': link.chat_id, 'booking': booking, 'text': body},
    )
    return int(created)


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
    'hours': {'uz': '{n} soat', 'ru': '{n} ч', 'en': '{n} h'},
    'minutes_left': {'uz': '{n} daqiqa', 'ru': '{n} мин', 'en': '{n} min'},
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
