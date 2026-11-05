"""What a counselor's Home and sidebar count.

DashboardStatsView merges ``counselor_summary`` into a counselor's stats, and
``counselor_home`` (``?include=home``) adds everything the Home page shows.
Every queryset here is scoped to the counselor's assigned, active students
(meetings: to the counselor's own bookings in their school, as the Bookings
page lists them), so a number never includes another counselor's or another
school's work. Dates are calendar days in the server's zone (Asia/Tashkent);
a week runs Monday to Sunday.

Every function runs a fixed number of queries whatever the caseload: counts
are aggregates, and only bounded pages of rows are read into Python (except
``student_progress``, whose buckets read one grouped row set per student).
"""
from collections import Counter
from datetime import date, datetime, time, timedelta
from functools import reduce
from operator import or_

from django.db import transaction
from django.db.models import Case, CharField, Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Concat, Lower, NullIf, Trim, TruncDate
from django.utils import timezone

from .models import (
    Achievement,
    ActivityLog,
    Application,
    Booking,
    ChannelMessage,
    Document,
    MeetingNote,
    MessageChannel,
    RecommendationLetter,
    RoadmapMission,
    Task,
)
from .progress import (
    APPLICATION_DONE, DOCUMENT_AWAITING_REVIEW, DOCUMENT_MISSING, OPEN_MISSION_STATUSES, OPEN_TASK_STATUSES, ProgressStats,
    late_tasks, load_progress_stats, percent,
)

DEADLINE_LIMIT = 6
REVIEW_ITEM_LIMIT = 8
NEED_YOU_LIMIT = 6
PROGRESS_LIMIT = 5
# Home lists this many check-in rows; ``?check_ins=all`` pages through the rest.
CHECK_IN_LIMIT = 50
CHECK_IN_MAX_LIMIT = 200
# The check-in heatmap: this many weeks, Monday to Sunday, ending this week.
HISTORY_WEEKS = 12
# "Next priorities" in a student snapshot.
SNAPSHOT_PRIORITY_LIMIT = 3
# Letters the recommender still owes; a submitted or approved one is no deadline.
OPEN_LETTER_STATUSES = (RecommendationLetter.Status.REQUESTED, RecommendationLetter.Status.DRAFTING)
# A meeting that is on the calendar (a rejected or cancelled one is not).
CALENDAR_MEETING_STATUSES = (Booking.Status.PENDING, Booking.Status.APPROVED, Booking.Status.COMPLETED)
HELD_MEETING_STATUSES = (Booking.Status.APPROVED, Booking.Status.COMPLETED)

# A manual check-in is an ActivityLog row, so it needs no table of its own and
# stays in the student's timeline. Rows are never deleted: un-ticking a day
# writes CHECK_IN_OFF, and the latest row for a (student, day) wins.
CHECK_IN_ON = 'Check-in recorded'
CHECK_IN_OFF = 'Check-in removed'
CHECK_IN_EVENT = 'counselor.check_in'
# Timeline rows a counselor causes without working with the student.
NOT_A_CHECK_IN = (
    'Student assigned to counselor', 'Student profile created', 'Student deactivated', 'Student reactivated',
    'Student confirmed',
)

# Student progress buckets (see progress_bucket).
NEEDS_ATTENTION_LATE = 3
NEEDS_ATTENTION_GAP = 25


def week_of(today):
    """Monday..Sunday of the week holding ``today``."""
    start = today - timedelta(days=today.weekday())
    return [start + timedelta(days=offset) for offset in range(7)]


def _day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def _name(row, prefix=''):
    first = row.get(f'{prefix}user__first_name') or ''
    last = row.get(f'{prefix}user__last_name') or ''
    return f'{first} {last}'.strip() or row.get(f'{prefix}user__username') or ''


def review_counts(students, tasks_submitted, documents_waiting, essays_reviewing):
    """Submitted work waiting for the counselor, per kind of the Review page (essays: their own badge).

    Tasks, documents and shared essays are counted by the dashboard already; it passes them in.
    """
    return {
        'tasks': tasks_submitted,
        'documents': documents_waiting,
        'roadmap': RoadmapMission.objects.filter(student__in=students, status=RoadmapMission.Status.SUBMITTED).count(),
        'portfolio': Achievement.objects.filter(student__in=students, verified=False, counselor_comment='').count(),
        'essays': essays_reviewing,
    }


