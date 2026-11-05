"""Meeting time rules shared by booking requests and staff availability."""
import math
from datetime import datetime, timedelta

from django.db.models import DateTimeField, DurationField, Exists, ExpressionWrapper, F, Func, OuterRef, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from .models import Booking

MEETING_DURATIONS = (30, 45, 60)
MAX_MEETING_MINUTES = max(MEETING_DURATIONS)
# "Repeat weekly" covers at most this many days, so one request adds at most ~85 slots.
MAX_REPEAT_DAYS = 12 * 7
# One request may add at most this many times (a 12-week range of full days would be thousands).
MAX_REPEAT_SLOTS = 400
# Each staff member's next slots; a busy colleague cannot crowd out the rest.
SLOTS_PER_PARTICIPANT = 200
# A student's all-staff overview: the next few free times of each staff member, and a hard total.
# The student's picker then loads the chosen person's full list.
OVERVIEW_SLOTS_PER_PARTICIPANT = 20
MAX_OVERVIEW_SLOTS = 2000


def overlapping(qs, start, duration_minutes, exclude_pk=None):
    """Rows of `qs` (meetings or slots) whose time overlaps [start, start + duration)."""
    rows = qs.filter(
        starts_at__lt=start + timedelta(minutes=duration_minutes),
        starts_at__gt=start - timedelta(minutes=MAX_MEETING_MINUTES),
    )
    if exclude_pk is not None:
        rows = rows.exclude(pk=exclude_pk)
    return [row for row in rows if row.starts_at + timedelta(minutes=row.duration_minutes) > start]


def clashes(rows, start, duration_minutes):
    """True when any of the loaded `rows` overlaps [start, start + duration); `overlapping` without a query."""
    end = start + timedelta(minutes=duration_minutes)
    return any(row.starts_at < end and row.starts_at + timedelta(minutes=row.duration_minutes) > start for row in rows)


class _Minutes(Func):
    """An integer column of minutes as a SQL duration (SQLite stores durations as microseconds)."""

    template = 'make_interval(mins => %(expressions)s)'
    output_field = DurationField()

    def as_sqlite(self, compiler, connection, **extra):
        return self.as_sql(compiler, connection, template='(%(expressions)s * 60000000)', **extra)


def _ends_at():
    return ExpressionWrapper(F('starts_at') + _Minutes(F('duration_minutes')), output_field=DateTimeField())


def free_slots(qs, moving=None):
    """Slots of `qs` that no open meeting of the same staff member overlaps, decided in SQL.

    `moving`: the id of a meeting being rescheduled; its current time does not count as busy.
    """
    busy = Booking.objects.annotate(ends_at=_ends_at()).filter(
        participant_id=OuterRef('participant_id'), status__in=Booking.OPEN_STATUSES,
        starts_at__lt=OuterRef('ends_at'), ends_at__gt=OuterRef('starts_at'),
    ).exclude(pk=moving)
    return qs.annotate(ends_at=_ends_at()).filter(~Exists(busy))


def upcoming_slots(qs, overview=False):
    """Future slots from `qs`, earliest first, at most SLOTS_PER_PARTICIPANT per staff member.

    `overview` (every staff member at once) keeps OVERVIEW_SLOTS_PER_PARTICIPANT each and at most
    MAX_OVERVIEW_SLOTS in total, cut by each person's first slots before anyone's later ones, so
    the total never drops a whole staff member while others keep several.
    """
    per_participant = OVERVIEW_SLOTS_PER_PARTICIPANT if overview else SLOTS_PER_PARTICIPANT
    rows = (
        qs.filter(starts_at__gt=timezone.now())
        .annotate(position=Window(RowNumber(), partition_by=F('participant_id'), order_by=F('starts_at').asc()))
        .filter(position__lte=per_participant)
    )
    if not overview:
        return list(rows.order_by('starts_at', 'id'))
    return sorted(rows.order_by('position', 'starts_at', 'id')[:MAX_OVERVIEW_SLOTS], key=lambda slot: (slot.starts_at, slot.id))


def with_availability(slots, moving=None):
    """(slot, free) pairs: free when no open meeting of that staff member overlaps the slot.

    `moving`: the id of a meeting being rescheduled; its current time does not count as busy.
    """
    if not slots:
        return []
    first = min(slot.starts_at for slot in slots)
    last_end = max(slot.starts_at + timedelta(minutes=slot.duration_minutes) for slot in slots)
    meetings = overlapping(
        Booking.objects.filter(participant_id__in={slot.participant_id for slot in slots}, status__in=Booking.OPEN_STATUSES)
        .exclude(pk=moving),
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


def weekly_starts(weekdays, time, start_date, end_date, tz, until=None, step=None):
    """Start times on the given weekdays (Monday = 0) between two dates inclusive, at `time` in `tz`.

    With `until`, each day is a range: a start every `step` minutes from `time`
    while that slot still ends by `until` (09:00-11:00 at 45 min gives 09:00, 09:45).
    """
    day = start_date
    while day <= end_date:
        if day.weekday() in weekdays:
            start = datetime.combine(day, time, tzinfo=tz)
            if until is None:
                yield start
            else:
                end = datetime.combine(day, until, tzinfo=tz)
                while start + timedelta(minutes=step) <= end:
                    yield start
                    start += timedelta(minutes=step)
        day += timedelta(days=1)
