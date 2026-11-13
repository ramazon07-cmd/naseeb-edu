"""Meeting notices and staff-created meetings, shared by the bookings API and the book_meetings command."""
from datetime import timedelta
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers as drf_serializers

from apps.users.models import User

from .meeting_mail import email_after_commit, telegram_after_commit
from .meetings import MEETING_DURATIONS, overlapping
from .models import Booking, MeetingAvailability, Notification


def notice_time(value):
    # Readers may sit in another zone; the notice text says which clock it uses.
    return f"{timezone.localtime(value).strftime('%d %b %Y, %H:%M')} (Tashkent time)"


def notify_student(booking, title, message, actor):
    """The student's feed row (also the assigned counselor's feed), plus their email and Telegram."""
    Notification.objects.create(student=booking.student, title=title, message=message, kind=Notification.Kind.MEETING)
    request = SimpleNamespace(user=actor)
    email_after_commit(booking, booking.student.user, title, request)
    telegram_after_commit(booking, booking.student.user, title, request)


def notify_participant(booking, title, message, actor):
    """A separate row addressed to the staff member: their bell never touches the student's feed."""
    if booking.participant_id:
        Notification.objects.create(
            student=booking.student, recipient_id=booking.participant_id,
            title=title, message=message, kind=Notification.Kind.MEETING, target_id=booking.pk,
        )
        email_after_commit(booking, booking.participant, title, SimpleNamespace(user=actor))


def covering_slot(staff, start, duration):
    """The staff member's own slot this time falls on (same start first, else one that contains it), if any."""
    end = start + timedelta(minutes=duration)
    exact = MeetingAvailability.objects.filter(participant=staff, starts_at=start).first()
    if exact:
        return exact
    for slot in MeetingAvailability.objects.filter(participant=staff, starts_at__lte=start, starts_at__gt=start - timedelta(hours=3)):
        if slot.starts_at + timedelta(minutes=slot.duration_minutes) >= end:
            return slot
    return None


def create_staff_booking(staff, profile, *, starts_at, duration_minutes=45, topic, notes='', ask_student=True):
    """Book `profile` with `staff`; returns the booking, or raises a DRF ValidationError.

    `ask_student` (the default): the meeting waits as PENDING for the student to confirm it. Otherwise it
    is confirmed at once and the student is only told. A slot of the staff member's that covers the time
    is taken by the booking, so no other student can claim it. Staff are not held to the students'
    minimum notice.
    """
    if duration_minutes not in MEETING_DURATIONS:
        raise drf_serializers.ValidationError({'duration_minutes': 'Choose a 30, 45, or 60 minute meeting.'})
    if starts_at <= timezone.now():
        raise drf_serializers.ValidationError({'starts_at': 'Choose a future meeting date and time.'})
    with transaction.atomic():
        # Same per-staff lock as availability and student claims.
        User.objects.select_for_update().get(pk=staff.pk)
        if overlapping(Booking.objects.filter(participant=staff, status__in=Booking.OPEN_STATUSES), starts_at, duration_minutes):
            raise drf_serializers.ValidationError({'starts_at': 'This time overlaps another meeting.'})
        slot = covering_slot(staff, starts_at, duration_minutes)
        booking = Booking.objects.create(
            student=profile, participant=staff, availability_slot=slot, topic=topic, notes=notes,
            starts_at=starts_at, duration_minutes=duration_minutes, staff_requested=ask_student,
            status=Booking.Status.PENDING if ask_student else Booking.Status.APPROVED,
        )
        name = staff.get_full_name() or staff.username
        when = notice_time(booking.starts_at)
        if ask_student:
            notify_student(
                booking, 'Meeting invitation',
                f'{name} invited you to "{booking.topic}" on {when}. Confirm it on the website.', staff,
            )
        else:
            notify_student(booking, 'Meeting confirmed', f'{name} booked "{booking.topic}" with you on {when}.', staff)
    return booking