def _attention_sources(today):
    """Why a student needs the counselor, most urgent first: the one rule behind
    ``students_need_you``, Home's "Students who need you" and the check-in order."""
    return (
        ('late_task', Task.objects.filter(late_tasks(today))),
        ('late_mission', RoadmapMission.objects.filter(status__in=OPEN_MISSION_STATUSES, due_date__lt=today)),
        ('missing_document', Document.objects.filter(DOCUMENT_MISSING)),
    )


def _needs_attention(today):
    """A condition on StudentProfile rows: the student has any reason of ``_attention_sources``."""
    return reduce(or_, (Exists(queryset.filter(student=OuterRef('pk'))) for _, queryset in _attention_sources(today)))


def students_needing_attention(students, today):
    """Students with late work or a required document still missing (the Students page's "Need you")."""
    return students.filter(_needs_attention(today))


def _sort_name():
    """``_name`` in SQL, lower-cased: "first last", or the username when both are blank."""
    full = Trim(Concat('user__first_name', Value(' '), 'user__last_name', output_field=CharField()))
    return Lower(Coalesce(NullIf(full, Value('')), 'user__username'))


STUDENT_FIELDS = ('student_id', 'student__user__first_name', 'student__user__last_name', 'student__user__username')


def _deadline(kind, row, title, due, today):
    return {
        'id': f'{kind}-{row["pk"]}',
        'kind': kind,
        'title': title,
        'student': row['student_id'],
        'student_name': _name(row, 'student__'),
        'due': due.isoformat() if due else None,
        # Only a dated item can be late.
        'late': bool(due and due < today),
    }


def _deadline_sources(students):
    """(kind, queryset, date field, title field) of every open, dated piece of work."""
    return (
        ('task', Task.objects.filter(student__in=students, status__in=OPEN_TASK_STATUSES), 'due_date', 'title'),
        ('mission', RoadmapMission.objects.filter(student__in=students, status__in=OPEN_MISSION_STATUSES), 'due_date', 'title'),
        ('application', Application.objects.filter(student__in=students).exclude(status__in=APPLICATION_DONE), 'deadline', 'university__name'),
        ('letter', RecommendationLetter.objects.filter(student__in=students, status__in=OPEN_LETTER_STATUSES), 'deadline', 'recommender_name'),
    )


def week_deadlines(students, today, limit=DEADLINE_LIMIT):
    """Open work due this week (Monday to Sunday), soonest first, and how much is older than that.

    Work that fell due before this week is only counted (``overdue``): left in
    the list, a backlog of old items would push this week's deadlines off it.
    Two queries whatever the sources: one UNION for the list, one for the counts.
    """
    week = week_of(today)
    listed, counted = [], []
    for kind, queryset, date_field, title_field in _deadline_sources(students):
        dated = queryset.filter(**{f'{date_field}__isnull': False}).order_by().annotate(
            kind=Value(kind, output_field=CharField()), due=F(date_field),
            label=Cast(title_field, output_field=CharField()),
        )
        listed.append(dated.filter(due__range=(week[0], week[-1])).values('kind', 'pk', 'label', 'due', *STUDENT_FIELDS))
        counted.append(dated.filter(due__lte=week[-1]).values('kind').annotate(
            overdue=Count('pk', filter=Q(due__lt=week[0])), in_week=Count('pk', filter=Q(due__gte=week[0])),
        ).values('kind', 'overdue', 'in_week'))
    rows = listed[0].union(*listed[1:], all=True).order_by('due', 'kind', 'pk')[:limit]
    totals = list(counted[0].union(*counted[1:], all=True))
    return {
        'items': [_deadline(row['kind'], row, row['label'], row['due'], today) for row in rows],
        'total': sum(row['in_week'] for row in totals),
        'overdue': sum(row['overdue'] for row in totals),
    }


def counselor_bookings(user):
    """The counselor's meetings, exactly as the Bookings page lists them: any
    student of their school may book them, assigned or not."""
    if not user.school_id:
        return Booking.objects.none()
    return Booking.objects.filter(participant=user, student__school_id=user.school_id)


