"""Admissions API views — the product-admin portal's summaries."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users import entitlements
from apps.users.admin_permissions import IsOpsStaff, IsSupportStaff
from apps.users.cache_safety import cache_get, cache_set
from apps.users.models import JobRun, User, WorkspaceSubscription
from core.health import readiness
from core.jobs import SCHEDULED_JOBS
from ..models import (
    Achievement,
    Activity,
    ChannelMessage,
    CounselorRoadmapMission,
    Document,
    Honor,
    MessageReport,
    RecommendationLetter,
    School,
    SupportTicket,
    Task,
)

ADMIN_SUMMARY_CACHE_KEY = 'admin-summary:v1'
# shortcut: a short TTL instead of invalidation on every write; switch to versioned keys if tiles must be instant.
ADMIN_SUMMARY_CACHE_SECONDS = 30
ATTENTION_LIMIT = 10
EXPIRING_WITHIN_DAYS = 30


def _attention(queryset, row):
    """At most ATTENTION_LIMIT rows plus the full count, for the "Needs attention" panel."""
    return {'count': queryset.count(), 'items': [row(item) for item in queryset[:ATTENTION_LIMIT]]}


def admin_summary():
    """Counts behind the Admin Control tiles and its "Needs attention" panel (docs/metrics.md)."""
    today = timezone.localdate()
    active = School.objects.filter(is_active=True)
    workspaces = active.aggregate(
        schools=Count('id', filter=Q(workspace_type=School.WorkspaceType.SCHOOL)),
        individual=Count('id', filter=Q(workspace_type=School.WorkspaceType.INDIVIDUAL)),
    )
    counselors = User.objects.filter(role=User.Role.COUNSELOR).aggregate(
        active=Count('id', filter=Q(is_active=True)), inactive=Count('id', filter=Q(is_active=False)),
    )
    tickets = SupportTicket.objects.aggregate(
        open=Count('id', filter=Q(status=SupportTicket.Status.OPEN)),
        in_progress=Count('id', filter=Q(status=SupportTicket.Status.IN_PROGRESS)),
    )
    expiring = WorkspaceSubscription.objects.filter(school__is_active=True).filter(
        Q(status__in=WorkspaceSubscription.READ_ONLY_STATUSES)
        | Q(period_end__lte=today + timedelta(days=EXPIRING_WITHIN_DAYS)),
    ).select_related('school').order_by(F('period_end').asc(nulls_first=True), 'school__name')
    # Organization schools only: an individual workspace is always "full" at its one counselor.
    full_seats = Q()
    for key in entitlements.SEAT_ROLES:
        full_seats |= Q(**{f'subscription__plan__{key}__isnull': False, f'{key}_used__gte': F(f'subscription__plan__{key}')})
    seats = entitlements.annotate_seat_usage(
        active.filter(workspace_type=School.WorkspaceType.SCHOOL).select_related('subscription__plan'),
    ).filter(full_seats).order_by('name')
    missing_login = active.filter(workspace_type=School.WorkspaceType.SCHOOL).exclude(
        users__role=User.Role.ORGANIZATION,
    ).order_by('name')
    return {
        'schools_active': workspaces['schools'],
        'individual_workspaces_active': workspaces['individual'],
        'counselors_active': counselors['active'],
        'counselors_inactive': counselors['inactive'],
        'roadmap_missions_submitted': CounselorRoadmapMission.objects.filter(
            status=CounselorRoadmapMission.Status.SUBMITTED,
        ).count(),
        'support_open': tickets['open'],
        'support_in_progress': tickets['in_progress'],
        'message_reports_pending': MessageReport.objects.filter(status=MessageReport.Status.PENDING).count(),
        'attention': {
            'expiring': _attention(expiring, lambda subscription: {
                'id': subscription.school_id, 'name': subscription.school.name,
                'period_end': subscription.period_end, 'status': subscription.status,
                'read_only': subscription.is_read_only,
            }),
            'seats_full': _attention(seats, lambda school: {
                'id': school.id, 'name': school.name,
                'seats': {
                    key: {'used': getattr(school, f'{key}_used'), 'limit': school.subscription.plan.limit(key)}
                    for key in entitlements.SEAT_ROLES
                    if school.subscription.plan.limit(key) is not None
                },
            }),
            'missing_login': _attention(missing_login, lambda school: {'id': school.id, 'name': school.name}),
        },
    }


class AdminSummaryView(APIView):
    """Admin Control's numbers in one cached request, instead of loading every school."""

    permission_classes = [IsSupportStaff]

    def get(self, request):
        summary = cache_get(ADMIN_SUMMARY_CACHE_KEY)
        if summary is None:
            summary = admin_summary()
            cache_set(ADMIN_SUMMARY_CACHE_KEY, summary, ADMIN_SUMMARY_CACHE_SECONDS)
        return Response(summary)


