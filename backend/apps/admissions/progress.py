"""Batch-loaded student progress statistics.

``load_progress_stats`` computes StudentProfile's progress/at-risk numbers for
any number of students in six grouped queries; ``attach_progress_stats``
caches them on the instances so list views stay O(1) in queries.
``summarize_progress`` averages the same numbers over a whole student
queryset inside the database, in one set-based query.
"""
from dataclasses import dataclass, field

from django.db.models import Case, Count, IntegerField, Q, QuerySet, Sum, Value, When
from django.utils import timezone

TASK_WEIGHTS = {
    'todo': 0,
    'late': 0,
    'in_progress': 40,
    'submitted': 80,
    'approved': 100,
}
TASK_DONE = 'approved'
MISSION_DONE = 'completed'
# Work the student still owes. Submitted work waits on the reviewer, so it is
# never late, whatever its due date.
OPEN_TASK_STATUSES = ('todo', 'in_progress', 'late')
OPEN_MISSION_STATUSES = ('planned', 'in_progress')
# Sent to the university; a decision (any of them) comes only after that.
APPLICATION_DONE = ('submitted', 'accepted', 'rejected', 'waitlisted')
APPLICATION_ACCEPTED = 'accepted'
DOCUMENT_DONE = 'approved'
# The recommender has sent the letter; the counselor's approval is a quality check on top.
RECOMMENDATION_DONE = ('submitted', 'approved')


def late_tasks(today):
    """Late tasks: work the student still owes that is past its due date.

    The single definition behind at-risk, the dashboard's tasks_late and the
    late-task alert. A task whose status is `late` but that is not past due
    (the due date was moved) is not late.
    """
    return Q(status__in=OPEN_TASK_STATUSES, due_date__lt=today)


def half_up(numerator, denominator):
    """``numerator / denominator`` rounded half up, in exact integer math; 0 when empty.

    Percentages are shown as whole numbers and 12.5% reads as 13%, exactly as
    the browser's Math.round would show it. Integers keep Python and SQL equal.
    """
    if not denominator:
        return 0
    return (2 * numerator + denominator) // (2 * denominator)


def percent(part, whole):
    return half_up(100 * part, whole)


@dataclass
class ProgressStats:
    task_counts: dict = field(default_factory=dict)
    mission_counts: dict = field(default_factory=dict)
    # {level: {status: count}}: the roadmap page shows one level at a time.
    mission_level_counts: dict = field(default_factory=dict)
    applications_total: int = 0
    applications_done: int = 0
    applications_accepted: int = 0
    achievements_total: int = 0
    documents_total: int = 0
    documents_done: int = 0
    recommendations_total: int = 0
    recommendations_done: int = 0
    task_overdue: bool = False
    mission_overdue: bool = False

    @property
    def tasks_total(self):
        return sum(self.task_counts.values())

    @property
    def missions_total(self):
        return sum(self.mission_counts.values())

    @property
    def readiness_items_total(self):
        return self.tasks_total + self.applications_total + self.documents_total + self.recommendations_total

    @property
    def readiness_items_done(self):
        return (
            self.task_counts.get(TASK_DONE, 0) + self.applications_done
            + self.documents_done + self.recommendations_done
        )

    @property
    def progress_percent(self):
        """Application readiness: finished items over all items."""
        return percent(self.readiness_items_done, self.readiness_items_total)

    @property
    def task_progress_percent(self):
        weighted = sum(TASK_WEIGHTS.get(status, 0) * count for status, count in self.task_counts.items())
        return half_up(weighted, self.tasks_total)

    @property
    def roadmap_progress_percent(self):
        return percent(self.mission_counts.get(MISSION_DONE, 0), self.missions_total)

    @property
    def roadmap_stars(self):
        return self.mission_counts.get(MISSION_DONE, 0)

    def level_missions(self, level):
        """``(approved, total)`` missions of one roadmap level."""
        counts = self.mission_level_counts.get(level, {})
        return counts.get(MISSION_DONE, 0), sum(counts.values())

    @property
    def journey_progress_percent(self):
        has_tasks = self.tasks_total > 0
        has_missions = self.missions_total > 0
        if has_tasks and has_missions:
            return half_up(self.task_progress_percent + self.roadmap_progress_percent, 2)
        if has_tasks:
            return self.task_progress_percent
        if has_missions:
            return self.roadmap_progress_percent
        return 0

    @property
    def is_at_risk(self):
        return self.task_overdue or self.mission_overdue