def badges(user, students):
    """The sidebar and bell numbers, cheap enough to poll (2 queries).

    * ``meetings_pending``: requests waiting for the counselor that have not
      started (counselorCounts.js ``pendingMeetings`` over the Bookings list).
    * ``messages_unread``: unread messages over every channel they are in (the
      sum of the channel list's ``unread_count``).
    * ``messages_unread_conversations``: channels with an unread message (the bell).
    * ``messages_unread_students``: their students who sent those messages.
    * ``students_pending``: students who joined by invite and wait for this
      counselor to confirm them (they are in no other count until then).
    """
    from apps.users.models import User

    from .invites import pending_scope
    from .views.messaging import unread_channel_messages

    unread = unread_channel_messages(user).order_by().aggregate(
        total=Count('pk'),
        conversations=Count('channel_id', distinct=True),
        students=Count('sender_id', distinct=True, filter=Q(sender__student_profile__in=students.order_by().values('pk'))),
    )
    meetings = counselor_bookings(user).filter(status=Booking.Status.PENDING, starts_at__gt=timezone.now())
    # Both counts in one round trip, as scalar subqueries.
    meetings_pending, students_pending = User.objects.filter(pk=user.pk).annotate(
        meetings=_scalar_count(meetings), pending=_scalar_count(pending_scope(user)),
    ).values_list('meetings', 'pending').get()
    return {
        'meetings_pending': meetings_pending,
        'messages_unread': unread['total'],
        'messages_unread_conversations': unread['conversations'],
        'messages_unread_students': unread['students'],
        'students_pending': students_pending,
    }


def _scalar_count(queryset):
    """``(SELECT COUNT(*) FROM queryset)`` as an expression (COUNT as a plain
    function, so the subquery has no GROUP BY and always yields one row)."""
    from django.db.models import Func

    return Subquery(
        queryset.order_by().annotate(n=Func(F('pk'), function='COUNT')).values('n')[:1],
        output_field=IntegerField(),
    )


def counselor_summary(user, students, today, *, tasks_submitted, documents_waiting, essays_reviewing, include_home=False):
    """The extra dashboard-stats fields of a counselor: review counts, who needs them, what is due.

    With ``include_home`` it adds ``home`` (see ``counselor_home``), reusing
    what both share, so the plain fields are identical either way.
    """
    deadlines = week_deadlines(students, today)
    badge_counts = badges(user, students)
    need_you = need_you_list(students, today) if include_home else None
    summary = {
        'review': review_counts(students, tasks_submitted, documents_waiting, essays_reviewing),
        'students_need_you': need_you['total'] if need_you is not None else students_needing_attention(students, today).count(),
        'deadlines': deadlines['items'],
        'deadlines_overdue': deadlines['overdue'],
        'deadlines_week_total': deadlines['total'],
        'badges': badge_counts,
    }
    if include_home:
        summary['home'] = counselor_home(user, students, today, deadlines=deadlines, need_you=need_you, badge_counts=badge_counts)
    return summary


# -- Home --------------------------------------------------------------------

def review_items(students, limit=REVIEW_ITEM_LIMIT):
    """The oldest work waiting for review, across the Review page's kinds.

    ``id`` is the Review page's own item id (``kind-recordId``) and ``at`` the
    moment it uses for "oldest first", so a click opens the same item.
    Roadmap is closed in this workspace: exclude it before applying the limit,
    so hidden missions cannot push visible tasks out of Home's first page.
    """
    sources = (
        ('task', Task.objects.filter(student__in=students, status=Task.Status.SUBMITTED)
         .annotate(at=Coalesce('submitted_at', 'updated_at'))),
        ('document', Document.objects.filter(DOCUMENT_AWAITING_REVIEW, student__in=students).annotate(at=F('updated_at'))),
        ('portfolio', Achievement.objects.filter(student__in=students, verified=False, counselor_comment='').annotate(at=F('created_at'))),
    )
    items = []
    for kind, queryset in sources:
        for row in queryset.order_by('at', 'pk').values('pk', 'title', 'at', *STUDENT_FIELDS)[:limit]:
            items.append({
                'id': f'{kind}-{row["pk"]}',
                'kind': kind,
                'record_id': row['pk'],
                'title': row['title'],
                'student': row['student_id'],
                'student_name': _name(row, 'student__'),
                'at': row['at'].isoformat(),
            })
    items.sort(key=lambda item: (item['at'], item['id']))
    return items[:limit]


