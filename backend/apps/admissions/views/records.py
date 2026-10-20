"""Admissions API views — records."""
from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import get_language
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from apps.users.entitlements import feature_enabled
from apps.users.models import User
from apps.users.throttles import WindowRateThrottle
from core.exceptions import CodedError
from .. import ai_budget, rec_letter_ai
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
    StudentProfile,
    Task,
    University,
)
from ..pricing import with_cost
from ..serializers import (
    AchievementSerializer,
    ActivitySerializer,
    ActivityLogSerializer,
    ApplicationSerializer,
    DocumentSerializer,
    HonorSerializer,
    InternshipSerializer,
    LetterStudentReviewSerializer,
    LetterSuggestionRequestSerializer,
    MeetingNoteSerializer,
    NotificationSerializer,
    ProjectSerializer,
    RecommendationLetterSerializer,
    ResearchSerializer,
    StudentProfileSerializer,
    TaskSerializer,
)
from ..serializers.common import UNAVAILABLE_STUDENT
from ..progress import DOCUMENT_AWAITING_REVIEW, OPEN_TASK_STATUSES
from ..progress_cache import invalidate_progress_summary
from ..scoping import scope_students, without_deactivated_students
from ..streaming import release_db_connection
from ..services import record_approval_note
from .common import (
    RECORD_ORDERING,
    ApproveMixin,
    ScopedQuerysetMixin,
    SendBackMixin,
    StaffControlledWorkMixin,
    StudentRecordListMixin,
    clean_note,
    serve_private_file,
)
from .messaging import unread_channel_messages

# Badges show "99+" past this, so counting further is wasted work.
SUMMARY_COUNT_LIMIT = 100
# Students one bulk task assignment may name.
BULK_TASK_LIMIT = 500


def bounded_count(queryset, limit=SUMMARY_COUNT_LIMIT):
    return queryset.order_by()[:limit].count()


class ApplicationViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    # The university comes with its cost annotation (pricing.py) for university_detail.
    queryset = Application.objects.select_related('student__user', 'student__assigned_counselor').prefetch_related(
        'status_history__changed_by', Prefetch('university', queryset=with_cost(University.objects.prefetch_related('programs'))),
    ).all()
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
        with transaction.atomic():
            # Recheck under the row lock: an open student plan must not undo a
            # counselor's decision or record a transition from an outdated status.
            application = self.get_queryset().select_for_update(of=('self',)).get(pk=serializer.instance.pk)
            serializer.instance = application
            if 'status' in serializer.validated_data:
                serializer.validate_status(serializer.validated_data['status'])
            old_status = application.status
            application = serializer.save()
            if application.status != old_status:
                ApplicationStatusHistory.objects.create(
                    application=application,
                    status=application.status,
                    changed_by=self.request.user,
                    note='Status updated',
                )
                # This locked instance has its own prefetched history; include the new entry in the response.
                getattr(application, '_prefetched_objects_cache', {}).pop('status_history', None)


