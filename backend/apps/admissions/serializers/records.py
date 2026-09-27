"""Admissions API serializers — records."""
from rest_framework import serializers
from django.urls import reverse
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
    Task,
)
from .common import (
    GoogleDocsModelSerializer,
    PrivateEvidenceSerializerMixin,
    StudentRecordSerializerMixin,
    VerifiedStudentRecordMixin,
    google_docs_preview_url,
    is_previewable,
    uploaded_file_details,
    validate_private_upload,
)
from .catalog import UniversitySerializer
from core.storage import delete_file_on_commit


class ApplicationStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)

    class Meta:
        model = ApplicationStatusHistory
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            data.pop('note', None)
            data.pop('changed_by', None)
            data.pop('changed_by_name', None)
        return data


class ApplicationSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    university_detail = UniversitySerializer(source='university', read_only=True)
    student_name = serializers.SerializerMethodField()
    status_history = ApplicationStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Application
        fields = '__all__'

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            for field in ('application_portal_url', 'portal_username', 'notes'):
                data.pop(field, None)
        return data

    def validate_status(self, value):
        request = self.context.get('request')
        if request and not request.user.is_counselor_like and value in {
            Application.Status.ACCEPTED,
            Application.Status.REJECTED,
            Application.Status.WAITLISTED,
        }:
            raise serializers.ValidationError('Admission decisions can only be recorded by a counselor.')
        return value


class TaskSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    STUDENT_PROGRESS_FIELDS = {'status', 'student_response', 'submission_url', 'submission_file'}
    STUDENT_SELF_TASK_FIELDS = STUDENT_PROGRESS_FIELDS | {'title', 'description', 'due_date', 'priority'}
    student_name = serializers.SerializerMethodField()
    assigned_by_name = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    submission_preview_url = serializers.SerializerMethodField()
    submission_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    has_submission_file = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = (
            'assigned_by', 'submitted_at', 'is_self_assigned',
            'submission_file_name', 'submission_file_content_type', 'submission_file_size',
        )

    def validate_submission_file(self, upload):
        if upload is None:
            return None
        return validate_private_upload(upload)

    def validate_status(self, value):
        request = self.context.get('request')
        current = getattr(self.instance, 'status', None)
        if request and request.user.is_task_manager and value == Task.Status.APPROVED and current != Task.Status.APPROVED:
            raise serializers.ValidationError('Use the approve action so XP is recorded.')
        if request and not request.user.is_task_manager and value not in {
            Task.Status.TODO,
            Task.Status.IN_PROGRESS,
            Task.Status.SUBMITTED,
        }:
            raise serializers.ValidationError('Students can only update task progress.')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        if request and request.user.role == request.user.Role.STUDENT:
            if not self.instance and attrs.get('status', Task.Status.TODO) != Task.Status.TODO:
                raise serializers.ValidationError({'status': 'A self-task must start in To Do status.'})
            # Approval is the reviewer's decision; reopening it would silently
            # drop the student's progress while the XP stays awarded.
            if self.instance and self.instance.status == Task.Status.APPROVED:
                raise serializers.ValidationError({'status': 'An approved task cannot be changed by a student.'})
            editable_fields = (
                self.STUDENT_SELF_TASK_FIELDS
                if not self.instance or self.instance.is_self_assigned
                else self.STUDENT_PROGRESS_FIELDS
            )
            forbidden = set(attrs) - editable_fields - {'student'}
            if forbidden:
                raise serializers.ValidationError({
                    field: 'Only a teacher or counselor can change this field.' for field in sorted(forbidden)
                })
        return attrs

    def get_submission_preview_url(self, obj):
        return google_docs_preview_url(obj.submission_url)

    def get_has_submission_file(self, obj) -> bool:
        return bool(obj.submission_file)

    @staticmethod
    def _submission_file_metadata(upload):
        name, content_type, size = uploaded_file_details(upload, 'submission')
        return {
            'submission_file_name': name,
            'submission_file_content_type': content_type,
            'submission_file_size': size,
        }

    def create(self, validated_data):
        upload = validated_data.get('submission_file')
        if upload:
            validated_data.update(self._submission_file_metadata(upload))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        file_supplied = 'submission_file' in validated_data
        upload = validated_data.get('submission_file')
        old_name = instance.submission_file.name if file_supplied and instance.submission_file else ''
        old_storage = instance.submission_file.storage if old_name else None
        if upload:
            validated_data.update(self._submission_file_metadata(upload))
        elif file_supplied:
            validated_data.update({
                'submission_file_name': '',
                'submission_file_content_type': '',
                'submission_file_size': 0,
            })
        updated = super().update(instance, validated_data)
        updated_name = updated.submission_file.name if updated.submission_file else ''
        if old_name and old_name != updated_name:
            delete_file_on_commit(old_storage, old_name)
        return updated

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            for field in (
                'student_response', 'submission_url', 'submission_file', 'submission_preview_url',
                'has_submission_file', 'submission_file_name', 'submission_file_content_type',
                'submission_file_size',
            ):
                data.pop(field, None)
        return data

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

    def get_assigned_by_name(self, obj) -> str | None:
        if not obj.assigned_by:
            return None
        return obj.assigned_by.get_full_name() or obj.assigned_by.username


