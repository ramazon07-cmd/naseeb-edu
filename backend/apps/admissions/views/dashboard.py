"""Admissions API views — dashboard."""
from datetime import timedelta
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from apps.users.cache_safety import cache_get, cache_set
from apps.users.throttles import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers
from drf_spectacular.utils import extend_schema, inline_serializer
from apps.users.models import User
from ..models import (
    Application,
    Document,
    Essay,
    School,
    StudentProfile,
    Task,
)
from ..scoping import active_visible_students, shared_essay_lookups
from ..progress import APPLICATION_DONE, OPEN_TASK_STATUSES, late_tasks
from ..progress_cache import cached_progress_summary


PUBLIC_REACH_CACHE_KEY = 'public-reach:v1'
PUBLIC_REACH_CACHE_SECONDS = 300
def _public_reach_counts():
    """Aggregate counts without loading student or school records."""
    per_region = dict(
        StudentProfile.objects
        .filter(school__region__in=School.Region.values)
        .values_list('school__region')
        .order_by()
        .annotate(students=Count('id'))
    )
    return {'total': StudentProfile.objects.count(), 'per_region': per_region}


def _public_reach_payload(counts):
    """Publish every region while suppressing small cells.

    Suppressed counts are also left out of the total, otherwise the total
    minus the published regions would reveal a lone suppressed region.
    """
    min_cell = max(int(getattr(settings, 'PUBLIC_REACH_MIN_CELL', 0) or 0), 0)
    regions = []
    suppressed_total = 0
    for value, label in School.Region.choices:
        students = counts['per_region'].get(value, 0)
        suppressed = bool(min_cell) and students < min_cell
        if suppressed:
            suppressed_total += students
        regions.append({
            'region': value,
            'label': label,
            'students': 0 if suppressed else students,
            'active': students > 0,
        })
    return {'total': counts['total'] - suppressed_total, 'regions': regions}


class PublicReachView(APIView):
    """Unauthenticated, count-only regional coverage aggregate."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'public_reach'

    @extend_schema(
        responses=inline_serializer(
            name='PublicReach',
            fields={
                'total': drf_serializers.IntegerField(),
                'regions': inline_serializer(
                    name='PublicReachRegion',
                    fields={
                        'region': drf_serializers.ChoiceField(choices=School.Region.choices),
                        'label': drf_serializers.CharField(),
                        'students': drf_serializers.IntegerField(),
                        'active': drf_serializers.BooleanField(),
                    },
                    many=True,
                ),
            },
        )
    )
    def get(self, request):
        counts = cache_get(PUBLIC_REACH_CACHE_KEY)
        if counts is None:
            counts = _public_reach_counts()
            cache_set(PUBLIC_REACH_CACHE_KEY, counts, PUBLIC_REACH_CACHE_SECONDS)
        return Response(_public_reach_payload(counts))


class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses=inline_serializer(
            name='DashboardStats',
            fields={
                'students_total': drf_serializers.IntegerField(),
                'average_progress': drf_serializers.IntegerField(required=False),
                'average_task_progress': drf_serializers.IntegerField(required=False),
                'average_roadmap_progress': drf_serializers.IntegerField(required=False),
                'average_journey_progress': drf_serializers.IntegerField(required=False),
                'students_at_risk': drf_serializers.IntegerField(required=False),
                'tasks_total': drf_serializers.IntegerField(required=False),
                'tasks_late': drf_serializers.IntegerField(required=False),
                'tasks_due_week': drf_serializers.IntegerField(required=False),
                'applications_total': drf_serializers.IntegerField(required=False),
                'applications_submitted': drf_serializers.IntegerField(required=False),
                'documents_pending_review': drf_serializers.IntegerField(required=False),
                'essays_need_revision': drf_serializers.IntegerField(required=False),
                'application_by_status': drf_serializers.ListField(required=False),
                'task_by_status': drf_serializers.ListField(required=False),
            },
        )
    )
    def get(self, request):
        user = request.user
        # Deactivated students drop out of every count, as they do from lists.
        students = active_visible_students(user)

        progress_summary = cached_progress_summary(user, students)
        students_total = progress_summary.pop('students_total')

        if user.is_organization:
            return Response({
                'students_total': students_total,
                **progress_summary,
            })

        tasks = Task.objects.filter(student__in=students)
        applications = Application.objects.filter(student__in=students)
        documents = Document.objects.filter(student__in=students)
        essays = Essay.objects.filter(student__in=students, trashed_at__isnull=True, **shared_essay_lookups(user))
        today = timezone.localdate()
        open_tasks = Q(status__in=OPEN_TASK_STATUSES)
        task_totals = tasks.order_by().aggregate(
            total=Count('id'),
            late=Count('id', filter=late_tasks(today)),
            due_week=Count('id', filter=open_tasks & Q(due_date__range=[today, today + timedelta(days=7)])),
        )
        task_by_status = list(tasks.order_by().values('status').annotate(count=Count('id')).order_by('status'))

        if user.role == User.Role.TEACHER:
            return Response({
                'students_total': students_total,
                **progress_summary,
                'tasks_total': task_totals['total'],
                'tasks_late': task_totals['late'],
                'tasks_due_week': task_totals['due_week'],
                'task_by_status': task_by_status,
            })

        application_by_status = list(
            applications.order_by().values('status').annotate(count=Count('id')).order_by('status')
        )
        data = {
            'students_total': students_total,
            **progress_summary,
            'tasks_total': task_totals['total'],
            'tasks_late': task_totals['late'],
            'tasks_due_week': task_totals['due_week'],
            'applications_total': sum(row['count'] for row in application_by_status),
            'applications_submitted': sum(
                row['count'] for row in application_by_status if row['status'] in APPLICATION_DONE
            ),
            'documents_pending_review': documents.filter(status__in=[Document.Status.UPLOADED, Document.Status.REVIEWING]).count(),
            'essays_need_revision': essays.filter(status=Essay.Status.NEEDS_REVISION).count(),
            'application_by_status': application_by_status,
            'task_by_status': task_by_status,
        }
        return Response(data)