class TaskViewSet(StudentRecordListMixin, StaffControlledWorkMixin, SendBackMixin, viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    send_back_statuses = (Task.Status.SUBMITTED,)
    send_back_to = Task.Status.IN_PROGRESS
    send_back_notice_kind = 'task'
    send_back_label = 'Task'
    send_back_managers = 'task_manager'
    queryset = Task.objects.select_related('student__user', 'assigned_by', 'student__assigned_counselor',
                                         'submission_essay__student__user', 'submission_essay__student__school').defer(
                                             'submission_essay__content', 'submission_essay__prompt', 'submission_essay__counselor_comment').all()
    search_fields = ('title',)
    choice_filters = {'status': ('status', Task.Status.choices), 'priority': ('priority', Task.Priority.choices)}
    int_filters = {**StudentRecordListMixin.int_filters, 'submission_essay': 'submission_essay_id'}
    bool_filters = {'self_assigned': 'is_self_assigned'}
    date_filters = {**StudentRecordListMixin.date_filters, 'due': 'due_date'}
    ordering_options = {**RECORD_ORDERING, 'due': ('due_date', 'id'), '-due': ('-due_date', '-id')}
    default_cursor_ordering = 'due'

    def get_queryset(self):
        return self.filter_work_for_user(self.queryset)

    def apply_filters(self, queryset, params):
        queryset = super().apply_filters(queryset, params)
        if params.get('status') == Task.Status.SUBMITTED and not params.get('student'):
            # The review queue: it matches the dashboard count, which skips deactivated students.
            queryset = without_deactivated_students(queryset)
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
        with transaction.atomic():
            if self.request.user.role == User.Role.STUDENT:
                current = Task.objects.select_for_update(of=('self',)).get(pk=serializer.instance.pk)
                if current.status == Task.Status.APPROVED or (not current.is_self_assigned and current.status == Task.Status.SUBMITTED):
                    raise ValidationError({'status': 'Your response is awaiting review. Your counselor can return it for changes.'})
                essay = serializer.validated_data.get('submission_essay', current.submission_essay)
                if essay:
                    from ..task_submissions import prepare_essay_submission
                    serializer.validated_data['submission_essay'] = prepare_essay_submission(current, essay.pk, self.request.user)
            target_status = serializer.validated_data.get('status', serializer.instance.status)
            response_changed = bool(
                {'student_response', 'submission_url', 'submission_file', 'submission_essay'}
                & set(serializer.validated_data)
            )
            submitted_now = target_status == Task.Status.SUBMITTED and (
                serializer.instance.status != Task.Status.SUBMITTED or response_changed
            )
            serializer.save(submitted_at=timezone.now() if submitted_now else serializer.instance.submitted_at)

    @action(detail=False, methods=['post'], url_path='bulk')
    def bulk(self, request):
        """One task for many students: ``{students: [ids], title, due_date, ...}``.

        The task fields are validated as a single create validates them. Every
        student must be in the caller's scope, or nothing is created.
        """
        if not request.user.is_task_manager:
            return Response({'detail': 'Only a teacher or counselor can assign tasks.'}, status=403)
        raw = request.data.get('students')
        if not isinstance(raw, list) or not raw:
            raise ValidationError({'students': ['Choose at least one student.']})
        if len(raw) > BULK_TASK_LIMIT:
            raise ValidationError({'students': [f'Assign to {BULK_TASK_LIMIT} students or fewer at once.']})
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in raw):
            raise ValidationError({'students': ['Use student ids.']})
        ids = list(dict.fromkeys(raw))
        found = set(scope_students(StudentProfile.objects.filter(pk__in=ids), request.user).values_list('pk', flat=True))
        if len(found) != len(ids):
            raise ValidationError({'students': [UNAVAILABLE_STUDENT]})
        fields = {key: value for key, value in request.data.items() if key not in {'students', 'student', 'submission_file'}}
        serializer = self.get_serializer(data={**fields, 'student': ids[0]})
        serializer.is_valid(raise_exception=True)
        values = {key: value for key, value in serializer.validated_data.items() if key != 'student'}
        values.setdefault('status', Task.Status.TODO)
        with transaction.atomic():
            tasks = Task.objects.bulk_create([
                Task(student_id=student_id, assigned_by=request.user, is_self_assigned=False, **values) for student_id in ids
            ])
            # bulk_create skips post_save, which drops the cached progress summary on a single create.
            transaction.on_commit(invalidate_progress_summary)
        return Response({'created': len(tasks), 'ids': [task.pk for task in tasks]}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if not request.user.is_task_manager:
            return Response({'detail': 'Only a teacher or counselor can approve tasks.'}, status=403)
        # Validate the note first: a bad note must not leave the task approved.
        note = clean_note(request)
        scoped_task = self.get_object()
        with transaction.atomic():
            task = Task.objects.select_for_update(of=('self',)).select_related('student').get(pk=scoped_task.pk)
            if task.status not in {Task.Status.SUBMITTED, Task.Status.APPROVED}:
                return Response({'detail': 'The student must submit the task before approval.'}, status=400)
            if task.status == Task.Status.SUBMITTED and task.submission_essay_id and not (task.student_response.strip() or task.submission_url or task.submission_file):
                from ..task_submissions import essay_submission_detail
                if essay_submission_detail(task, request.user) is None or not task.submission_essay.content.strip():
                    raise ValidationError({'submission_essay': 'The attached essay is no longer shared or available. Return the task to the student.'})
            newly_approved = task.status != Task.Status.APPROVED
            task.status = Task.Status.APPROVED
            task.save(update_fields=['status', 'updated_at'])
            # One entry per approval event. get_or_create keyed on the text merged
            # two tasks with the same title (and raised once duplicates existed).
            if newly_approved:
                ActivityLog.objects.create(
                    actor=request.user,
                    student=task.student,
                    action=f'Task approved: {task.title}',
                    metadata={'task': task.id},
                )
        record_approval_note(record=task, student=task.student, note=note, notice_kind='task')
        task.student.refresh_from_db()
        data = TaskSerializer(task, context={'request': request}).data
        data['xp_awarded'] = 0
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



DOCUMENT_REVIEW_STATUSES = (Document.Status.UPLOADED, Document.Status.REVIEWING)


class DocumentViewSet(StudentRecordListMixin, ScopedQuerysetMixin, ApproveMixin, SendBackMixin, viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    approve_notice_kind = 'document'
    approve_label = 'Document'

    def apply_approval(self, record):
        record.status = Document.Status.APPROVED
        return ['status']

    def is_approved(self, record):
        return record.status == Document.Status.APPROVED

    def awaiting_review(self, record):
        # A document is its file: nothing to approve until one is attached.
        return record.status in DOCUMENT_REVIEW_STATUSES and bool(record.file or record.google_docs_url)
    send_back_statuses = DOCUMENT_REVIEW_STATUSES
    send_back_to = Document.Status.REJECTED
    send_back_notice_kind = 'document'
    send_back_label = 'Document'

    def apply_filters(self, queryset, params):
        queryset = super().apply_filters(queryset, params)
        value = params.get('awaiting_review')
        if value in (None, ''):
            return queryset
        if value not in {'true', 'false', '1', '0'}:
            raise ValidationError({'awaiting_review': ['Use true or false.']})
        waiting = DOCUMENT_AWAITING_REVIEW
        if value in {'true', '1'}:
            waiting_qs = queryset.filter(waiting)
            return waiting_qs if params.get('student') else without_deactivated_students(waiting_qs)
        return queryset.exclude(waiting)
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



class AchievementViewSet(PrivateEvidenceViewSetMixin, StudentRecordListMixin, ScopedQuerysetMixin, ApproveMixin, SendBackMixin, viewsets.ModelViewSet):
    serializer_class = AchievementSerializer
    approve_label = 'Achievement'

    def apply_approval(self, record):
        record.verified = True
        return ['verified']

    def is_approved(self, record):
        return record.verified

    def awaiting_review(self, record):
        # Any unverified record may be approved, including one sent back or un-verified with a note.
        return not record.verified
    queryset = Achievement.objects.select_related('student__user', 'student__assigned_counselor').all()
    search_fields = ('title',)
    choice_filters = {'category': ('category', Achievement.Category.choices)}
    bool_filters = {'verified': 'verified'}
    send_back_label = 'Achievement'

    def get_queryset(self):
        return self.filter_for_user(self.queryset)

    def apply_filters(self, queryset, params):
        queryset = super().apply_filters(queryset, params)
        value = params.get('awaiting_review')
        if value in (None, ''):
            return queryset
        if value not in {'true', 'false', '1', '0'}:
            raise ValidationError({'awaiting_review': ['Use true or false.']})
        # Waiting for the counselor: not verified, and not already sent back.
        waiting = Q(verified=False, counselor_comment='')
        if value in {'true', '1'}:
            waiting_qs = queryset.filter(waiting)
            return waiting_qs if params.get('student') else without_deactivated_students(waiting_qs)
        return queryset.exclude(waiting)

    def send_back_refusal(self, record):
        if record.verified:
            return 'This work is not waiting for review.'
        # Once per change: a record not touched since its last send-back is still with the student.
        last = ActivityLog.objects.filter(
            student_id=record.student_id, action__startswith=f'{self.send_back_label} sent back:',
            metadata__record=record.pk, metadata__kind=self.send_back_label.lower(),
        ).values_list('created_at', flat=True).first()
        if last is not None and record.updated_at <= last:
            return 'Already sent back; waiting for the student.'
        return None

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


# Translated by code in the app (translations/errorCodes.js) and by text for older clients (api_messages).
LETTER_CHANGED_MESSAGE = 'This letter has changed. Reopen it and read the latest text before reviewing.'


class LetterSuggestThrottle(WindowRateThrottle):
    """Suggestions follow the counselor's typing: a short minimum interval plus an hourly cap."""

    scope = 'rec_letter_suggest'
    sliding = False
    cache_prefix = 'rec-letter'

    def get_cache_key(self, request, view):
        return str(request.user.pk) if request.user.is_authenticated else None

    def get_limits(self):
        return [
            (1, settings.REC_LETTER_SUGGEST_MIN_INTERVAL_SECONDS),
            (settings.REC_LETTER_SUGGEST_HOURLY_LIMIT, 3600),
        ]


class RecommendationLetterViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = RecommendationLetterSerializer
    queryset = RecommendationLetter.objects.select_related('student__user', 'student__school').all()
    search_fields = ('recommender_name',)
    choice_filters = {'status': ('status', RecommendationLetter.Status.choices)}

    def get_queryset(self):
        return self.filter_for_user(self.queryset)

    @action(detail=False, methods=['post'], url_path='suggest')
    def suggest(self, request):
        """Ideas for the letter a counselor is writing, drawn from the student's profile."""
        if not request.user.is_counselor_like:
            raise PermissionDenied('Only a counselor can ask for letter suggestions.')
        payload = LetterSuggestionRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        throttle = LetterSuggestThrottle()
        if not throttle.allow_request(request, self):
            self.throttled(request, throttle.wait())
        data = payload.validated_data
        # The school name is read during the AI call (to keep it out of the prompt),
        # which runs after the connection is released: load it now.
        student = get_object_or_404(scope_students(StudentProfile.objects.select_related('user', 'school'), request.user), pk=data['student'])
        facts = rec_letter_ai.profile_facts(student)
        if (
            rec_letter_ai.gateway_configured()
            and feature_enabled(request.user, 'ai_assistant')
            and ai_budget.consume('recommendation_letter', request.user)
        ):
            release_db_connection()  # don't hold a pooled connection during the AI call
            language = getattr(request, 'LANGUAGE_CODE', None) or get_language()
            try:
                suggestions = rec_letter_ai.ai_suggestions(student, facts, data['draft'], letter=data, language=language)
                return Response({'source': 'ai', 'suggestions': suggestions + rec_letter_ai.missing_facts(facts, data['draft'])})
            except rec_letter_ai.SuggestionsUnavailable:
                pass
        return Response({'source': 'profile', 'suggestions': rec_letter_ai.local_suggestions(facts, data['draft'])})

    @action(detail=True, methods=['post'], url_path='student-review')
    def student_review(self, request, pk=None):
        """The student confirms the letter their counselor shared, or asks for changes."""
        letter = self.get_object()
        if letter.student.user_id != request.user.id:
            raise PermissionDenied('Only the student can review their letter.')
        if not (letter.shared_with_student and letter.body):
            raise ValidationError({'detail': ['Your counselor has not shared this letter with you yet.']})
        payload = LetterStudentReviewSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        # The decision is about the exact text the student read.
        if payload.validated_data['reviewed_body'] != letter.body:
            raise CodedError(LETTER_CHANGED_MESSAGE, 'letter_changed', status.HTTP_409_CONFLICT)
        decision = payload.validated_data['decision']
        changes = decision == RecommendationLetter.StudentReview.CHANGES_REQUESTED
        now = timezone.now()
        # The counselor can edit or unshare while this request is being validated.
        # Write the review only while the exact text remains shared.
        updated = self.get_queryset().filter(pk=letter.pk, body=letter.body, shared_with_student=True).update(
            student_review=decision,
            student_review_note=payload.validated_data['note'].strip() if changes else '',
            student_reviewed_at=now,
            updated_at=now,
        )
        if not updated:
            raise CodedError(LETTER_CHANGED_MESSAGE, 'letter_changed', status.HTTP_409_CONFLICT)
        letter.refresh_from_db()
        return Response(self.get_serializer(letter).data)

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


def audience_filter(user):
    """Student notices (no recipient) for everyone who shares the student's feed; addressed ones for their recipient.

    A student never sees a notice addressed to a staff member, even though it is filed under them.
    """
    if user.role == User.Role.STUDENT:
        return Q(recipient__isnull=True)
    return Q(recipient__isnull=True) | Q(recipient=user)


def reads_addressed_notices(user):
    """Staff whose own addressed notices (e.g. a meeting request) are theirs whatever the student's scope."""
    return user.is_counselor_like or user.role in {User.Role.TEACHER, User.Role.ORGANIZATION}


class NotificationViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.select_related('student__user', 'student__assigned_counselor').all()
    # ?cursor= pages newest first without OFFSET scans.
    keyset_ordering = ('-created_at', '-id')

    def get_queryset(self):
        user = self.request.user
        mine = self.request.query_params.get('mine') in ['1', 'true', 'True']
        if reads_addressed_notices(user) and (mine or not user.is_counselor_like):
            # ?mine=true: a staff member's bell, only the notices addressed to them.
            # Teachers and school staff get only this.
            queryset = self.addressed_notices(self.queryset)
        else:
            queryset = self.filter_for_user(self.queryset).filter(audience_filter(user))
            if user.is_counselor_like:
                # Opening or reading one of their addressed notices by id, outside their student scope.
                queryset = queryset | self.addressed_notices(self.queryset)
        queryset = queryset.order_by(*self.keyset_ordering)
        unread = self.request.query_params.get('unread')
        if unread in ['1', 'true', 'True']:
            queryset = queryset.filter(is_read=False)
        return queryset

    def addressed_notices(self, queryset):
        """Notices addressed to the caller about a student they serve or one at their current school.

        Being booked does not need the student's assignment (any staff member of the
        student's school can be), but a student who left that school is no longer theirs.
        """
        user = self.request.user
        addressed = queryset.filter(recipient=user)
        scoped = self.filter_for_user(addressed)
        if user.school_id:
            return scoped | addressed.filter(student__school_id=user.school_id)
        return scoped

    def bell_notices(self):
        """The notices behind the caller's bell: a student's own feed, or those addressed to a staff member.

        A staff member never counts or clears a student's notices: the student
        shares that feed with their counselor and would lose alerts they never saw.
        """
        user = self.request.user
        if user.role == User.Role.STUDENT:
            return Notification.objects.filter(student__user=user, recipient__isnull=True)
        if reads_addressed_notices(user):
            return self.addressed_notices(Notification.objects.all())
        return self.filter_for_user(Notification.objects.filter(recipient=user))

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read', 'updated_at'])
        return Response(NotificationSerializer(notification, context={'request': request}).data)

    @action(detail=False, methods=['post'], url_path='read-all')
    def read_all(self, request):
        updated = self.bell_notices().filter(is_read=False).update(is_read=True, updated_at=timezone.now())
        return Response({'updated': updated})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Unread counts behind the notification bell, in three bounded queries."""
        user = request.user
        return Response({
            'unread': bounded_count(self.bell_notices().filter(is_read=False)),
            'counselor_messages_unread': bounded_count(
                StudentMessage.objects.filter(recipient=user, student__user=user, is_read=False),
            ),
            'chats_unread': bounded_count(unread_channel_messages(user)),
            'limit': SUMMARY_COUNT_LIMIT,
        })


class ActivityLogViewSet(StudentRecordListMixin, ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ActivityLogSerializer
    queryset = ActivityLog.objects.select_related('actor', 'student__user', 'student__assigned_counselor').all()
    choice_filters = {
        'kind': ('metadata__kind', ('document', 'task', 'achievement', 'roadmap mission')),
    }

    def get_queryset(self):
        return self.filter_for_user(self.queryset)
