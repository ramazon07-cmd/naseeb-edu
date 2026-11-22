"""Post-meeting follow-up for counselors, in Telegram.

Ten minutes after an approved meeting starts, the counselor gets one message about it with two buttons,
"Done" and "Canceled" (``queue_followups``, run with the reminders). Pressing one calls ``perform_followup``:

* Done marks the meeting completed, through the website's own ``complete`` action.
* Canceled marks it cancelled by staff and asks for a note; the counselor's next text in the chat is saved
  on ``Booking.staff_note`` (``save_note``). The wait is a ``PendingMeetingNote`` row, so it survives a bot
  restart, and it lapses after ``NOTE_TTL``.

A meeting whose status already changed (on the website, or by an earlier tap) is never overwritten: the
counselor is told what it is now.
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.admissions.meeting_service import notice_time, notify_student
from apps.admissions.models import Booking

from .meeting_cards import staff_in_scope, _actor, _escape, _name, _own_booking, _run_view, _status_key, card_text, when_line
from .models import PendingMeetingNote, TelegramLink, TelegramOutbox
from .services import Refused, link_allowed

CALLBACK_PREFIX = 'mf'
ACTIONS = ('done', 'cancel')
FOLLOWUP_DELAY = timedelta(minutes=10)
# After downtime the follow-up is still sent for this long after its moment, then skipped.
FOLLOWUP_GRACE = timedelta(minutes=60)
NOTE_TTL = timedelta(hours=24)
NOTE_LIMIT = 4096

TEXTS = {
    'h_followup': {
        'uz': '📋 Uchrashuv qanday o\'tdi?', 'ru': '📋 Как прошла встреча?', 'en': '📋 How did the meeting go?',
    },
    'b_done': {'uz': '✅ O\'tkazildi', 'ru': '✅ Состоялась', 'en': '✅ Done'},
    'b_canceled': {'uz': '🚫 Bekor qilindi', 'ru': '🚫 Отменена', 'en': '🚫 Canceled'},
    'r_done': {'uz': '✅ O\'tkazilgan deb belgilandi', 'ru': '✅ Отмечена как состоявшаяся', 'en': '✅ Marked as done'},
    'r_canceled': {'uz': '🚫 Bekor qilingan deb belgilandi', 'ru': '🚫 Отмечена как отменённая', 'en': '🚫 Marked as canceled'},
    'r_current': {
        'uz': 'ℹ️ Holat o\'zgargan, hozir: {status}', 'ru': 'ℹ️ Статус уже изменён, сейчас: {status}',
        'en': 'ℹ️ Status already changed, now: {status}',
    },
    'r_same': {'uz': 'ℹ️ Allaqachon: {status}', 'ru': 'ℹ️ Уже: {status}', 'en': 'ℹ️ Already: {status}'},
    'ask_note': {
        'uz': 'Nima uchun bekor qilindi? Izohni bitta xabar bilan yozing (ixtiyoriy). O\'tkazib yuborish: /cancel',
        'ru': 'Почему встреча отменена? Напишите заметку одним сообщением (по желанию). Пропустить: /cancel',
        'en': 'Why was it canceled? Reply with a note in one message (optional). Skip: /cancel',
    },
    'note_saved': {'uz': '📝 Izoh saqlandi.', 'ru': '📝 Заметка сохранена.', 'en': '📝 Note saved.'},
}


def followup_text(language, key, **values):
    entry = TEXTS[key]
    return (entry.get(language) or entry['uz']).format(**values)


def followup_card(booking, language):
    return '\n'.join([
        followup_text(language, 'h_followup'), f'<b>{_escape(_name(booking.student.user))}</b>',
        when_line(booking, language), _escape(booking.topic),
    ])


def followup_buttons(booking, language):
    return [[
        {'text': followup_text(language, 'b_done'), 'callback_data': f'{CALLBACK_PREFIX}:done:{booking.pk}'},
        {'text': followup_text(language, 'b_canceled'), 'callback_data': f'{CALLBACK_PREFIX}:cancel:{booking.pk}'},
    ]]


def queue_followups(now=None):
    """One follow-up per approved meeting, FOLLOWUP_DELAY after it starts, for a counselor with an active
    Telegram link. The outbox key makes it once-only, however often this runs or the process restarts."""
    now = now or timezone.now()
    bookings = Booking.objects.filter(
        status=Booking.Status.APPROVED, participant__telegram_link__is_active=True,
        starts_at__lte=now - FOLLOWUP_DELAY, starts_at__gt=now - FOLLOWUP_DELAY - FOLLOWUP_GRACE,
    ).select_related(
        'student__user', 'participant__telegram_link', 'participant__school', 'participant__supervising_counselor',
    )
    queued = 0
    for booking in bookings:
        link = booking.participant.telegram_link
        if not link_allowed(link) or not staff_in_scope(booking):
            continue
        key = f'meeting:{booking.pk}:{int(booking.starts_at.timestamp())}:followup:staff'
        _, created = TelegramOutbox.objects.get_or_create(key=key, defaults={
            'chat_id': link.chat_id, 'booking': booking, 'text': followup_card(booking, link.language),
            'buttons': followup_buttons(booking, link.language),
        })
        queued += int(created)
    return queued


# --- button presses -------------------------------------------------------------------------

def _staff_booking(chat_id, booking_id):
    user, role, language = _actor(chat_id)
    if role != 'staff':
        raise Refused('not_allowed', 403)
    booking = _own_booking(user, role, booking_id)
    if booking is None:
        # Not this chat's meeting: a plain 404, so nothing about it leaks.
        raise Refused('not_found', 404)
    return user, language, booking


def _reply(booking, language, result, line, alert=None, ask_note=False):
    return {
        'result': result, 'alert': alert,
        'text': f'{followup_card(booking, language)}\n\n{line}', 'buttons': [],
        'prompt': followup_text(language, 'ask_note') if ask_note else None,
    }


def _current(booking, language, same_status=None):
    status = card_text(language, _status_key(booking, 'staff'))
    key = 'r_same' if booking.status == same_status else 'r_current'
    line = followup_text(language, key, status=status)
    return line


def _pending(chat_id, booking):
    return PendingMeetingNote.objects.filter(
        chat_id=chat_id, booking=booking, expires_at__gt=timezone.now(),
    ).exists()


def perform_followup(chat_id, booking_id, action):
    """Run a follow-up button for the chat's own meeting.

    Returns {'result': 'done'|'already'|'unavailable', 'alert', 'text', 'buttons', 'prompt'}: the message
    redrawn with a result line, and `prompt` (the note question) right after a cancel.
    """
    if action not in ACTIONS:
        raise Refused('invalid_action', 400)
    user, language, booking = _staff_booking(chat_id, booking_id)
    target = Booking.Status.COMPLETED if action == 'done' else Booking.Status.CANCELLED
    if booking.status == target:
        line = _current(booking, language, same_status=target)
        ask = action == 'cancel' and _pending(chat_id, booking)
        return _reply(booking, language, 'already', line, alert=line, ask_note=ask)
    if booking.status != Booking.Status.APPROVED:
        line = _current(booking, language)
        return _reply(booking, language, 'unavailable', line, alert=line)
    if action == 'done':
        response = _run_view(user, 'complete', booking.pk)
        booking = Booking.objects.select_related('student__user', 'participant').get(pk=booking.pk)
        if response.status_code >= 400 or booking.status != target:
            line = _current(booking, language)
            return _reply(booking, language, 'unavailable', line, alert=line)
        return _reply(booking, language, 'done', followup_text(language, 'r_done'))
    with transaction.atomic():
        locked = Booking.objects.select_for_update(of=('self',)).select_related('student__user', 'participant').get(pk=booking.pk)
        if locked.status != Booking.Status.APPROVED:
            # Changed on the website between the read above and now: never overwrite it.
            line = _current(locked, language, same_status=target)
            return _reply(locked, language, 'already' if locked.status == target else 'unavailable', line, alert=line)
        locked.status = Booking.Status.CANCELLED
        locked.cancelled_by_role = 'staff'
        locked.save(update_fields=['status', 'cancelled_by_role', 'updated_at'])
        PendingMeetingNote.objects.update_or_create(
            chat_id=chat_id, defaults={'booking': locked, 'expires_at': timezone.now() + NOTE_TTL},
        )
        participant_name = _name(locked.participant)
        notify_student(
            locked, 'Meeting cancelled',
            f'Your meeting with {participant_name} on {notice_time(locked.starts_at)} was cancelled.', user,
        )
    return _reply(locked, language, 'done', followup_text(language, 'r_canceled'), ask_note=True)


def save_note(chat_id, note):
    """The counselor's text after pressing Canceled. {'result': 'saved', 'text'} or {'result': 'none'} when
    no cancel is waiting for a note (or it lapsed), so an unrelated message is never saved as one."""
    note = (note or '').strip()
    user, role, language = _actor(chat_id)
    if role != 'staff' or not note:
        return {'result': 'none'}
    now = timezone.now()
    PendingMeetingNote.objects.filter(expires_at__lte=now).delete()
    with transaction.atomic():
        pending = PendingMeetingNote.objects.select_for_update().filter(chat_id=chat_id).first()
        if pending is None:
            return {'result': 'none'}
        booking = Booking.objects.select_related('student', 'participant').get(pk=pending.booking_id)
        pending.delete()
        if booking.participant_id != user.pk or not staff_in_scope(booking) or booking.status != Booking.Status.CANCELLED:
            return {'result': 'none'}
        booking.staff_note = note[:NOTE_LIMIT]
        booking.save(update_fields=['staff_note', 'updated_at'])
    return {'result': 'saved', 'text': followup_text(language, 'note_saved')}


def dismiss_note(chat_id):
    """The counselor chose not to write the note: forget the wait. {'dismissed': True} if one was pending."""
    deleted, _ = PendingMeetingNote.objects.filter(chat_id=chat_id, expires_at__gt=timezone.now()).delete()
    PendingMeetingNote.objects.filter(chat_id=chat_id).delete()
    return {'dismissed': bool(deleted)}