class AdminAiUsageView(APIView):
    """Paid AI calls today against their daily caps. Counters only: no student content."""

    permission_classes = [IsSupportStaff]

    def get(self, request):
        from .. import ai_budget

        names = dict(School.objects.filter(is_active=True).values_list('id', 'name'))
        report = ai_budget.usage_today(list(names))
        for feature in (report or {}).values():
            for row in feature['top_schools']:
                row['name'] = names.get(row['id'], '')
        return Response({
            'day': timezone.localdate(),
            'cache_available': report is not None,
            'fallback_active': ai_budget.fallback_active(),
            'features': report,
        })


# Uploaded files by kind, from the sizes saved with each upload; images
# (avatars, photos) keep no size and are not counted.
STORAGE_CATEGORIES = (
    ('documents', ((Document, 'file_size'),)),
    ('task_submissions', ((Task, 'submission_file_size'),)),
    ('message_attachments', ((ChannelMessage, 'attachment_size'),)),
    ('activity_evidence', ((Achievement, 'proof_file_size'), (Activity, 'proof_file_size'), (Honor, 'proof_file_size'))),
    ('recommendation_letters', ((RecommendationLetter, 'file_size'),)),
)
JOB_OVERDUE_AFTER = timedelta(hours=26)


# Summing every upload's size reads whole tables, so the result is kept for
# STORAGE_CACHE_SECONDS; "Check again" recounts at most once per STORAGE_RECHECK_SECONDS.
STORAGE_CACHE_KEY = 'admin-storage:v1'
STORAGE_CACHE_SECONDS = 10 * 60
STORAGE_RECHECK_SECONDS = 60


def storage_usage():
    rows = []
    for category, sources in STORAGE_CATEGORIES:
        files = size = 0
        for model, field in sources:
            # One pass per table, no WHERE on the unindexed size column: sizes are
            # never negative, so the plain sum already leaves out files without one.
            totals = model.objects.aggregate(files=Count('pk', filter=Q(**{f'{field}__gt': 0})), size=Sum(field))
            files += totals['files']
            size += totals['size'] or 0
        rows.append({'category': category, 'files': files, 'bytes': size})
    return rows


def cached_storage_usage(recheck=False):
    """``(rows, checked_at)``, recounted when the cached count is gone, or on a
    recheck when it is older than STORAGE_RECHECK_SECONDS."""
    cached = cache_get(STORAGE_CACHE_KEY)
    now = timezone.now()
    if cached is not None and not (
        recheck and (now - cached['checked_at']).total_seconds() >= STORAGE_RECHECK_SECONDS
    ):
        return cached['rows'], cached['checked_at']
    rows = storage_usage()
    cache_set(STORAGE_CACHE_KEY, {'rows': rows, 'checked_at': now}, STORAGE_CACHE_SECONDS)
    return rows, now


class AdminHealthView(APIView):
    """Readiness, the last run of every scheduled job, file storage and error tracking.

    Operational facts only: no personal data.
    """

    permission_classes = [IsOpsStaff]

    def get(self, request):
        overall, checks = readiness()
        overdue_before = timezone.now() - JOB_OVERDUE_AFTER
        jobs = []
        for name in SCHEDULED_JOBS:
            runs = JobRun.objects.filter(name=name)
            # A run skipped because another instance held the lock did no work: it
            # must not hide the real last run, and only a success keeps a job on time.
            last = runs.exclude(result=JobRun.Result.SKIPPED).first()
            last_success = runs.filter(result=JobRun.Result.OK).only('started_at').first()
            jobs.append({
                'name': name,
                'last_run': {
                    'started_at': last.started_at, 'duration_seconds': last.duration_seconds,
                    'result': last.result, 'processed': last.processed, 'error': last.error,
                } if last else None,
                'last_success_at': last_success.started_at if last_success else None,
                'skipped_recently': runs.filter(
                    result=JobRun.Result.SKIPPED, started_at__gte=overdue_before,
                ).count(),
                'overdue': last_success is None or last_success.started_at < overdue_before,
            })
        storage, storage_checked_at = cached_storage_usage(recheck=request.query_params.get('refresh') == 'storage')
        return Response({
            'readiness': {'status': overall, **checks},
            'jobs': jobs,
            'storage': storage,
            'storage_checked_at': storage_checked_at,
            'error_tracking': {'enabled': settings.SENTRY_ENABLED, 'url': settings.ERROR_TRACKER_URL or None},
        })