def _count_of(queryset):
    """Per-student row count of ``queryset`` as a StudentProfile annotation."""
    return Coalesce(Subquery(
        queryset.filter(student=OuterRef('pk')).order_by().values('student').annotate(n=Count('pk')).values('n'),
        output_field=IntegerField(),
    ), 0)


def need_you_list(students, today):
    """"Students who need you": how many, and the most urgent few with their reasons.

    The same rule and the same queryset as ``students_need_you``. Most reasons
    first, then most late items, then by name.
    """
    needing = students_needing_attention(students, today)
    counts = {f'{key}_n': _count_of(queryset) for key, queryset in _attention_sources(today)}
    first_missing = Document.objects.filter(DOCUMENT_MISSING, student=OuterRef('pk')).order_by('title')
    rows = needing.annotate(**counts).annotate(
        reasons_n=sum((Case(When(**{f'{name}__gt': 0}, then=1), default=0) for name in counts), Value(0)),
        late_n=F('late_task_n') + F('late_mission_n'),
        missing_title=Subquery(first_missing.values('title')[:1]),
        sort_name=_sort_name(),
    ).order_by('-reasons_n', '-late_n', 'sort_name', 'pk').values(
        'pk', 'user__first_name', 'user__last_name', 'user__username', 'missing_title', 'late_n', *counts,
    )[:NEED_YOU_LIMIT]
    listed = []
    for row in rows:
        reasons = [{'key': key, 'count': row[f'{key}_n']} for key, _ in _attention_sources(today) if row[f'{key}_n']]
        for reason in reasons:
            if reason['key'] == 'missing_document':
                reason['title'] = (row['missing_title'] or '') if reason['count'] == 1 else ''
        listed.append({'id': row['pk'], 'name': _name(row), 'reasons': reasons, 'late': row['late_n']})
    return {'total': needing.count(), 'students': listed}


def progress_bucket(completion, expected, late):
    """Where a student stands on their roadmap.

    * ``completion``: completed missions / all missions (the roadmap %).
    * ``expected``: missions whose due date has passed / all missions, i.e.
      what a student keeping to schedule would have finished by today.
    * ``late``: late tasks + late missions (open work past its due date, the
      same rule as at-risk).

    Needs attention: 3+ late items, or completion 25+ points under expected.
    Behind: any late item, or completion under expected.
    On track: nothing late and completion at or above expected.
    """
    gap = expected - completion
    if late >= NEEDS_ATTENTION_LATE or gap >= NEEDS_ATTENTION_GAP:
        return 'needs_attention'
    if late > 0 or gap > 0:
        return 'behind'
    return 'on_track'


def roster(students):
    """``{student_id: name}`` for every student in scope (no profile is loaded)."""
    return {
        row['pk']: _name(row)
        for row in students.order_by().values('pk', 'user__first_name', 'user__last_name', 'user__username')
    }


def student_progress(students, today):
    """"Student progress", over every student in scope."""
    names = roster(students)
    stats = load_progress_stats(students)
    due_by_today = dict(
        RoadmapMission.objects.filter(student__in=students, due_date__lt=today).order_by()
        .values('student_id').annotate(total=Count('pk')).values_list('student_id', 'total')
    )
    progress = []
    buckets = {'on_track': 0, 'behind': 0, 'needs_attention': 0}
    for student_id, name in names.items():
        item = stats.get(student_id) or ProgressStats()
        late = item.tasks_overdue_count + item.missions_overdue_count
        completion = item.roadmap_progress_percent
        expected = percent(due_by_today.get(student_id, 0), item.missions_total)
        bucket = progress_bucket(completion, expected, late)
        buckets[bucket] += 1
        progress.append({
            'id': student_id, 'name': name, 'completion': completion, 'expected': expected,
            'late': late, 'bucket': bucket,
        })
    progress.sort(key=lambda row: (row['completion'], -row['late'], row['name'].lower(), row['id']))
    return {'total': len(progress), 'buckets': buckets, 'students': progress[:PROGRESS_LIMIT]}