def _student_filter(students):
    if isinstance(students, QuerySet):
        return {'student__in': students.order_by().values('pk')}
    return {'student_id__in': list(students)}


def load_progress_stats(students):
    """Return ``{student_id: ProgressStats}`` for a queryset or iterable of ids (6 queries)."""
    from .models import Achievement, Application, Document, Honor, RecommendationLetter, RoadmapMission, Task

    today = timezone.localdate()
    scope = _student_filter(students)
    stats = {}

    def get(student_id):
        if student_id not in stats:
            stats[student_id] = ProgressStats()
        return stats[student_id]

    for row in (
        Task.objects.filter(**scope).order_by().values('student_id', 'status')
        .annotate(total=Count('id'), overdue=Count('id', filter=late_tasks(today)))
    ):
        item = get(row['student_id'])
        item.task_counts[row['status']] = row['total']
        if row['overdue']:
            item.task_overdue = True
    for row in (
        RoadmapMission.objects.filter(**scope).order_by().values('student_id', 'level', 'status')
        .annotate(total=Count('id'), overdue=Count('id', filter=Q(due_date__lt=today)))
    ):
        item = get(row['student_id'])
        status = row['status']
        item.mission_counts[status] = item.mission_counts.get(status, 0) + row['total']
        item.mission_level_counts.setdefault(row['level'], {})[status] = row['total']
        if row['status'] in OPEN_MISSION_STATUSES and row['overdue']:
            item.mission_overdue = True
    for row in (
        Application.objects.filter(**scope).order_by().values('student_id')
        .annotate(
            total=Count('id'),
            done=Count('id', filter=Q(status__in=APPLICATION_DONE)),
            accepted=Count('id', filter=Q(status=APPLICATION_ACCEPTED)),
        )
    ):
        item = get(row['student_id'])
        item.applications_total = row['total']
        item.applications_done = row['done']
        item.applications_accepted = row['accepted']
    for row in (
        Document.objects.filter(**scope).order_by().values('student_id')
        .annotate(total=Count('id'), done=Count('id', filter=Q(status=DOCUMENT_DONE)))
    ):
        item = get(row['student_id'])
        item.documents_total = row['total']
        item.documents_done = row['done']
    for row in (
        RecommendationLetter.objects.filter(**scope).order_by().values('student_id')
        .annotate(total=Count('id'), done=Count('id', filter=Q(status__in=RECOMMENDATION_DONE)))
    ):
        item = get(row['student_id'])
        item.recommendations_total = row['total']
        item.recommendations_done = row['done']
    # Achievements and honors are one "Achievements" count: one UNION ALL query.
    achievements = Achievement.objects.filter(**scope).order_by().values('student_id').annotate(total=Count('id'))
    honors = Honor.objects.filter(**scope).order_by().values('student_id').annotate(total=Count('id'))
    for row in achievements.union(honors, all=True):
        get(row['student_id']).achievements_total += row['total']
    return stats


def attach_progress_stats(profiles):
    """Cache batch-loaded stats on each profile; returns the same list."""
    profiles = [profile for profile in profiles if profile is not None]
    if not profiles:
        return profiles
    stats = load_progress_stats([profile.pk for profile in profiles])
    for profile in profiles:
        profile._progress_stats = stats.get(profile.pk) or ProgressStats()
    return profiles


def _grouped_sql(queryset):
    sql, params = queryset.query.sql_with_params()
    return f'({sql})', list(params)


def _half_up_sql(numerator, denominator):
    """SQL twin of ``half_up`` for non-negative integers (integer division truncates)."""
    return f'CASE WHEN {denominator} > 0 THEN (2 * ({numerator}) + {denominator}) / (2 * {denominator}) ELSE 0 END'


