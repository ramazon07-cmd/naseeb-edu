"""Admissions API views — dashboard."""
from django.conf import settings
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from apps.users.cache_safety import cache_get, cache_set
from apps.users.throttles import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ValidationError
from rest_framework.settings import api_settings
from drf_spectacular.utils import extend_schema, inline_serializer
from apps.users.models import User
from ..models import (
    Application,
    Document,
    Essay,
    School,
    StudentProfile,
    SupportTicket,
    Task,
)
from ..counselor_summary import (
    CHECK_IN_LIMIT, CHECK_IN_MAX_LIMIT, counselor_summary, record_check_in, student_snapshot, week_of, weekly_check_ins,
)
from ..params import int_param
from ..scoping import active_visible_students, shared_essay_lookups
from ..progress import APPLICATION_DONE, DOCUMENT_AWAITING_REVIEW, OPEN_TASK_STATUSES, late_tasks
from ..progress_cache import cached_progress_summary


def support_unread(user):
    """The user's own tickets with an answer they have not opened (SupportTicket.has_unread_response), in one query."""
    return SupportTicket.objects.filter(requester=user, responded_at__isnull=False).filter(
        Q(requester_viewed_at__isnull=True) | Q(requester_viewed_at__lt=F('responded_at')),
    ).count()


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


class CheckInThrottle(ScopedRateThrottle):
    """Check-in taps per counselor; ``check_in`` in DEFAULT_THROTTLE_RATES overrides the default."""

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES.get('check_in', '60/minute')


def _check_in_page(params):
    """``(limit, offset)`` of ``?check_ins=all``, or a 400."""
    limit = int_param(params, 'limit')
    offset = int_param(params, 'offset')
    limit = CHECK_IN_LIMIT if limit is None else limit
    offset = 0 if offset is None else offset
    if not 1 <= limit <= CHECK_IN_MAX_LIMIT:
        raise ValidationError({'limit': [f'Use a number from 1 to {CHECK_IN_MAX_LIMIT}.']})
    if offset < 0:
        raise ValidationError({'offset': ['Use 0 or more.']})
    return limit, offset