def meetings_this_week(user, today, week):
    """Today's meetings in time order, and how many meetings each day of the week has.

    Every booking of the counselor's Bookings page counts, whoever booked it.
    """
    rows = list(
        counselor_bookings(user).filter(
            status__in=CALENDAR_MEETING_STATUSES,
            starts_at__gte=_day_start(week[0]), starts_at__lt=_day_start(week[-1] + timedelta(days=1)),
        ).annotate(day=TruncDate('starts_at')).order_by('starts_at', 'pk')
        .values('pk', 'topic', 'starts_at', 'duration_minutes', 'status', 'day', *STUDENT_FIELDS)
    )
    per_day = {}
    for row in rows:
        per_day[row['day'].isoformat()] = per_day.get(row['day'].isoformat(), 0) + 1
    return {
        'today': [{
            'id': row['pk'], 'topic': row['topic'], 'starts_at': row['starts_at'].isoformat(),
            'duration_minutes': row['duration_minutes'], 'status': row['status'],
            'student': row['student_id'], 'student_name': _name(row, 'student__'),
        } for row in rows if row['day'] == today],
        'days': per_day,
    }


class _LocalDate(TruncDate):
    """``TruncDate`` that, on SQLite, uses the native ``date()`` when the whole
    window has one UTC offset: Django's per-row Python timezone function there
    costs ~100 ms on a 2,000-student 12-week history. Other databases: unchanged."""

    def __init__(self, expression, start, end):
        super().__init__(expression)
        offsets = {_day_start(start + timedelta(days=n)).utcoffset() for n in range((end - start).days + 2)}
        self.offset = offsets.pop() if len(offsets) == 1 else None

    def as_sqlite(self, compiler, connection, **extra_context):
        if self.offset is None:
            return self.as_sql(compiler, connection, **extra_context)
        sql, params = compiler.compile(self.lhs)
        return f'date({sql}, %s)', (*params, f'{int(self.offset.total_seconds()) // 60:+d} minutes')


def _work_sources(user, start, end):
    """(queryset, path to the student, day) of the counselor's own work with a student, ``start``..``end``.

    Meetings held, meeting notes, approvals / send-backs / reviews / reminders
    (their ActivityLog rows), direct messages they sent, and tasks or missions
    they assigned. Not scoped to students yet: the caller adds that.
    """
    since, until = _day_start(start), _day_start(end + timedelta(days=1))
    created = {'created_at__gte': since, 'created_at__lt': until}
    sources = [
        (Booking.objects.filter(
            participant=user, status__in=HELD_MEETING_STATUSES, starts_at__gte=since, starts_at__lt=min(until, timezone.now()),
        ), 'student', _LocalDate('starts_at', start, end)),
        (MeetingNote.objects.filter(counselor=user, meeting_date__range=(start, end)), 'student', F('meeting_date')),
        (ActivityLog.objects.filter(actor=user, **created)
         .exclude(action__in=(CHECK_IN_ON, CHECK_IN_OFF))
         .exclude(reduce(or_, (Q(action__startswith=prefix) for prefix in NOT_A_CHECK_IN))), 'student', _LocalDate('created_at', start, end)),
        (ChannelMessage.objects.filter(
            sender=user, deleted_at__isnull=True, channel__kind=MessageChannel.Kind.DIRECT, **created,
        ), 'channel__memberships__user__student_profile', _LocalDate('created_at', start, end)),
    ]
    sources += [
        (model.objects.filter(assigned_by=user, **created), 'student', _LocalDate('created_at', start, end))
        for model in (Task, RoadmapMission)
    ]
    return sources


def _check_in_day():
    """The 'YYYY-MM-DD' a check-in row ticks, as plain text (JSON key lookups
    such as ``__in`` would otherwise compare JSON values, not strings)."""
    return Cast(KeyTextTransform('date', 'metadata'), output_field=CharField())


