"""GET /api/review/today/: what the caller approved or sent back today.

Read from the timeline entries the approve and send-back actions already
write (ApproveMixin, SendBackMixin, the task and roadmap approve actions), so
nothing new is stored. "Today" starts at local midnight in the server's zone
(Asia/Tashkent). Rows are the caller's own and only for students the caller
can still see, so a counselor moved to another school, or a student moved to
another counselor, drops out. One query, whatever the count.
"""
import re
from datetime import datetime, time

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import permissions
from rest_framework import serializers as drf_serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import ActivityLog
from ..scoping import scope_students

REVIEWED_TODAY_LIMIT = 100

# (action prefix, queue kind, decision). Kinds match the frontend review queue.
REVIEW_ACTIONS = (
    ('Task approved: ', 'task', 'approved'),
    ('Self-task approved: ', 'task', 'approved'),
    ('Document approved: ', 'document', 'approved'),
    ('Roadmap mission approved: ', 'roadmap', 'approved'),
    ('Achievement approved: ', 'portfolio', 'approved'),
    ('Task sent back: ', 'task', 'sent_back'),
    ('Document sent back: ', 'document', 'sent_back'),
    ('Roadmap mission sent back: ', 'roadmap', 'sent_back'),
    ('Achievement sent back: ', 'portfolio', 'sent_back'),
)
XP_SUFFIX = re.compile(r' \((?:\+\d+ XP|no XP)\)$')
RECORD_KEYS = ('record', 'task', 'roadmap_mission')


def today_start():
    local_today = timezone.localdate()
    return timezone.make_aware(datetime.combine(local_today, time.min), timezone.get_current_timezone())


def review_entry(log):
    for prefix, kind, decision in REVIEW_ACTIONS:
        if log.action.startswith(prefix):
            break
    else:
        return None
    metadata = log.metadata if isinstance(log.metadata, dict) else {}
    record_id = next((metadata[key] for key in RECORD_KEYS if isinstance(metadata.get(key), int)), None)
    user = log.student.user if log.student else None
    return {
        'id': log.pk,
        'kind': kind,
        'decision': decision,
        'record_id': record_id,
        'title': XP_SUFFIX.sub('', log.action[len(prefix):]),
        'student_id': log.student_id,
        'student_name': (user.get_full_name() or user.username) if user else '',
        'at': log.created_at,
    }


class ReviewedTodayView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses=inline_serializer(
            name='ReviewedToday',
            fields={
                'results': drf_serializers.ListField(child=drf_serializers.DictField()),
                'since': drf_serializers.DateTimeField(),
                'limit': drf_serializers.IntegerField(),
            },
        ),
    )
    def get(self, request):
        user = request.user
        if not user.is_task_manager:
            return Response({'detail': 'Only staff who review work have a review history.'}, status=403)
        since = today_start()
        prefixes = Q()
        for prefix, _kind, _decision in REVIEW_ACTIONS:
            prefixes |= Q(action__startswith=prefix)
        logs = scope_students(
            ActivityLog.objects.filter(prefixes, actor=user, created_at__gte=since, student__isnull=False),
            user, via='student',
        ).select_related('student__user').order_by('-created_at', '-id')[:REVIEWED_TODAY_LIMIT]
        results = [entry for entry in map(review_entry, logs) if entry]
        return Response({'results': results, 'since': since, 'limit': REVIEWED_TODAY_LIMIT})
