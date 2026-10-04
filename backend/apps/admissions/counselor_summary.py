"""What a counselor's Home and sidebar count.

DashboardStatsView merges ``counselor_summary`` into a counselor's stats.
Every queryset here is already scoped to the counselor's visible students, so
a number never includes another counselor's or another school's work.
"""
from datetime import timedelta

from django.db.models import Exists, OuterRef

from .models import (
    Achievement,
    Application,
    Document,
    Essay,
    RecommendationLetter,
    RoadmapMission,
    Task,
)
from .progress import APPLICATION_DONE, OPEN_MISSION_STATUSES, OPEN_TASK_STATUSES, late_tasks
from .scoping import shared_essay_lookups

DEADLINE_WINDOW_DAYS = 7
DEADLINE_LIMIT = 5
# Letters the recommender still owes; a submitted or approved one is no deadline.
OPEN_LETTER_STATUSES = (RecommendationLetter.Status.REQUESTED, RecommendationLetter.Status.DRAFTING)


def review_counts(students, user, tasks_submitted, documents_waiting):
    """Submitted work waiting for the counselor, per kind of the Review page (essays: their own badge).

    Tasks and documents are counted by the dashboard already; it passes them in.
    """
    return {
        'tasks': tasks_submitted,
        'documents': documents_waiting,
        'roadmap': RoadmapMission.objects.filter(student__in=students, status=RoadmapMission.Status.SUBMITTED).count(),
        'portfolio': Achievement.objects.filter(student__in=students, verified=False, counselor_comment='').count(),
        'essays': Essay.objects.filter(
            student__in=students, status=Essay.Status.REVIEWING, trashed_at__isnull=True, **shared_essay_lookups(user),
        ).count(),
    }


def students_needing_attention(students, today):
    """Students with late work or a required document still missing (the Students page's "Need you")."""
    late_task = Exists(Task.objects.filter(student=OuterRef('pk')).filter(late_tasks(today)))
    late_mission = Exists(RoadmapMission.objects.filter(
        student=OuterRef('pk'), status__in=OPEN_MISSION_STATUSES, due_date__lt=today,
    ))
    missing_document = Exists(Document.objects.filter(student=OuterRef('pk'), status=Document.Status.REQUIRED))
    return students.filter(late_task | late_mission | missing_document).count()


STUDENT_FIELDS = ('student_id', 'student__user__first_name', 'student__user__username')


def _deadline(kind, row, title, due, today):
    return {
        'id': f'{kind}-{row["pk"]}',
        'kind': kind,
        'title': title,
        'student': row['student_id'],
        'student_name': row['student__user__first_name'] or row['student__user__username'],
        'due': due.isoformat(),
        'late': due < today,
    }


def upcoming_deadlines(students, today, limit=DEADLINE_LIMIT):
    """Open work due within a week, or already late, across tasks, applications and letters. Soonest first."""
    horizon = today + timedelta(days=DEADLINE_WINDOW_DAYS)
    found = []
    # values(): the dashboard never loads student profiles, only the names it shows.
    for row in (
        Task.objects.filter(student__in=students, status__in=OPEN_TASK_STATUSES, due_date__lte=horizon)
        .order_by('due_date', 'id').values('pk', 'title', 'due_date', *STUDENT_FIELDS)[:limit]
    ):
        found.append(_deadline('task', row, row['title'], row['due_date'], today))
    for row in (
        Application.objects.filter(student__in=students, deadline__isnull=False, deadline__lte=horizon)
        .exclude(status__in=APPLICATION_DONE)
        .order_by('deadline', 'id').values('pk', 'university__name', 'deadline', *STUDENT_FIELDS)[:limit]
    ):
        found.append(_deadline('application', row, row['university__name'], row['deadline'], today))
    for row in (
        RecommendationLetter.objects.filter(student__in=students, status__in=OPEN_LETTER_STATUSES, deadline__isnull=False, deadline__lte=horizon)
        .order_by('deadline', 'id').values('pk', 'recommender_name', 'deadline', *STUDENT_FIELDS)[:limit]
    ):
        found.append(_deadline('letter', row, row['recommender_name'], row['deadline'], today))
    found.sort(key=lambda row: (row['due'], row['id']))
    return found[:limit]


def counselor_summary(user, students, today, *, tasks_submitted, documents_waiting):
    """The extra dashboard-stats fields of a counselor: review counts, who needs them, what is due."""
    return {
        'review': review_counts(students, user, tasks_submitted, documents_waiting),
        'students_need_you': students_needing_attention(students, today),
        'deadlines': upcoming_deadlines(students, today),
    }
