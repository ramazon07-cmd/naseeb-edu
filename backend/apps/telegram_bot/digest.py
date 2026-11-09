"""The daily update and the grouped student list.

Every student comes from ``active_visible_students(user)``, the scope the
website's dashboard counts use, so the bot cannot show anyone the website would
not. Essays are limited by ``scope_essays`` (only essays the student shared).
Query count is fixed: students, six progress queries, one essay aggregate.
"""
from collections import OrderedDict
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.db.models import Count, Q

from apps.admissions.models import Essay, StudentProfile
from apps.admissions.onboarding import PROFILE_READINESS_ITEMS, profile_readiness
from apps.admissions.progress import attach_progress_stats
from apps.admissions.scoping import active_visible_students, scope_essays

from .activity import ActivityResult, essay_activity_for

TASHKENT = ZoneInfo('Asia/Tashkent')
MAX_STUDENTS = 300
SECTIONS = tuple(dict.fromkeys(section for _, section, _ in PROFILE_READINESS_ITEMS))
GRADE_ORDER = [value for value, _ in StudentProfile.Grade.choices]


def tashkent_now(now=None):
    return (now or datetime.now(TASHKENT)).astimezone(TASHKENT)


def _students(user):
    queryset = active_visible_students(user).select_related('user')
    return queryset.order_by('user__first_name', 'user__last_name', 'id')[:MAX_STUDENTS]


def _total(user, shown):
    # The cap only matters when it was reached, so the usual case costs no extra query.
    return active_visible_students(user).count() if shown >= MAX_STUDENTS else shown


def _name(student):
    return student.user.get_full_name().strip() or student.user.username


def grouped_students(user):
    """Students by class/grade: ``StudentProfile.grade`` ('' when the student has not picked one)."""
    rows = list(active_visible_students(user).order_by('user__first_name', 'user__last_name', 'id').values_list(
        'grade', 'user__first_name', 'user__last_name', 'user__username',
    )[:MAX_STUDENTS])
    groups = OrderedDict()
    for grade, first, last, username in rows:
        groups.setdefault(grade, []).append(f'{first} {last}'.strip() or username)
    ordered = sorted(groups, key=lambda g: (GRADE_ORDER.index(g) if g in GRADE_ORDER else len(GRADE_ORDER), g))
    total = _total(user, len(rows))
    return {
        'total': total,
        'omitted': total - len(rows),
        'groups': [{'grade': g, 'count': len(groups[g]), 'students': groups[g]} for g in ordered],
    }


def _essay_counts(user, student_ids, day_start):
    rows = (
        scope_essays(Essay.objects.filter(student_id__in=student_ids, trashed_at__isnull=True), user)
        .order_by().values('student_id')
        .annotate(total=Count('id'), edited=Count('id', filter=Q(last_edited_at__gte=day_start)))
    )
    return {row['student_id']: (row['total'], row['edited']) for row in rows}


def _application(student):
    readiness = profile_readiness(student)
    missing = {item['section'] for item in readiness['missing']}
    stats = student.progress_stats
    return {
        'percent': readiness['percent'],
        'sections': {section: section not in missing for section in SECTIONS},
        'activities': stats.activities_total,
        'honors': stats.achievements_total,
        'applications': {'done': stats.applications_done, 'total': stats.applications_total},
        'documents': {'done': stats.documents_done, 'total': stats.documents_total},
        'recommendations': {'done': stats.recommendations_done, 'total': stats.recommendations_total},
    }


def build_digest(user, prefs, now=None):
    now = tashkent_now(now)
    today = now.date()
    day_start = datetime.combine(today, time.min, tzinfo=TASHKENT)
    students = attach_progress_stats(list(_students(user)))
    ids = [student.pk for student in students]
    want_essays = prefs.get('essays', True)
    want_streak = prefs.get('streak', True)
    want_application = prefs.get('application', True)
    essays = _essay_counts(user, ids, day_start) if ids and (want_essays or want_streak) else {}
    private = set(
        Essay.objects.filter(student_id__in=ids, trashed_at__isnull=True, shared_with_counselor=False)
        .order_by().values_list('student_id', flat=True).distinct()
    ) if ids and want_streak else set()
    shared = {
        student.user_id for student in students
        if essays.get(student.pk, (0, 0))[0] and student.pk not in private
    }
    activity = essay_activity_for(sorted(shared), today) if shared else ActivityResult()
    items = []
    for student in students:
        item = {'name': _name(student), 'grade': student.grade}
        if want_essays:
            total, edited = essays.get(student.pk, (0, 0))
            item['essays'] = {'total': total, 'edited_today': edited}
        if want_streak:
            item['streak'] = {
                'days': activity.for_user(student.user_id).streak_days,
                'shared': student.user_id in shared,
            }
        if want_application:
            item['application'] = _application(student)
        items.append(item)
    total = _total(user, len(items))
    return {
        'date': today.isoformat(),
        'total_students': total,
        'omitted': total - len(items),
        'students': items,
    }

