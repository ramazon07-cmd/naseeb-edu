"""Admissions API views — records."""
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from apps.users.models import User
from ..models import (
    Achievement,
    Activity,
    ActivityLog,
    Application,
    ApplicationStatusHistory,
    Document,
    Honor,
    Internship,
    MeetingNote,
    Notification,
    Project,
    RecommendationLetter,
    Research,
    StudentMessage,
    Task,
    XPTransaction,
)
from ..serializers import (
    AchievementSerializer,
    ActivitySerializer,
    ActivityLogSerializer,
    ApplicationSerializer,
    DocumentSerializer,
    HonorSerializer,
    InternshipSerializer,
    MeetingNoteSerializer,
    NotificationSerializer,
    ProjectSerializer,
    RecommendationLetterSerializer,
    ResearchSerializer,
    StudentProfileSerializer,
    TaskSerializer,
)
from ..progress import OPEN_TASK_STATUSES
from ..services import TASK_XP_BY_PRIORITY, award_approval_xp
from .common import (
    RECORD_ORDERING,
    ScopedQuerysetMixin,
    StaffControlledWorkMixin,
    StudentRecordListMixin,
    serve_private_file,
)
from .messaging import unread_channel_messages

# Badges show "99+" past this, so counting further is wasted work.
SUMMARY_COUNT_LIMIT = 100


def bounded_count(queryset, limit=SUMMARY_COUNT_LIMIT):
    return queryset.order_by()[:limit].count()


class ApplicationViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    queryset = Application.objects.select_related(
        'student__user', 'student__assigned_counselor', 'university',
    ).prefetch_related('status_history__changed_by', 'university__programs').all()
    search_fields = ('program', 'university__name')
    choice_filters = {'status': ('status', Application.Status.choices), 'tier': ('tier', Application._meta.get_field('tier').choices)}
    date_filters = {**StudentRecordListMixin.date_filters, 'deadline': 'deadline'}

    def get_queryset(self):
        return self.filter_for_user(self.queryset)

    def perform_create(self, serializer):
        application = serializer.save()
        ApplicationStatusHistory.objects.create(
            application=application,
            status=application.status,
            changed_by=self.request.user,
            note='Application created',
        )

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        application = serializer.save()
        if application.status != old_status:
            ApplicationStatusHistory.objects.create(
                application=application,
                status=application.status,
                changed_by=self.request.user,
                note='Status updated',
            )