def summarize_progress(students):
    """Averages and at-risk count over ``students`` in one query.

    Each related table is grouped by student once; those grouped rows are
    joined to the student ids, and the percentages and their sums are
    computed over that derived table. No per-student subqueries, and no
    student is ever loaded into Python. All arithmetic is integer, with the
    same half-up rounding as ProgressStats, so both always agree.
    """
    from django.db import connections
    from django.core.exceptions import EmptyResultSet

    from .models import Application, Document, RecommendationLetter, RoadmapMission, Task

    today = timezone.localdate()
    ids = students.order_by().values('pk')
    scope = {'student__in': ids}
    weight = Case(
        *(When(status=status, then=Value(points)) for status, points in TASK_WEIGHTS.items() if points),
        default=Value(0), output_field=IntegerField(),
    )
    grouped = {
        't': Task.objects.filter(**scope).order_by().values('student_id').annotate(
            total=Count('pk'),
            done=Count('pk', filter=Q(status=TASK_DONE)),
            points=Sum(weight),
            risky=Count('pk', filter=late_tasks(today)),
        ),
        'm': RoadmapMission.objects.filter(**scope).order_by().values('student_id').annotate(
            total=Count('pk'),
            done=Count('pk', filter=Q(status=MISSION_DONE)),
            risky=Count('pk', filter=Q(due_date__lt=today, status__in=OPEN_MISSION_STATUSES)),
        ),
        'a': Application.objects.filter(**scope).order_by().values('student_id').annotate(
            total=Count('pk'), done=Count('pk', filter=Q(status__in=APPLICATION_DONE)),
        ),
        'd': Document.objects.filter(**scope).order_by().values('student_id').annotate(
            total=Count('pk'), done=Count('pk', filter=Q(status=DOCUMENT_DONE)),
        ),
        'r': RecommendationLetter.objects.filter(**scope).order_by().values('student_id').annotate(
            total=Count('pk'), done=Count('pk', filter=Q(status__in=RECOMMENDATION_DONE)),
        ),
    }
    try:
        scope_sql, params = _grouped_sql(ids)
        joins = []
        for alias, queryset in grouped.items():
            sql, extra = _grouped_sql(queryset)
            joins.append(f'LEFT JOIN {sql} {alias} ON {alias}.student_id = s.pk')
            params += extra
    except EmptyResultSet:
        return _summary(0, {})

    connection = connections[students.db]
    sql = f"""
        SELECT COUNT(*), SUM(progress), SUM(task_progress), SUM(roadmap_progress),
            SUM(CASE WHEN tasks > 0 AND missions > 0 THEN (task_progress + roadmap_progress + 1) / 2
                WHEN tasks > 0 THEN task_progress WHEN missions > 0 THEN roadmap_progress ELSE 0 END),
            SUM(CASE WHEN risky > 0 THEN 1 ELSE 0 END)
        FROM (
            SELECT tasks, missions, risky,
                {_half_up_sql('100 * (task_done + app_done + doc_done + rec_done)', '(tasks + apps + docs + recs)')}
                    AS progress,
                {_half_up_sql('points', 'tasks')} AS task_progress,
                {_half_up_sql('100 * mission_done', 'missions')} AS roadmap_progress
            FROM (
                SELECT COALESCE(t.total, 0) AS tasks, COALESCE(t.done, 0) AS task_done,
                    COALESCE(t.points, 0) AS points,
                    COALESCE(m.total, 0) AS missions, COALESCE(m.done, 0) AS mission_done,
                    COALESCE(a.total, 0) AS apps, COALESCE(a.done, 0) AS app_done,
                    COALESCE(d.total, 0) AS docs, COALESCE(d.done, 0) AS doc_done,
                    COALESCE(r.total, 0) AS recs, COALESCE(r.done, 0) AS rec_done,
                    COALESCE(t.risky, 0) + COALESCE(m.risky, 0) AS risky
                FROM {scope_sql} s
                {' '.join(joins)}
            ) counts
        ) per_student
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        count, *sums = cursor.fetchone()
    keys = ('progress', 'task_progress', 'roadmap_progress', 'journey', 'at_risk')
    return _summary(count, dict(zip(keys, sums)))


def _summary(count, totals):
    def average(key):
        return half_up(int(totals.get(key) or 0), count)

    return {
        'students_total': count,
        'average_progress': average('progress'),
        'average_task_progress': average('task_progress'),
        'average_roadmap_progress': average('roadmap_progress'),
        'average_journey_progress': average('journey'),
        'students_at_risk': int(totals.get('at_risk') or 0),
    }