class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'check_in'

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method == 'POST':
            throttles.append(CheckInThrottle())
        return throttles

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
                # Counselors only: what Home and the sidebar count.
                'review': inline_serializer(
                    name='DashboardReviewCounts',
                    fields={
                        'tasks': drf_serializers.IntegerField(),
                        'documents': drf_serializers.IntegerField(),
                        'roadmap': drf_serializers.IntegerField(),
                        'portfolio': drf_serializers.IntegerField(),
                        'essays': drf_serializers.IntegerField(),
                    },
                    required=False,
                ),
                'students_need_you': drf_serializers.IntegerField(required=False),
                # Open work due this week (Monday-Sunday); older open work is only counted.
                'deadlines': drf_serializers.ListField(required=False),
                'deadlines_overdue': drf_serializers.IntegerField(required=False),
                'deadlines_week_total': drf_serializers.IntegerField(required=False),
                # Every role: the Support badge (the ticket list is paged, so it cannot count them).
                'support_unread': drf_serializers.IntegerField(required=False),
                # Counselors only: the numbers the sidebar and bell poll.
                'badges': inline_serializer(
                    name='DashboardBadges',
                    fields={
                        'meetings_pending': drf_serializers.IntegerField(),
                        'messages_unread': drf_serializers.IntegerField(),
                        'messages_unread_conversations': drf_serializers.IntegerField(),
                        'messages_unread_students': drf_serializers.IntegerField(),
                        'students_pending': drf_serializers.IntegerField(),
                    },
                    required=False,
                ),
                # Counselors, with ?include=home: see counselor_summary.counselor_home.
                'home': drf_serializers.DictField(required=False),
                # Counselors, with ?check_ins=all&limit=&offset=: the response is only this page.
                'check_ins': drf_serializers.DictField(required=False),
                # Counselors, with ?snapshot=<student id>: the response is only that student's snapshot.
                'snapshot': drf_serializers.DictField(required=False),
            },
        )
    )
    def get(self, request):
        user = request.user
        # Deactivated students drop out of every count, as they do from lists.
        students = active_visible_students(user)
        today = timezone.localdate()

        if user.role == User.Role.COUNSELOR and request.query_params.get('check_ins') == 'all':
            limit, offset = _check_in_page(request.query_params)
            return Response({'check_ins': weekly_check_ins(user, students, today, week_of(today), limit=limit, offset=offset)})

        if user.role == User.Role.COUNSELOR and 'snapshot' in request.query_params:
            student_id = int_param(request.query_params, 'snapshot')
            snapshot = student_snapshot(students, student_id, today) if student_id is not None else None
            if snapshot is None:
                return Response({'detail': 'Not found.'}, status=404)
            return Response({'snapshot': snapshot})

        progress_summary = cached_progress_summary(user, students)
        students_total = progress_summary.pop('students_total')

        if user.is_organization:
            from ..invites import pending_scope

            return Response({
                'students_total': students_total,
                **progress_summary,
                'support_unread': support_unread(user),
                # Students who joined by invite and wait for the school to confirm them.
                'badges': {'students_pending': pending_scope(user).count()},
            })

        tasks = Task.objects.filter(student__in=students)
        applications = Application.objects.filter(student__in=students)
        documents = Document.objects.filter(student__in=students)
        essays = Essay.objects.filter(student__in=students, trashed_at__isnull=True, **shared_essay_lookups(user))
        week = week_of(today)
        open_tasks = Q(status__in=OPEN_TASK_STATUSES)
        task_totals = tasks.order_by().aggregate(
            total=Count('id'),
            late=Count('id', filter=late_tasks(today)),
            # Monday to Sunday, as the deadlines are.
            due_week=Count('id', filter=open_tasks & Q(due_date__range=[week[0], week[-1]])),
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
                'support_unread': support_unread(user),
            })

        essay_totals = essays.order_by().aggregate(
            need_revision=Count('id', filter=Q(status=Essay.Status.NEEDS_REVISION)),
            reviewing=Count('id', filter=Q(status=Essay.Status.REVIEWING)),
        )
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
            'documents_pending_review': documents.filter(DOCUMENT_AWAITING_REVIEW).count(),
            'essays_need_revision': essay_totals['need_revision'],
            'application_by_status': application_by_status,
            'task_by_status': task_by_status,
            'support_unread': support_unread(user),
        }
        if user.role == User.Role.COUNSELOR:
            data.update(counselor_summary(
                user, students, today,
                tasks_submitted=sum(row['count'] for row in task_by_status if row['status'] == Task.Status.SUBMITTED),
                documents_waiting=data['documents_pending_review'],
                essays_reviewing=essay_totals['reviewing'],
                include_home=request.query_params.get('include') == 'home',
            ))
        return Response(data)

    @extend_schema(
        request=inline_serializer(
            name='CounselorCheckIn',
            fields={
                'student': drf_serializers.IntegerField(),
                'date': drf_serializers.DateField(),
                'checked': drf_serializers.BooleanField(),
            },
        ),
        responses=inline_serializer(
            name='CounselorCheckInResult',
            fields={
                'student': drf_serializers.IntegerField(),
                'date': drf_serializers.DateField(),
                'checked': drf_serializers.BooleanField(),
            },
        ),
    )
    def post(self, request):
        """A counselor ticks or un-ticks a day of this week (up to today) for one of their students on Home."""
        user = request.user
        if user.role != User.Role.COUNSELOR:
            return Response({'detail': 'Only a counselor can record a check-in.'}, status=403)
        payload = CheckInSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        values = payload.validated_data
        today = timezone.localdate()
        if not week_of(today)[0] <= values['date'] <= today:
            return Response({'date': ['Pick a day of this week, up to today.']}, status=400)
        student = active_visible_students(user).filter(pk=values['student']).first()
        if student is None:
            return Response({'detail': 'Not found.'}, status=404)
        record_check_in(user, student, values['date'], values['checked'])
        return Response({'student': student.pk, 'date': values['date'], 'checked': values['checked']})


class CheckInSerializer(drf_serializers.Serializer):
    student = drf_serializers.IntegerField()
    date = drf_serializers.DateField()
    checked = drf_serializers.BooleanField()
