"""Meeting emails: one short message per event, sent to the address a person connected on Meetings."""
import logging
from smtplib import SMTPException

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


def send_meeting_email(booking, recipient, event, language=None):
    """Email `recipient` about `booking`; True when it went out. A mail failure never fails the meeting."""
    # No per-user language is stored, so mail goes out in the product's default language (Uzbek).
    language = language or settings.LANGUAGE_CODE
    address = recipient and meeting_address(recipient)
    # The console backend delivers nothing; outside DEBUG it would only fill the logs with names.
    if not address or (settings.EMAIL_BACKEND == CONSOLE_BACKEND and not settings.DEBUG):
        return False
    student = booking.student.user
    other = booking.participant if recipient.pk == student.pk else student
    values = {
        'name': recipient.first_name or recipient.username,
        'other': (other.get_full_name() or other.username) if other else '—',
        'topic': booking.topic,
        'time': timezone.localtime(booking.starts_at).strftime('%d.%m.%Y %H:%M'),
        'minutes': booking.duration_minutes,
        'link': f'{settings.FRONTEND_URL}/meetings',
    }
    try:
        send_mail(
            localized_message(f'meeting_email_{event}_subject', language=language).format(**values),
            localized_message(f'meeting_email_{event}', language=language).format(**values)
            + localized_message('meeting_email_details', language=language).format(**values),
            settings.DEFAULT_FROM_EMAIL,
            [address],
        )
    except (SMTPException, OSError):
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
        transaction.on_commit(lambda: send_meeting_email(booking, recipient, event))
