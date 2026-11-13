"""Meeting emails: one short message per event, sent to the address a person connected on Meetings.

Requests never talk to the mail server. They queue a ``MeetingEmail`` row in their own
transaction (``queue_meeting_email``); the hourly reminder job queues reminders the same way.
``deliver_queued_emails`` sends what is queued within a time budget; the counselor bot asks the
backend for that every minute (``POST /api/bot/meeting-emails/``), and
``manage.py send_meeting_emails`` does the same by hand or from a cron.
"""
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.utils import timezone

from apps.users.localization import localized_message

logger = logging.getLogger(__name__)
CONSOLE_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# In-app notification title -> email event; other titles (e.g. "Meeting completed") send no email.
EVENTS = {
    'New meeting request': 'requested',
    'Meeting confirmed': 'confirmed',
    'Meeting rejected': 'declined',
    'Meeting cancelled': 'cancelled',
    'Meeting reschedule requested': 'move_requested',
    'Meeting moved': 'moved',
}


def meeting_address(user):
    """Where meeting emails for `user` go: the connected Google address, else a real account email."""
    if user.google_email:
        return user.google_email
    return '' if user.email.endswith(f'@{settings.PLACEHOLDER_EMAIL_DOMAIN}') else user.email


def deliverable_address(recipient):
    """The address an email to `recipient` would really reach, or '' when none would be sent."""
    address = recipient and meeting_address(recipient)
    # The console backend delivers nothing; outside DEBUG it would only fill the logs with names.
    if not address or (settings.EMAIL_BACKEND == CONSOLE_BACKEND and not settings.DEBUG):
        return ''
    return address


def _one_line(value):
    # Names land in the subject, where a line break makes Django refuse the whole message.
    return ' '.join(str(value).split())


def meeting_message(booking, recipient, event, language=None, connection=None):
    """The email to `recipient` about `booking`, or None when they have no address that would reach them."""
    # No per-user language is stored, so mail goes out in the product's default language (Uzbek).
    language = language or settings.LANGUAGE_CODE
    address = deliverable_address(recipient)
    if not address:
        return None
    student = booking.student.user
    other = booking.participant if recipient.pk == student.pk else student
    values = {
        'name': _one_line(recipient.first_name or recipient.username),
        'other': _one_line(other.get_full_name() or other.username) if other else '—',
        'topic': booking.topic,
        'time': timezone.localtime(booking.starts_at).strftime('%d.%m.%Y %H:%M'),
        'minutes': booking.duration_minutes,
        'link': f'{settings.FRONTEND_URL}/meetings',
    }
    return EmailMessage(
        _one_line(localized_message(f'meeting_email_{event}_subject', language=language).format(**values)),
        localized_message(f'meeting_email_{event}', language=language).format(**values)
        + localized_message('meeting_email_details', language=language).format(**values),
        settings.DEFAULT_FROM_EMAIL,
        [address],
        connection=connection,
    )


def send_meeting_email(booking, recipient, event, language=None):
    """Email `recipient` about `booking` now; True when it went out. Never raises."""
    try:
        message = meeting_message(booking, recipient, event, language)
        if message is None:
            return False
        message.send()
    except Exception:  # noqa: BLE001 - any mail problem (SMTP, headers, backend) is logged, never raised
        logger.warning('Meeting email (%s) failed for booking %s', event, booking.pk, exc_info=True)
        return False
    return True


def queue_meeting_email(booking, recipient, title, request):
    """Queue the email matching an in-app notification `title`, in the request's own transaction.

    Only the other side is emailed: whoever made the change already knows. Nothing is sent here:
    a rolled-back change leaves no email behind, and a slow mail server never holds the request.
    """
    from .models import MeetingEmail

    event = EVENTS.get(title)
    if event and recipient and recipient.pk != request.user.pk and deliverable_address(recipient):
        MeetingEmail.objects.create(booking=booking, recipient=recipient, event=event, meeting_start=booking.starts_at)


# --- sending the queue ----------------------------------------------------------------------

# Rows handed out per call; the time budget usually ends a call first when the server is slow.
SEND_BATCH = 50
MAX_ATTEMPTS = 5
# A row still "sending" after this was interrupted (worker killed, deploy): dropped, never resent,
# since the mail server may already have taken it. Far above any request's lifetime.
INTERRUPTED_AFTER = timedelta(minutes=10)
# An event email not sent within a day is no longer news.
MAX_AGE = timedelta(days=1)
# Sent and dropped rows are kept this long for support questions, then deleted.
KEEP_FOR = timedelta(days=7)