def _manual_on(user, start, end):
    """The counselor's check-in rows that tick a day of ``start``..``end`` and are still on.

    The latest row for a (student, day) wins, so an ON row counts only when no
    later row exists for the same student and day.
    """
    rows = ActivityLog.objects.filter(actor=user, action__in=(CHECK_IN_ON, CHECK_IN_OFF)).annotate(day=_check_in_day())
    later = rows.filter(student_id=OuterRef('student_id'), day=OuterRef('day')).filter(
        Q(created_at__gt=OuterRef('created_at')) | Q(created_at=OuterRef('created_at'), pk__gt=OuterRef('pk')),
    )
    days = [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)]
    # A tick for a day of this week is never written before the week began.
    return rows.filter(action=CHECK_IN_ON, day__in=days, created_at__gte=_day_start(start)).exclude(Exists(later))


def _checked_in(user, start, end):
    """A condition on StudentProfile rows: some auto or manual check-in ``start``..``end``."""
    found = [Exists(queryset.filter(**{path: OuterRef('pk')})) for queryset, path, _ in _work_sources(user, start, end)]
    found.append(Exists(_manual_on(user, start, end).filter(student=OuterRef('pk'))))
    return reduce(or_, found)


def _day_states(user, student_ids, start, end):
    """``({(student_id, date)} auto, {(student_id, date)} manual)`` for a page of students."""
    auto = set()
    for queryset, path, day in _work_sources(user, start, end):
        rows = queryset.filter(**{f'{path}__in': student_ids}).annotate(on_day=day).order_by()
        auto.update(rows.values_list(path, 'on_day').distinct())
    manual = {
        (student_id, datetime.strptime(day, '%Y-%m-%d').date())
        for student_id, day in _manual_on(user, start, end).filter(student_id__in=student_ids)
        .order_by().values_list('student_id', 'day').distinct()
    }
    return auto, manual


def weekly_check_ins(user, students, today, week, *, limit=CHECK_IN_LIMIT, offset=0):
    """Per student, the days of this week the counselor met, reviewed or wrote to them.

    A day is ``auto`` when the counselor's own records show work with that
    student, ``manual`` when they ticked it on Home, ``None`` otherwise (and
    always ``None`` for days still to come). ``students_total`` and
    ``checked_in`` cover the whole caseload; ``students`` is one page of it,
    students who need the counselor first, then by name.
    """
    totals = students.order_by().aggregate(
        total=Count('pk'), checked_in=Count('pk', filter=_checked_in(user, week[0], today)),
    )
    page = list(
        students.annotate(
            attention_rank=Case(When(_needs_attention(today), then=0), default=1), sort_name=_sort_name(),
        ).order_by('attention_rank', 'sort_name', 'pk')
        .values('pk', 'user__first_name', 'user__last_name', 'user__username')[offset:offset + limit]
    )
    auto, manual = _day_states(user, [row['pk'] for row in page], week[0], today)
    rows = []
    for row in page:
        days = []
        for day in week:
            key = (row['pk'], day)
            days.append('auto' if key in auto else 'manual' if key in manual else None)
        rows.append({'student': row['pk'], 'name': _name(row), 'days': days})
    return {
        'students_total': totals['total'],
        'checked_in': totals['checked_in'],
        'limit': limit,
        'offset': offset,
        'students': rows,
    }


def check_in_history(user, students, today, week):
    """How many students the counselor checked in with on each day of the last 12 weeks.

    The same sources as ``weekly_check_ins`` (their own work with a student,
    plus the days they ticked), each student counted once a day. Two queries
    whatever the caseload: one UNION of the work sources, one for the ticks.
    """
    start = week[0] - timedelta(weeks=HISTORY_WEEKS - 1)
    in_scope = students.order_by().values('pk')
    # EXISTS, not ``path__in``: SQLite probes an IN list per row on the direct-message join.
    pairs = [
        queryset.filter(Exists(students.order_by().filter(pk=OuterRef(path))))
        .annotate(on_day=day).order_by().values_list(path, 'on_day')
        for queryset, path, day in _work_sources(user, start, today)
    ]
    seen = set(pairs[0].union(*pairs[1:]))
    seen.update(
        (student_id, date.fromisoformat(day))
        for student_id, day in _manual_on(user, start, today).filter(student__in=in_scope)
        .order_by().values_list('student_id', 'day').distinct()
    )
    per_day = Counter(day.isoformat() for _, day in seen)
    return {'start': start.isoformat(), 'end': today.isoformat(), 'days': dict(sorted(per_day.items()))}


