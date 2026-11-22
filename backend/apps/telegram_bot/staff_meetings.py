"""Meetings in the bot: what a student's change tells their counselor, and the /meetings overview.

Everything here is addressed through the booking's own participant (or the caller's own chat), so one
person's meetings never reach another's chat.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.admissions.meetings import window_summary, within_window
from apps.admissions.models import Booking, MeetingSchedule

from .models import StudentTelegram, TelegramLink
from .services import Refused, resolve_link
from core.public_urls import public_url

# Upcoming meetings sent to the bot; it shows fewer.
MAX_LISTED = 60
CANCELLED_DAYS = 7


def _name(user):
    return (user.get_full_name().strip() or user.username) if user else '—'


def _username(student):
    link = getattr(student, 'student_telegram', None)
    return link.telegram_username if link else ''


def booking_link(user):
    """The page where a student books this staff member (the Meetings page opens their booking dialog)."""
    return public_url(f'/meetings?book={user.pk}')


def queue_staff_update(booking, action):
    """Tell the booking's staff participant what their student just did ('booked', 'cancelled', 'moved',
    'accepted', 'declined'), as a card in their link's language. False when nothing was queued."""
    from .meeting_cards import queue_staff_card

    return queue_staff_card(booking, action)


def _item(booking, who, username=''):
    start = timezone.localtime(booking.starts_at)
    waiting = None
    if booking.status == Booking.Status.PENDING:
        # A staff proposal waits for the student; a student's request waits for the staff member.
        waiting = 'student' if booking.staff_requested else 'staff'
    return {
        'id': booking.pk, 'name': _name(who), 'date': start.date().isoformat(), 'time': start.strftime('%H:%M'),
        'duration_minutes': booking.duration_minutes, 'status': booking.status, 'waiting_for': waiting,
        'topic': booking.topic, 'telegram_username': username,
    }


def _staff_overview(user):
    now = timezone.now()
    base = Booking.objects.filter(participant=user, student__school_id=user.school_id) if user.school_id else Booking.objects.none()
    upcoming = within_window(
        base.filter(status__in=Booking.OPEN_STATUSES, starts_at__gt=now), [user.pk],
    ).select_related('student__user__student_telegram').order_by('starts_at', 'id')
    rows = list(upcoming[:MAX_LISTED])
    summary = window_summary(user)
    schedule = MeetingSchedule.objects.filter(participant=user).first()
    waiting = upcoming.filter(status=Booking.Status.PENDING)
    return {
        'role': 'staff',
        'timezone': settings.TIME_ZONE,
        'booking_url': booking_link(user),
        'meetings': [_item(row, row.student.user, _username(row.student.user)) for row in rows],
        'counts': {
            'booked': summary['upcoming_booked'],
            'waiting_for_you': waiting.filter(staff_requested=False).count(),
            'waiting_for_student': waiting.filter(staff_requested=True).count(),
            'cancelled_week': base.filter(
                status=Booking.Status.CANCELLED, updated_at__gte=now - timedelta(days=CANCELLED_DAYS),
            ).count(),
        },
        'free_slots': summary['free_slots'],
        'settings': None if schedule is None else {
            'duration_minutes': schedule.duration_minutes, 'min_notice_hours': schedule.min_notice_hours,
            'window_mode': schedule.window_mode, 'window_days': schedule.window_days,
            'window_start': schedule.window_start.isoformat() if schedule.window_start else None,
            'window_end': schedule.window_end.isoformat() if schedule.window_end else None,
        },
    }


def _student_overview(user):
    rows = list(
        Booking.objects.filter(student__user=user, status__in=Booking.OPEN_STATUSES, starts_at__gt=timezone.now())
        .select_related('participant').order_by('starts_at', 'id')[:MAX_LISTED]
    )
    return {'role': 'student', 'timezone': settings.TIME_ZONE, 'meetings': [_item(row, row.participant) for row in rows]}


def meetings_overview(chat_id):
    """The chat's own upcoming meetings: a staff member's (with counts and settings) or a student's."""
    if TelegramLink.objects.filter(chat_id=chat_id).exists():
        return _staff_overview(resolve_link(chat_id).user)
    link = StudentTelegram.objects.select_related('user').filter(chat_id=chat_id, is_active=True, user__is_active=True).first()
    if link is None:
        raise Refused('not_linked', 404)
    return _student_overview(link.user)
