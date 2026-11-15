"""Meeting time rules shared by booking requests and staff availability."""
import math
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import (
    DateTimeField, DurationField, Exists, ExpressionWrapper, F, Func, IntegerField, OuterRef, Q, Subquery, Value, Window,
)
from django.db.models.functions import Coalesce, RowNumber
from django.utils import timezone

from .models import Booking, MeetingAvailability, MeetingSchedule

MEETING_DURATIONS = (15, 20, 30, 45, 60, 90)
MAX_MEETING_MINUTES = max(MEETING_DURATIONS)
# "Repeat weekly" covers at most this many days, so one request adds at most ~85 slots.
MAX_REPEAT_DAYS = 12 * 7
# One request may add at most this many times (a 12-week range of full days would be thousands).
MAX_REPEAT_SLOTS = 400
# Each staff member's next slots; a busy colleague cannot crowd out the rest.
# (A 90-day horizon of 10 slots a day fits.)
SLOTS_PER_PARTICIPANT = 1000
# Weekly hours are turned into dated slots this far ahead (never past the booking window), topped up once less than a week short.
SCHEDULE_DAYS = 90
# A student's all-staff overview: the next few free times of each staff member, and a hard total.
# The student's picker then loads the chosen person's full list.
OVERVIEW_SLOTS_PER_PARTICIPANT = 20
MAX_OVERVIEW_SLOTS = 2000
# How far ahead a student must book when the staff member set no minimum of their own.
DEFAULT_MIN_NOTICE_HOURS = 12
MAX_MIN_NOTICE_HOURS = 168


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


def min_notice_hours(participant_id):
    """How many hours ahead a student must book this staff member (the default until they set it)."""
    value = MeetingSchedule.objects.filter(participant_id=participant_id).values_list('min_notice_hours', flat=True).first()
    return DEFAULT_MIN_NOTICE_HOURS if value is None else value


def too_soon_for_student(participant_id, starts_at, now=None):
    """True when a student may not take a slot starting at `starts_at` with this staff member."""
    return starts_at < (now or timezone.now()) + timedelta(hours=min_notice_hours(participant_id))


def notice_message(participant_id):
    hours = min_notice_hours(participant_id)
    return f'Meetings must be booked at least {hours} hour{"" if hours == 1 else "s"} ahead. Choose a later time.'


def respecting_notice(qs, now=None):
    """Slots of `qs` that start at least their staff member's minimum notice from now (what a student may book)."""
    notice = Coalesce(
        Subquery(MeetingSchedule.objects.filter(participant_id=OuterRef('participant_id')).values('min_notice_hours')[:1]),
        Value(DEFAULT_MIN_NOTICE_HOURS), output_field=IntegerField(),
    )
    earliest = ExpressionWrapper(
        Value(now or timezone.now(), output_field=DateTimeField()) + _Minutes(F('notice_hours') * 60),
        output_field=DateTimeField(),
    )
    return qs.annotate(notice_hours=notice).filter(starts_at__gte=earliest)


def window_dates(schedule, today=None):
    """(first, last) Tashkent dates, inclusive, students may book under this schedule; first may be past `last` once a range has ended."""
    today = today or timezone.localdate()
    if schedule.window_mode == MeetingSchedule.WindowMode.RANGE and schedule.window_start and schedule.window_end:
        return max(today, schedule.window_start), schedule.window_end
    return today, today + timedelta(days=schedule.window_days)


def _day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def window_bounds(participant_ids, today=None):
    """{participant id: (start, end) datetimes, end exclusive} for staff with a schedule; others have no limit."""
    bounds = {}
    for schedule in MeetingSchedule.objects.filter(participant_id__in=list(participant_ids)):
        first, last = window_dates(schedule, today)
        bounds[schedule.participant_id] = (_day_start(first), _day_start(last + timedelta(days=1)))
    return bounds


def within_window(qs, participant_ids, today=None):
    """Rows of `qs` (slots or meetings) inside their staff member's booking window; staff without a schedule are unlimited."""
    participant_ids = list(participant_ids)
    bounds = window_bounds(participant_ids, today)
    by_bounds = {}
    for participant_id, span in bounds.items():
        by_bounds.setdefault(span, []).append(participant_id)
    keep = Q(participant_id__in=[pid for pid in participant_ids if pid not in bounds])
    for (start, end), ids in by_bounds.items():
        keep |= Q(participant_id__in=ids, starts_at__gte=start, starts_at__lt=end)
    return qs.filter(keep)


def outside_window(participant_id, starts_at):
    """True when a student may not book `starts_at` with this staff member because it is past their booking window."""
    span = window_bounds([participant_id]).get(participant_id)
    return span is not None and not span[0] <= starts_at < span[1]