def _retry_delay(attempts):
    return timedelta(minutes=2 ** min(attempts, 6))


def _tidy(now):
    from .models import MeetingEmail

    open_rows = MeetingEmail.objects.filter(sent_at__isnull=True, dropped_at__isnull=True)
    interrupted = open_rows.filter(sending_at__lt=now - INTERRUPTED_AFTER).update(dropped_at=now)
    if interrupted:
        logger.warning('%s meeting emails were interrupted while sending; dropped so none goes out twice', interrupted)
    too_old = open_rows.filter(sending_at__isnull=True, created_at__lt=now - MAX_AGE).update(dropped_at=now)
    MeetingEmail.objects.filter(created_at__lt=now - KEEP_FOR).exclude(sent_at__isnull=True, dropped_at__isnull=True).delete()
    return interrupted + too_old


def _stale(row, now):
    """A reminder for a meeting that was since cancelled, moved or has begun."""
    booking = row.booking
    if row.event != 'reminder':
        return False
    from .models import Booking

    return booking.status != Booking.Status.APPROVED or booking.starts_at != row.meeting_start or booking.starts_at <= now


def deliver_queued_emails(*, budget=None, limit=SEND_BATCH, clock=time.monotonic):
    """Send queued meeting emails until `limit` rows or `budget` seconds are used up.

    Returns counts: sent, failed (tried again later), dropped, and how many are still waiting.
    Each row is claimed with a committed update before it is sent, so two callers never send
    the same row and a crash mid-send never sends it twice. Must not run inside a transaction.
    """
    from .models import MeetingEmail

    budget = settings.MEETING_EMAIL_SEND_SECONDS if budget is None else budget
    started = clock()
    now = timezone.now()
    counts = {'sent': 0, 'failed': 0, 'dropped': _tidy(now)}
    due = MeetingEmail.objects.filter(
        sent_at__isnull=True, dropped_at__isnull=True, sending_at__isnull=True, send_after__lte=now,
    )
    rows = list(
        due.select_related('booking__student__user', 'booking__participant', 'recipient').order_by('send_after', 'id')[:limit]
    )
    connection = None
    try:
        for row in rows:
            if clock() - started >= budget:
                break
            claimed = MeetingEmail.objects.filter(
                pk=row.pk, sending_at__isnull=True, sent_at__isnull=True, dropped_at__isnull=True,
            ).update(sending_at=timezone.now())
            if not claimed:
                continue  # another caller took it
            outcome = _send_row(row, connection or (connection := get_connection()))
            counts[outcome] += 1
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 - closing a broken connection may fail too
                pass
    counts['waiting'] = due.count()
    return counts


def _send_row(row, connection):
    from .models import MeetingEmail

    now = timezone.now()
    try:
        message = None if _stale(row, now) else meeting_message(row.booking, row.recipient, row.event, connection=connection)
        if message is None:
            MeetingEmail.objects.filter(pk=row.pk).update(dropped_at=now)
            return 'dropped'
        message.send()
    except Exception:  # noqa: BLE001 - any mail problem is logged and tried again later
        logger.warning('Meeting email (%s) failed for booking %s', row.event, row.booking_id, exc_info=True)
        # A broken connection is opened again for the next row.
        try:
            connection.close()
        except Exception:  # noqa: BLE001
            pass
        attempts = row.attempts + 1
        if attempts >= MAX_ATTEMPTS:
            MeetingEmail.objects.filter(pk=row.pk).update(attempts=attempts, dropped_at=now)
            return 'dropped'
        MeetingEmail.objects.filter(pk=row.pk).update(
            attempts=attempts, sending_at=None, send_after=now + _retry_delay(attempts),
        )
        return 'failed'
    MeetingEmail.objects.filter(pk=row.pk).update(sent_at=timezone.now())
    return 'sent'


def telegram_after_commit(booking, recipient, title, request):
    """The Telegram message matching an in-app notification `title`, for a student who linked the bot."""
    event = EVENTS.get(title)
    if event and recipient and recipient.pk != request.user.pk:
        from apps.telegram_bot.student_link import queue_event

        transaction.on_commit(lambda: queue_event(booking, recipient, event), robust=True)