class DocumentSerializer(StudentRecordSerializerMixin, GoogleDocsModelSerializer):
    file = serializers.FileField(write_only=True, required=False, allow_null=True)
    has_file = serializers.SerializerMethodField()
    file_name = serializers.CharField(source='original_file_name', read_only=True)
    file_previewable = serializers.SerializerMethodField()
    file_preview_url = serializers.SerializerMethodField()
    file_download_url = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = '__all__'
        read_only_fields = (
            'original_file_name', 'file_content_type', 'file_size', 'uploaded_by',
        )

    def validate_file(self, upload):
        if upload is None:
            return None
        return validate_private_upload(upload)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        user = request.user if request else None
        file_value = attrs.get('file', getattr(self.instance, 'file', None))
        docs_value = attrs.get('google_docs_url', getattr(self.instance, 'google_docs_url', ''))
        status_value = attrs.get('status', getattr(self.instance, 'status', Document.Status.REQUIRED))

        if user and user.role == User.Role.STUDENT:
            if 'counselor_comment' in attrs:
                raise serializers.ValidationError({
                    'counselor_comment': 'Only a counselor can write document review comments.'
                })
            # Re-sending the stored link (e.g. while renaming) is not new work.
            link_changed = 'google_docs_url' in attrs and (
                not self.instance or attrs['google_docs_url'] != self.instance.google_docs_url
            )
            if 'file' in attrs or link_changed or not self.instance:
                attrs['status'] = Document.Status.UPLOADED
                status_value = Document.Status.UPLOADED
            elif (
                attrs.get('status', self.instance.status) != self.instance.status
                and self.instance.status not in {Document.Status.REQUIRED, Document.Status.REJECTED}
            ):
                # Without new work a student cannot pull a document back out of review.
                raise serializers.ValidationError({
                    'status': 'Upload a new file to resubmit a document that is under review or approved.'
                })
        if status_value != Document.Status.REQUIRED and not file_value and not docs_value:
            raise serializers.ValidationError({
                'file': 'Upload a file or add a Google Docs link before marking this document as uploaded.'
            })
        return attrs

    @staticmethod
    def _file_metadata(upload):
        name, content_type, size = uploaded_file_details(upload, 'document')
        return {'original_file_name': name, 'file_content_type': content_type, 'file_size': size}

    def create(self, validated_data):
        upload = validated_data.get('file')
        if upload:
            validated_data.update(self._file_metadata(upload))
            validated_data['uploaded_by'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        file_supplied = 'file' in validated_data
        upload = validated_data.get('file')
        old_name = instance.file.name if file_supplied and instance.file else ''
        old_storage = instance.file.storage if old_name else None
        if upload:
            validated_data.update(self._file_metadata(upload))
            validated_data['uploaded_by'] = self.context['request'].user
        elif file_supplied:
            # Clearing the file (file=null) must also clear its metadata.
            validated_data.update({'original_file_name': '', 'file_content_type': '', 'file_size': 0})
        updated = super().update(instance, validated_data)
        if old_name and old_name != (updated.file.name or ''):
            delete_file_on_commit(old_storage, old_name)
        return updated

    def validate_status(self, value):
        request = self.context.get('request')
        if request and request.user.role == User.Role.STUDENT and value != Document.Status.UPLOADED:
            raise serializers.ValidationError('Students can only submit documents for counselor review.')
        if request and not request.user.is_counselor_like and value in {Document.Status.APPROVED, Document.Status.REJECTED}:
            raise serializers.ValidationError('Only a counselor can approve or reject documents.')
        return value

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            data.pop('counselor_comment', None)
            data.pop('uploaded_by', None)
        return data

    def get_has_file(self, obj):
        return bool(obj.file)

    def get_file_previewable(self, obj):
        return bool(obj.file) and is_previewable(obj.original_file_name or obj.file.name)

    def _file_url(self, obj, download=False):
        if not obj.file:
            return None
        request = self.context.get('request')
        path = reverse('documents-file', kwargs={'pk': obj.pk})
        if download:
            path += '?download=1'
        return request.build_absolute_uri(path) if request else path

    def get_file_preview_url(self, obj):
        return self._file_url(obj)

    def get_file_download_url(self, obj):
        return self._file_url(obj, download=True)


class AchievementSerializer(PrivateEvidenceSerializerMixin, VerifiedStudentRecordMixin, serializers.ModelSerializer):
    evidence_resource = 'achievements'
    proof_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    has_proof_file = serializers.SerializerMethodField()
    proof_file_previewable = serializers.SerializerMethodField()
    proof_file_preview_url = serializers.SerializerMethodField()
    proof_file_download_url = serializers.SerializerMethodField()
    proof_resource = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Achievement
        fields = '__all__'
        read_only_fields = ('proof_file_name', 'proof_file_content_type', 'proof_file_size')

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username


class ResearchSerializer(VerifiedStudentRecordMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Research
        fields = '__all__'

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username


class ProjectSerializer(VerifiedStudentRecordMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = '__all__'

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username


class InternshipSerializer(VerifiedStudentRecordMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Internship
        fields = '__all__'

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username


class ActivitySerializer(PrivateEvidenceSerializerMixin, VerifiedStudentRecordMixin, GoogleDocsModelSerializer):
    evidence_resource = 'activities'
    proof_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    has_proof_file = serializers.SerializerMethodField()
    proof_file_previewable = serializers.SerializerMethodField()
    proof_file_preview_url = serializers.SerializerMethodField()
    proof_file_download_url = serializers.SerializerMethodField()
    proof_resource = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = '__all__'
        read_only_fields = ('proof_file_name', 'proof_file_content_type', 'proof_file_size')

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username


class HonorSerializer(PrivateEvidenceSerializerMixin, VerifiedStudentRecordMixin, GoogleDocsModelSerializer):
    evidence_resource = 'honors'
    proof_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    has_proof_file = serializers.SerializerMethodField()
    proof_file_previewable = serializers.SerializerMethodField()
    proof_file_preview_url = serializers.SerializerMethodField()
    proof_file_download_url = serializers.SerializerMethodField()
    proof_resource = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Honor
        fields = '__all__'
        read_only_fields = ('proof_file_name', 'proof_file_content_type', 'proof_file_size')

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username


class RecommendationLetterSerializer(StudentRecordSerializerMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()
    file = serializers.FileField(write_only=True, required=False, allow_null=True)
    has_file = serializers.SerializerMethodField()
    file_name = serializers.CharField(source='original_file_name', read_only=True)
    file_previewable = serializers.SerializerMethodField()

    class Meta:
        model = RecommendationLetter
        fields = '__all__'
        read_only_fields = ('original_file_name', 'file_content_type', 'file_size')

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

    def validate_file(self, upload):
        if upload is None:
            return None
        return validate_private_upload(upload)

    def get_has_file(self, obj) -> bool:
        return bool(obj.file)

    def get_file_previewable(self, obj) -> bool:
        return bool(obj.file) and is_previewable(obj.original_file_name or obj.file.name)

    @staticmethod
    def _file_metadata(upload):
        name, content_type, size = uploaded_file_details(upload, 'recommendation')
        return {'original_file_name': name, 'file_content_type': content_type, 'file_size': size}

    def create(self, validated_data):
        upload = validated_data.get('file')
        if upload:
            validated_data.update(self._file_metadata(upload))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        file_supplied = 'file' in validated_data
        upload = validated_data.get('file')
        old_name = instance.file.name if file_supplied and instance.file else ''
        old_storage = instance.file.storage if old_name else None
        if upload:
            validated_data.update(self._file_metadata(upload))
        elif file_supplied:
            validated_data.update({
                'original_file_name': '',
                'file_content_type': '',
                'file_size': 0,
            })
        updated = super().update(instance, validated_data)
        updated_name = updated.file.name if updated.file else ''
        if old_name and old_name != updated_name:
            delete_file_on_commit(old_storage, old_name)
        return updated

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            for field in (
                'recommender_email', 'file', 'google_docs_url', 'google_docs_preview_url', 'notes',
                'has_file', 'file_name', 'file_previewable', 'original_file_name', 'file_content_type',
                'file_size',
            ):
                data.pop(field, None)
        return data

    def validate_status(self, value):
        request = self.context.get('request')
        if request and not request.user.is_counselor_like:
            if value == RecommendationLetter.Status.APPROVED:
                raise serializers.ValidationError('Only a counselor can approve recommendation letters.')
            current = getattr(self.instance, 'status', None)
            if current == RecommendationLetter.Status.APPROVED and value != current:
                raise serializers.ValidationError('An approved recommendation letter cannot be reopened by a student.')
        return value


class MeetingNoteSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    counselor_name = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = MeetingNote
        fields = '__all__'
        # The author is whoever wrote the note (MeetingNoteViewSet.perform_create).
        read_only_fields = ('counselor',)

    def get_counselor_name(self, obj) -> str | None:
        if not obj.counselor:
            return None
        return obj.counselor.get_full_name() or obj.counselor.username

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            for field in ('summary', 'next_steps'):
                data.pop(field, None)
        return data


class NotificationSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = '__all__'
        # Set by the server, which knows what the notice points at.
        read_only_fields = ('kind', 'target_id')

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username


class ActivityLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = '__all__'

    def get_actor_name(self, obj) -> str | None:
        if not obj.actor:
            return None
        return obj.actor.get_full_name() or obj.actor.username

    def get_student_name(self, obj) -> str | None:
        if not obj.student:
            return None
        return obj.student.user.get_full_name() or obj.student.user.username