def window_summary(user):
    """Open meetings and free slots still ahead inside `user`'s booking window (the counselor's tally)."""
    now = timezone.now()
    booked = within_window(
        Booking.objects.filter(participant=user, status__in=Booking.OPEN_STATUSES, starts_at__gt=now), [user.pk],
    ).count()
    free = free_slots(within_window(MeetingAvailability.objects.filter(participant=user, starts_at__gt=now), [user.pk])).count()
    return {'upcoming_booked': booked, 'free_slots': free}


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
                if until <= time:
                    end += timedelta(days=1)  # a range ending at 00:00 runs to midnight
                while start + timedelta(minutes=step) <= end:
                    yield start
                    start += timedelta(minutes=step)
        day += timedelta(days=1)


def add_free_slots(user, starts, duration, **fields):
    """Create slots at the future `starts` that overlap none of `user`'s slots or open meetings.

    The caller holds the per-staff lock (`select_for_update` on the user) inside a transaction.
    """
    now = timezone.now()
    future = [start for start in starts if start > now]
    if not future:
        return []
    # One read of the whole range (slots and open meetings), then checks in memory.
    first = min(future)
    span = math.ceil((max(future) - first).total_seconds() / 60) + duration
    taken = (
        overlapping(MeetingAvailability.objects.filter(participant=user), first, span)
        + overlapping(Booking.objects.filter(participant=user, status__in=Booking.OPEN_STATUSES), first, span)
    )
    created = []
    for start in future:
        if not clashes(taken, start, duration):
            slot = MeetingAvailability(participant=user, starts_at=start, duration_minutes=duration, **fields)
            created.append(slot)
            taken.append(slot)
    return MeetingAvailability.objects.bulk_create(created)


def fill_schedule(schedule, replace=False, first_day=None, until=None):
    """Generate the weekly hours' slots inside the booking window, at most SCHEDULE_DAYS ahead; the caller holds the per-staff lock.

    `replace` (the hours or window changed): unbooked generated slots are dropped and rebuilt from today,
    so slots outside the new window disappear. Hand-added slots and any slot with an open meeting stay,
    and new slots never overlap them.
    """
    today = timezone.localdate()
    window_first, window_last = window_dates(schedule, today)
    # `first_day` / `until` (the book_meetings command) set the days themselves; the API never passes them.
    until = until or min(today + timedelta(days=SCHEDULE_DAYS), window_last)
    if first_day is None:
        first_day = today if replace or not schedule.generated_until else schedule.generated_until + timedelta(days=1)
        first_day = max(first_day, window_first)
    if replace:
        MeetingAvailability.objects.filter(
            participant=schedule.participant, from_schedule=True, starts_at__gt=timezone.now(),
        ).exclude(bookings__status__in=Booking.OPEN_STATUSES).delete()
    tz = timezone.get_default_timezone()
    starts = [
        start
        for weekday, ranges in schedule.hours.items()
        for begin, end in ranges
        for start in weekly_starts(
            {int(weekday)}, time.fromisoformat(begin), first_day, until, tz,
            until=time.fromisoformat(end), step=schedule.duration_minutes,
        )
    ]
    add_free_slots(schedule.participant, starts, schedule.duration_minutes, from_schedule=True)
    schedule.generated_until = until
    schedule.save(update_fields=['generated_until', 'updated_at'])


def _generation_target(schedule, today):
    """The last day slots should exist for: the window's end, but never more than SCHEDULE_DAYS ahead."""
    return min(today + timedelta(days=SCHEDULE_DAYS), window_dates(schedule, today)[1])


def _needs_top_up(schedule, today):
    # Less than a week short of the target (a window shorter than a week is topped up daily).
    return schedule.generated_until is not None and schedule.generated_until < min(
        _generation_target(schedule, today), today + timedelta(days=SCHEDULE_DAYS - 7),
    )


def top_up_schedules(participant_ids):
    """Extend the generated slots of these staff members where they run out before their window (or the horizon) does.

    One query finds who is short (usually nobody); each of those is filled under their own lock.
    """
    today = timezone.localdate()
    due = [
        schedule.participant_id
        for schedule in MeetingSchedule.objects.filter(participant_id__in=list(participant_ids), generated_until__isnull=False)
        if _needs_top_up(schedule, today)
    ]
    for participant_id in due:
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=participant_id)
            schedule = MeetingSchedule.objects.get(participant_id=participant_id)
            if _needs_top_up(schedule, today):
                fill_schedule(schedule)


def top_up_schedule(participant_id):
    """Extend one staff member's generated slots when they run short of their window."""
    top_up_schedules([participant_id])
