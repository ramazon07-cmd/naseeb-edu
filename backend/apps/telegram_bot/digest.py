"""The daily update and the grouped student list.

Every student comes from ``active_visible_students(user)``, the scope the
website's dashboard counts use, so the bot cannot show anyone the website would
not. Essays are limited by ``scope_essays`` (only essays the student shared); the streak is shown
only for students without private essays (trashed ones included: their writing days remain).
Query count is fixed: students, six progress queries, one essay aggregate, one last-seen aggregate,
one credential query.

``last_seen_at`` is the newest sign of life of the student (UTC): a screen-time write, a sign-in
(``last_login``), the use of a temporary password, or the student setting their own password. The website's
"not started" rule reads the same signals, so a student who signed in is never shown as "never opened"
just because no screen-time row was written (or it was cleaned up). Screen-time rows are deleted after
``SCREEN_TIME_RETENTION_DAYS``, so a student with no signal who joined before that window is marked
``last_seen_expired`` (no recent activity on record) instead of "never opened the app".

``password`` is where the student stands with their login: ``none`` (own password from the start),
``issued`` (temporary password not used yet), ``used`` (signed in with it, own password not set yet),
``expired``, ``revoked`` or ``changed`` (the student set their own password).
"""
from collections import OrderedDict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Max, Q

from apps.admissions.models import Essay, ScreenTimeDaily, StudentProfile
from apps.admissions.onboarding import PROFILE_READINESS_ITEMS, profile_readiness
from apps.admissions.progress import attach_progress_stats
from apps.admissions.scoping import active_visible_students, scope_essays
from apps.users.models import TemporaryCredential

from .activity import essay_activity_for

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


def _last_seen(user_ids):
    rows = (
        ScreenTimeDaily.objects.filter(user_id__in=user_ids).order_by()
        .values('user_id').annotate(last=Max('last_seen_at'))
    )
    return {row['user_id']: row['last'] for row in rows}


def _credentials(user_ids):
    """``({user_id: latest credential}, {user_id: newest time a temporary password was used})``."""
    latest, used = {}, {}
    rows = (
        TemporaryCredential.objects.filter(user_id__in=user_ids).order_by('-issued_at', '-id')
        .only('user_id', 'status', 'expires_at', 'used_at')
    )
    for credential in rows:
        latest.setdefault(credential.user_id, credential)
        if credential.used_at and (credential.user_id not in used or credential.used_at > used[credential.user_id]):
            used[credential.user_id] = credential.used_at
    return latest, used


def _password_state(user, credential, now):
    if not user.must_change_password:
        # A later own password ends the temporary one, whatever its row says.
        if user.password_changed_at:
            return 'changed'
        return credential.status if credential else 'none'
    if credential is None:
        return 'none'
    if credential.status == TemporaryCredential.Status.ISSUED and credential.expires_at <= now:
        return TemporaryCredential.Status.EXPIRED.value
    return credential.status


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
    essays = _essay_counts(user, ids, day_start) if ids and want_essays else {}
    private = set(
        Essay.objects.filter(student_id__in=ids, shared_with_counselor=False)
        .order_by().values_list('student_id', flat=True).distinct()
    ) if ids and want_streak else set()
    visible = {student.user_id for student in students if student.pk not in private} if want_streak else set()
    last_seen = _last_seen([student.user_id for student in students]) if students else {}
    credentials, used_at = _credentials([student.user_id for student in students]) if students else ({}, {})
    retention_start = now - timedelta(days=settings.SCREEN_TIME_RETENTION_DAYS)
    streaks = essay_activity_for(sorted(visible), today) if visible else {}
    items = []
    for student in students:
        account = student.user
        seen = max(
            (moment for moment in (
                last_seen.get(student.user_id), account.last_login, used_at.get(student.user_id),
                account.password_changed_at,
            ) if moment),
            default=None,
        )
        item = {
            'id': student.pk,
            'name': _name(student),
            'grade': student.grade,
            'last_seen_at': seen.isoformat() if seen else None,
            'last_seen_expired': seen is None and account.date_joined < retention_start,
            'password': _password_state(account, credentials.get(student.user_id), now),
        }
        if want_essays:
            total, edited = essays.get(student.pk, (0, 0))
            item['essays'] = {'total': total, 'edited_today': edited}
        if want_streak:
            item['streak'] = {
                'days': streaks.get(student.user_id),
                'shared': student.user_id in visible,
            }
        if want_application:
            item['application'] = _application(student)
        items.append(item)
    total = _total(user, len(items))
    return {
        'date': today.isoformat(),
        'total_students': total,
        'omitted': total - len(items),
        'retention_days': settings.SCREEN_TIME_RETENTION_DAYS,
        'students': items,
    }

