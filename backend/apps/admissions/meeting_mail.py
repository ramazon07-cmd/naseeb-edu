"""Meeting emails: one short message per event, sent to the address a person connected on Meetings."""
import logging

from django.conf import settings
from django.core.mail import send_mail
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


def send_meeting_email(booking, recipient, event, language=None):
    """Email `recipient` about `booking`; True when it went out. A mail failure never fails the meeting."""
    # No per-user language is stored, so mail goes out in the product's default language (Uzbek).
    language = language or settings.LANGUAGE_CODE
    address = deliverable_address(recipient)
    if not address:
        return False
    try:
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
        send_mail(
            _one_line(localized_message(f'meeting_email_{event}_subject', language=language).format(**values)),
            localized_message(f'meeting_email_{event}', language=language).format(**values)
            + localized_message('meeting_email_details', language=language).format(**values),
            settings.DEFAULT_FROM_EMAIL,
            [address],
        )
    except Exception:  # noqa: BLE001 - any mail problem (SMTP, headers, backend) is logged, never raised
        logger.warning('Meeting email (%s) failed for booking %s', event, booking.pk, exc_info=True)
        return False
    return True


def email_after_commit(booking, recipient, title, request):
    """Queue the email matching an in-app notification `title`, sent once the change is committed.

    Only the other side is emailed: whoever made the change already knows.
    """
    event = EVENTS.get(title)
    if event and recipient and recipient.pk != request.user.pk:
        # shortcut: sent in the request after commit (waits up to EMAIL_TIMEOUT); move to a queue when mail volume grows.
        # robust: the change is already saved, so nothing about the email may turn the response into an error.
        transaction.on_commit(lambda: send_meeting_email(booking, recipient, event), robust=True)


def telegram_after_commit(booking, recipient, title, request):
    """The Telegram message matching an in-app notification `title`, for a student who linked the bot."""
    event = EVENTS.get(title)
    if event and recipient and recipient.pk != request.user.pk:
        from apps.telegram_bot.student_link import queue_event

        transaction.on_commit(lambda: queue_event(booking, recipient, event), robust=True)