class TaskViewSet(StudentRecordListMixin, StaffControlledWorkMixin, viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    queryset = Task.objects.select_related('student__user', 'assigned_by', 'student__assigned_counselor').all()
    search_fields = ('title',)
    choice_filters = {'status': ('status', Task.Status.choices), 'priority': ('priority', Task.Priority.choices)}
    bool_filters = {'self_assigned': 'is_self_assigned'}
    date_filters = {**StudentRecordListMixin.date_filters, 'due': 'due_date'}
    ordering_options = {**RECORD_ORDERING, 'due': ('due_date', 'id'), '-due': ('-due_date', '-id')}
    default_cursor_ordering = 'due'

    def get_queryset(self):
        return self.filter_work_for_user(self.queryset)

    def apply_filters(self, queryset, params):
        queryset = super().apply_filters(queryset, params)
        value = params.get('open')
        if value in (None, ''):
            return queryset
        if value not in {'true', 'false', '1', '0'}:
            raise ValidationError({'open': ['Use true or false.']})
        # Open = work the student still owes (see progress.OPEN_TASK_STATUSES).
        if value in {'true', '1'}:
            return queryset.filter(status__in=OPEN_TASK_STATUSES)
        return queryset.exclude(status__in=OPEN_TASK_STATUSES)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(
            assigned_by=user,
            is_self_assigned=user.role == User.Role.STUDENT,
            status=Task.Status.TODO if user.role == User.Role.STUDENT else serializer.validated_data.get('status', Task.Status.TODO),
        )

    def perform_update(self, serializer):
        target_status = serializer.validated_data.get('status', serializer.instance.status)
        response_changed = bool(
            {'student_response', 'submission_url', 'submission_file'}
            & set(serializer.validated_data)
        )
        submitted_now = target_status == Task.Status.SUBMITTED and (
            serializer.instance.status != Task.Status.SUBMITTED or response_changed
        )
        serializer.save(submitted_at=timezone.now() if submitted_now else serializer.instance.submitted_at)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if not request.user.is_task_manager:
            return Response({'detail': 'Only a teacher or counselor can approve tasks.'}, status=403)
        scoped_task = self.get_object()
        with transaction.atomic():
            task = Task.objects.select_for_update(of=('self',)).select_related('student').get(pk=scoped_task.pk)
            if task.status not in {Task.Status.SUBMITTED, Task.Status.APPROVED}:
                return Response({'detail': 'The student must submit the task before approval.'}, status=400)
            newly_approved = task.status != Task.Status.APPROVED
            task.status = Task.Status.APPROVED
            task.save(update_fields=['status', 'updated_at'])
            xp_amount = 0 if task.is_self_assigned else TASK_XP_BY_PRIORITY[task.priority]
            xp_created = False
            if xp_amount:
                _, xp_created = award_approval_xp(
                    student=task.student,
                    source_type=XPTransaction.Source.TASK,
                    source_id=task.id,
                    amount=xp_amount,
                    reason=f'Task approved: {task.title}',
                    awarded_by=request.user,
                )
            # One entry per approval event. get_or_create keyed on the text merged
            # two tasks with the same title (and raised once duplicates existed).
            if newly_approved:
                ActivityLog.objects.create(
                    actor=request.user,
                    student=task.student,
                    action=(
                        f'Task approved: {task.title} (+{xp_amount} XP)'
                        if xp_amount
                        else f'Self-task approved: {task.title} (no XP)'
                    ),
                    metadata={'task': task.id},
                )
        task.student.refresh_from_db()
        data = TaskSerializer(task, context={'request': request}).data
        data['xp_awarded'] = xp_amount if xp_created else 0
        data['student_leveling'] = StudentProfileSerializer(task.student, context={'request': request}).data
        return Response(data)

    @action(detail=True, methods=['get'], url_path='submission-file')
    def submission_file(self, request, pk=None):
        task = self.get_object()
        if request.user.is_organization:
            # Task submission content is hidden from school organizations by
            # policy (see TaskSerializer.to_representation) — keep this
            # streaming endpoint from becoming a bypass of that.
            raise Http404('This task has no submitted file.')
        if not task.submission_file:
            raise Http404('This task has no submitted file.')
        return serve_private_file(
            request,
            task.submission_file,
            original_name=task.submission_file_name,
            content_type=task.submission_file_content_type,
            missing_message='The uploaded file is unavailable. Contact support.',
        )



class DocumentViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    queryset = Document.objects.select_related('student__user', 'student__assigned_counselor').all()
    search_fields = ('title',)
    choice_filters = {
        'status': ('status', Document.Status.choices),
        'document_type': ('document_type', Document.Type.choices),
    }

    def get_queryset(self):
        return self.filter_for_user(self.queryset)

    @action(detail=True, methods=['get'], url_path='file')
    def file(self, request, pk=None):
        document = self.get_object()
        if not document.file:
            raise Http404('This document has no uploaded file.')
        return serve_private_file(
            request,
            document.file,
            original_name=document.original_file_name,
            content_type=document.file_content_type,
            missing_message='The uploaded file is unavailable. Contact support.',
        )



class PrivateEvidenceViewSetMixin:
    @action(detail=True, methods=['get'], url_path='proof-file')
    def proof_file(self, request, pk=None):
        record = self.get_object()
        if not record.proof_file:
            raise Http404('This record has no proof file.')
        return serve_private_file(
            request,
            record.proof_file,
            original_name=record.proof_file_name,
            content_type=record.proof_file_content_type,
            missing_message='The proof file is unavailable. Contact support.',
        )



class AchievementViewSet(PrivateEvidenceViewSetMixin, StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = AchievementSerializer
    queryset = Achievement.objects.select_related('student__user', 'student__assigned_counselor').all()
    search_fields = ('title',)
    choice_filters = {'category': ('category', Achievement.Category.choices)}

    def get_queryset(self):
        return self.filter_for_user(self.queryset)

class ResearchViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ResearchSerializer
    queryset = Research.objects.select_related('student__user', 'student__school').all()
    search_fields = ('title',)

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class ProjectViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    queryset = Project.objects.select_related('student__user', 'student__school').all()
    search_fields = ('title',)

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class InternshipViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = InternshipSerializer
    queryset = Internship.objects.select_related('student__user', 'student__school').all()
    search_fields = ('organization', 'position')

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class ActivityViewSet(PrivateEvidenceViewSetMixin, StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ActivitySerializer
    queryset = Activity.objects.select_related('student__user', 'student__school').all()
    search_fields = ('name',)
    choice_filters = {'activity_type': ('activity_type', Activity.Type.choices)}

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class HonorViewSet(PrivateEvidenceViewSetMixin, StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = HonorSerializer
    queryset = Honor.objects.select_related('student__user', 'student__school').all()
    search_fields = ('title',)
    choice_filters = {'level': ('level', Honor.Level.choices)}

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class RecommendationLetterViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = RecommendationLetterSerializer
    queryset = RecommendationLetter.objects.select_related('student__user', 'student__school').all()
    search_fields = ('recommender_name',)
    choice_filters = {'status': ('status', RecommendationLetter.Status.choices)}

    def get_queryset(self):
        return self.filter_for_user(self.queryset)

    @action(detail=True, methods=['get'], url_path='file')
    def file(self, request, pk=None):
        letter = self.get_object()
        if request.user.is_organization:
            # The letter file is hidden from school organizations by policy
            # (see RecommendationLetterSerializer.to_representation) — keep
            # this streaming endpoint from becoming a bypass of that.
            raise Http404('This recommendation letter has no uploaded file.')
        if not letter.file:
            raise Http404('This recommendation letter has no uploaded file.')
        return serve_private_file(
            request,
            letter.file,
            original_name=letter.original_file_name,
            content_type=letter.file_content_type,
            missing_message='The uploaded file is unavailable. Contact support.',
        )


class MeetingNoteViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = MeetingNoteSerializer
    queryset = MeetingNote.objects.select_related('student__user', 'student__assigned_counselor', 'counselor').all()
    search_fields = ('title',)
    date_filters = {**StudentRecordListMixin.date_filters, 'meeting': 'meeting_date'}

    def get_queryset(self):
        return self.filter_for_user(self.queryset)

    def perform_create(self, serializer):
        serializer.save(counselor=self.request.user)


class NotificationViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.select_related('student__user', 'student__assigned_counselor').all()
    # ?cursor= pages newest first without OFFSET scans.
    keyset_ordering = ('-created_at', '-id')

    def get_queryset(self):
        queryset = self.filter_for_user(self.queryset).order_by(*self.keyset_ordering)
        unread = self.request.query_params.get('unread')
        if unread in ['1', 'true', 'True']:
            queryset = queryset.filter(is_read=False)
        return queryset

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read', 'updated_at'])
        return Response(NotificationSerializer(notification, context={'request': request}).data)

    # The actions below act on the caller's own student record only. The
    # notice list is shared with the counselor; a counselor clearing it would
    # hide alerts the student never saw.

    @action(detail=False, methods=['post'], url_path='read-all')
    def read_all(self, request):
        updated = Notification.objects.filter(student__user=request.user, is_read=False).update(
            is_read=True, updated_at=timezone.now(),
        )
        return Response({'updated': updated})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Unread counts behind the notification bell, in three bounded queries."""
        user = request.user
        return Response({
            'unread': bounded_count(Notification.objects.filter(student__user=user, is_read=False)),
            'counselor_messages_unread': bounded_count(
                StudentMessage.objects.filter(recipient=user, student__user=user, is_read=False),
            ),
            'chats_unread': bounded_count(unread_channel_messages(user)),
            'limit': SUMMARY_COUNT_LIMIT,
        })


class ActivityLogViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ActivityLogSerializer
    queryset = ActivityLog.objects.select_related('actor', 'student__user', 'student__assigned_counselor').all()

    def get_queryset(self):
        return self.filter_for_user(self.queryset)
