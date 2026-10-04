"""Meeting time rules shared by booking requests and staff availability."""
import math
from datetime import timedelta

from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from .models import Booking, MeetingAvailability

MEETING_DURATIONS = (30, 45, 60)
MAX_MEETING_MINUTES = max(MEETING_DURATIONS)
# Each staff member's next slots; a busy colleague cannot crowd out the rest.
SLOTS_PER_PARTICIPANT = 200


def overlapping(qs, start, duration_minutes, exclude_pk=None):
    """Rows of `qs` (meetings or slots) whose time overlaps [start, start + duration)."""
    rows = qs.filter(
        starts_at__lt=start + timedelta(minutes=duration_minutes),
        starts_at__gt=start - timedelta(minutes=MAX_MEETING_MINUTES),
    )
    if exclude_pk is not None:
        rows = rows.exclude(pk=exclude_pk)
    return [row for row in rows if row.starts_at + timedelta(minutes=row.duration_minutes) > start]


def upcoming_slots(qs):
    """Future slots from `qs`, at most SLOTS_PER_PARTICIPANT per staff member, earliest first."""
    return list(
        qs.filter(starts_at__gt=timezone.now())
        .annotate(position=Window(RowNumber(), partition_by=F('participant_id'), order_by=F('starts_at').asc()))
        .filter(position__lte=SLOTS_PER_PARTICIPANT)
        .order_by('starts_at', 'id')
    )


def with_availability(slots):
    """(slot, free) pairs: free when no open meeting of that staff member overlaps the slot."""
    if not slots:
        return []
    first = min(slot.starts_at for slot in slots)
    last_end = max(slot.starts_at + timedelta(minutes=slot.duration_minutes) for slot in slots)
    meetings = overlapping(
        Booking.objects.filter(participant_id__in={slot.participant_id for slot in slots}, status__in=Booking.OPEN_STATUSES),
        first, math.ceil((last_end - first).total_seconds() / 60),
    )

    def is_free(slot):
        end = slot.starts_at + timedelta(minutes=slot.duration_minutes)
        return not any(
            meeting.participant_id == slot.participant_id
            and meeting.starts_at < end
            and meeting.starts_at + timedelta(minutes=meeting.duration_minutes) > slot.starts_at
            for meeting in meetings
        )
    return [(slot, is_free(slot)) for slot in slots]


def has_open_slot(participant_id):
    """Whether a student must pick one of this staff member's slots (else any time is fine)."""
    slots = upcoming_slots(MeetingAvailability.objects.filter(participant_id=participant_id))
    return any(free for _, free in with_availability(slots))