def student_snapshot(students, student_id, today):
    """One student's Home as they see it, or ``None`` when not in ``students``.

    Their study goal, roadmap level and stars, applications, achievements and
    open tasks. Blank goal fields are left out. Eight queries.
    """
    row = students.filter(pk=student_id).values(
        'pk', 'user__first_name', 'user__last_name', 'user__username', 'target_major', 'target_countries', 'level',
    ).first()
    if row is None:
        return None
    stats = load_progress_stats([row['pk']]).get(row['pk']) or ProgressStats()
    open_tasks = Task.objects.filter(student_id=row['pk'], status__in=OPEN_TASK_STATUSES)
    priorities = [
        {'id': task['pk'], 'title': task['title'], 'due': task['due_date'].isoformat() if task['due_date'] else None,
         'late': bool(task['due_date'] and task['due_date'] < today)}
        for task in open_tasks.order_by(F('due_date').asc(nulls_last=True), 'pk').values('pk', 'title', 'due_date')[:SNAPSHOT_PRIORITY_LIMIT]
    ]
    level_approved, level_total = stats.level_missions(row['level'])
    snapshot = {
        'student': row['pk'],
        'name': _name(row),
        'level': row['level'],
        'stars': stats.roadmap_stars,
        'roadmap': {
            'percent': stats.roadmap_progress_percent, 'approved': stats.roadmap_stars, 'total': stats.missions_total,
            'level_approved': level_approved, 'level_total': level_total,
        },
        'applications': {
            'total': stats.applications_total, 'submitted': stats.applications_done, 'accepted': stats.applications_accepted,
        },
        'achievements': stats.achievements_total,
        'open_tasks': sum(stats.task_counts.get(status, 0) for status in OPEN_TASK_STATUSES),
        'priorities': priorities,
    }
    if row['target_major'].strip():
        snapshot['study_goal'] = row['target_major'].strip()
    countries = [country.strip() for country in row['target_countries'].split(',') if country.strip()]
    if countries:
        snapshot['target_countries'] = countries
    return snapshot


def counselor_home(user, students, today, *, deadlines, need_you, badge_counts):
    """Everything the counselor Home shows beyond ``counselor_summary``, in one response.

    ``counselor_summary`` computes what both share and passes it in.
    """
    week = week_of(today)
    return {
        'today': today.isoformat(),
        'week': [day.isoformat() for day in week],
        'review_items': review_items(students),
        'need_you': need_you,
        'meetings': meetings_this_week(user, today, week),
        'messages': {'unread': badge_counts['messages_unread'], 'students': badge_counts['messages_unread_students']},
        'deadlines': deadlines,
        'check_ins': weekly_check_ins(user, students, today, week),
        'check_in_history': check_in_history(user, students, today, week),
        'progress': student_progress(students, today),
    }


def record_check_in(user, student, day, checked):
    """Tick (or un-tick) a day of this week for one student; the row is the audit trail.

    A tap that asks for the state the day already has writes nothing.
    Returns whether a row was written.
    """
    with transaction.atomic():
        # One tap at a time per counselor: two quick taps must not both read the same latest state.
        type(user).objects.select_for_update().filter(pk=user.pk).exists()
        latest = (
            ActivityLog.objects.filter(actor=user, student=student, action__in=(CHECK_IN_ON, CHECK_IN_OFF))
            .annotate(day=_check_in_day()).filter(day=day.isoformat())
            .order_by('-created_at', '-pk').values_list('action', flat=True).first()
        )
        if (latest == CHECK_IN_ON) == checked:
            return False
        ActivityLog.objects.create(
            actor=user, student=student, action=CHECK_IN_ON if checked else CHECK_IN_OFF,
            metadata={'event': CHECK_IN_EVENT, 'date': day.isoformat()},
        )
        return True
