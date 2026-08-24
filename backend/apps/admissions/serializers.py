from rest_framework import serializers
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from pathlib import Path
from urllib.parse import urlparse
import mimetypes
import zipfile
import codecs
from PIL import Image, UnidentifiedImageError
from django.contrib.auth.password_validation import validate_password
from django.db.models import Count
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from apps.users.models import User
from apps.users.credentials import issue_temporary_credential
from apps.users.serializers import UserSerializer
from .models import (
    Achievement,
    Activity,
    ActivityLog,
    Application,
    ApplicationStatusHistory,
    Booking,
    ChannelMembership,
    ChannelMessage,
    CommunityPost,
    Document,
    Essay,
    EssayAIReview,
    EssayRevision,
    Honor,
    Internship,
    LevelApproval,
    MeetingNote,
    MessageChannel,
    MessageReport,
    Notification,
    OpportunityProgram,
    ParentStudentLink,
    ProgramService,
    Project,
    RecommendationLetter,
    Research,
    ResourceLibraryItem,
    RoadmapMission,
    CounselorRoadmap,
    CounselorRoadmapMission,
    CounselorRoadmapTemplate,
    CounselorRoadmapTemplateMission,
    School,
    ScreenTimeDaily,
    Scholarship,
    StoreItem,
    SupportTicket,
    StudentProfile,
    StudentMessage,
    Task,
    University,
    XPTransaction,
)


def google_docs_document_id(value):
    if not value:
        return None
    parsed = urlparse(str(value))
    if parsed.scheme != 'https' or parsed.hostname != 'docs.google.com':
        return None
    parts = [part for part in parsed.path.split('/') if part]
    if not parts or parts[0] != 'document':
        return None
    for index, part in enumerate(parts[:-1]):
        if part == 'd' and parts[index + 1]:
            return parts[index + 1]
    return None


def validate_google_docs_url(value):
    if value and not google_docs_document_id(value):
        raise serializers.ValidationError('Use a valid https://docs.google.com/document/... link.')
    return value


def google_docs_preview_url(value):
    document_id = google_docs_document_id(value)
    return f'https://docs.google.com/document/d/{document_id}/preview' if document_id else None


def validate_private_upload(upload):
    """Validate private documents and evidence using one production-safe policy."""
    extension = Path(upload.name or '').suffix.lower()
    allowed = set(settings.DOCUMENT_ALLOWED_EXTENSIONS)
    if extension not in allowed:
        raise serializers.ValidationError(
            f'Unsupported file type. Allowed: {", ".join(sorted(allowed))}.'
        )
    if upload.size > settings.DOCUMENT_MAX_UPLOAD_SIZE:
        limit_mb = settings.DOCUMENT_MAX_UPLOAD_SIZE // (1024 * 1024)
        raise serializers.ValidationError(f'File is larger than the {limit_mb} MB limit.')
    if upload.size == 0:
        raise serializers.ValidationError('The selected file is empty.')

    try:
        head = upload.read(min(upload.size, 4096))
        upload.seek(0)
        if extension == '.pdf' and not head.startswith(b'%PDF-'):
            raise serializers.ValidationError('This file is not a valid PDF.')
        if extension in {'.png', '.jpg', '.jpeg', '.webp'}:
            try:
                Image.open(upload).verify()
            except (UnidentifiedImageError, OSError, SyntaxError):
                raise serializers.ValidationError('This file is not a valid image.')
            finally:
                upload.seek(0)
        if extension == '.heic' and b'ftyp' not in head[:32]:
            raise serializers.ValidationError('This file is not a valid HEIC image.')
        if extension in {'.doc', '.xls', '.ppt'} and not head.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
            raise serializers.ValidationError('This legacy Office file is invalid.')
        if extension == '.rtf' and not head.lstrip().startswith(b'{\\rtf'):
            raise serializers.ValidationError('This file is not a valid RTF document.')
        if extension in {'.txt', '.csv'}:
            if b'\x00' in head:
                raise serializers.ValidationError('Text documents cannot contain binary data.')
            codecs.getincrementaldecoder('utf-8-sig')().decode(head, final=False)
        if extension in {'.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp'}:
            with zipfile.ZipFile(upload) as archive:
                names = archive.namelist()
                required_prefix = {
                    '.docx': 'word/', '.xlsx': 'xl/', '.pptx': 'ppt/',
                    '.odt': 'content.xml', '.ods': 'content.xml', '.odp': 'content.xml',
                }[extension]
                if not any(name == required_prefix or name.startswith(required_prefix) for name in names):
                    raise serializers.ValidationError('The Office document structure is invalid.')
            upload.seek(0)
    except UnicodeDecodeError:
        upload.seek(0)
        raise serializers.ValidationError('Text documents must use UTF-8 encoding.')
    except zipfile.BadZipFile:
        upload.seek(0)
        raise serializers.ValidationError('The Office document is damaged or invalid.')
    return upload


class SchoolSerializer(serializers.ModelSerializer):
    students_count = serializers.IntegerField(read_only=True)
    owner_counselor_name = serializers.SerializerMethodField()
    organization_account_id = serializers.SerializerMethodField()
    organization_account_username = serializers.SerializerMethodField()
    organization_credential_status = serializers.SerializerMethodField()
    organization_credential_expires_at = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = '__all__'

    def get_owner_counselor_name(self, obj) -> str | None:
        if not obj.owner_counselor:
            return None
        return obj.owner_counselor.get_full_name() or obj.owner_counselor.username

    def _organization_account(self, obj):
        if not hasattr(obj, '_organization_account'):
            obj._organization_account = obj.users.filter(role=User.Role.ORGANIZATION).first()
        return obj._organization_account

    def _organization_credential(self, obj):
        account = self._organization_account(obj)
        if not account:
            return None
        if not hasattr(obj, '_organization_credential'):
            obj._organization_credential = account.temporary_credentials.order_by('-issued_at', '-id').first()
        return obj._organization_credential

    def get_organization_account_id(self, obj) -> int | None:
        account = self._organization_account(obj)
        return account.id if account else None

    def get_organization_account_username(self, obj) -> str | None:
        account = self._organization_account(obj)
        return account.username if account else None

    def get_organization_credential_status(self, obj) -> str:
        credential = self._organization_credential(obj)
        if not credential:
            return 'none'
        return 'expired' if credential.is_expired else credential.status

    def get_organization_credential_expires_at(self, obj) -> datetime | None:
        credential = self._organization_credential(obj)
        return credential.expires_at if credential else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            data.pop('organization_credential_status', None)
            data.pop('organization_credential_expires_at', None)
        return data


class OrganizationAccountSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('This username is already in use.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email is already in use.')
        return value.lower()

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(
            **validated_data,
            password=None,
            role=User.Role.ORGANIZATION,
            school=self.context['school'],
        )
        user, _, _, _ = issue_temporary_credential(
            user=user,
            issued_by=self.context['request'].user,
            raw_password=password,
            request=self.context['request'],
        )
        return user


class StudentProfileSerializer(serializers.ModelSerializer):
    STUDENT_EDITABLE_FIELDS = {
        'target_major', 'target_countries', 'budget_usd', 'scholarship_needed',
        'parent_contact', 'notes',
    }
    user_detail = UserSerializer(source='user', read_only=True)
    counselor_name = serializers.SerializerMethodField()
    progress_percent = serializers.IntegerField(read_only=True)
    task_progress_percent = serializers.IntegerField(read_only=True)
    roadmap_progress_percent = serializers.IntegerField(read_only=True)
    journey_progress_percent = serializers.IntegerField(read_only=True)
    is_at_risk = serializers.BooleanField(read_only=True)
    task_status_counts = serializers.SerializerMethodField()
    roadmap_status_counts = serializers.SerializerMethodField()
    eligible_level = serializers.IntegerField(read_only=True)
    next_level_xp = serializers.IntegerField(read_only=True)
    xp_progress_percent = serializers.IntegerField(read_only=True)
    level_up_pending = serializers.BooleanField(read_only=True)

    class Meta:
        model = StudentProfile
        fields = '__all__'
        read_only_fields = ('xp_total', 'level')

    def get_counselor_name(self, obj) -> str | None:
        if not obj.assigned_counselor:
            return None
        return obj.assigned_counselor.get_full_name() or obj.assigned_counselor.username

    def get_task_status_counts(self, obj) -> dict[str, int]:
        counts = {choice: 0 for choice, _ in Task.Status.choices}
        for row in obj.tasks.values('status').annotate(total=Count('id')):
            counts[row['status']] = row['total']
        return counts

    def get_roadmap_status_counts(self, obj) -> dict[str, int]:
        counts = {choice: 0 for choice, _ in RoadmapMission.Status.choices}
        for row in obj.roadmap_missions.values('status').annotate(total=Count('id')):
            counts[row['status']] = row['total']
        return counts

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            data.pop('notes', None)
        return data

    def validate(self, attrs):
        request = self.context.get('request')
        user = attrs.get('user', getattr(self.instance, 'user', None))
        school = attrs.get('school', getattr(self.instance, 'school', None))
        assigned_counselor = attrs.get(
            'assigned_counselor', getattr(self.instance, 'assigned_counselor', None)
        )
        if user and user.role != user.Role.STUDENT:
            raise serializers.ValidationError({'user': 'Student profile requires a student user.'})
        if assigned_counselor:
            if assigned_counselor.role != User.Role.COUNSELOR:
                raise serializers.ValidationError({'assigned_counselor': 'Select a counselor account.'})
            if not school or assigned_counselor.school_id != school.id:
                raise serializers.ValidationError({
                    'assigned_counselor': 'The counselor and student must belong to the same school.'
                })
        if request and request.user.is_organization:
            if not request.user.school_id or not school or school.id != request.user.school_id:
                raise serializers.ValidationError({'school': 'Organization users can only manage their own school.'})
            if user and user.school_id != request.user.school_id:
                raise serializers.ValidationError({'user': 'This user does not belong to your school.'})
            if 'assigned_counselor' in attrs:
                current = getattr(self.instance, 'assigned_counselor', None)
                if attrs['assigned_counselor'] != current:
                    raise serializers.ValidationError({'assigned_counselor': 'Only a counselor can change this assignment.'})
            if 'notes' in attrs and attrs['notes'] != getattr(self.instance, 'notes', ''):
                raise serializers.ValidationError({'notes': 'Internal counselor notes are not available to school accounts.'})
        if request and request.user.role == request.user.Role.COUNSELOR and 'assigned_counselor' in attrs:
            current = getattr(self.instance, 'assigned_counselor', None)
            requested = attrs['assigned_counselor']
            if requested != current:
                raise serializers.ValidationError({
                    'assigned_counselor': 'Use the student assignment workflow to connect unassigned students.'
                })
        if request and request.user.role == request.user.Role.STUDENT:
            forbidden = set(attrs) - self.STUDENT_EDITABLE_FIELDS
            if forbidden:
                raise serializers.ValidationError({
                    field: 'This field requires counselor review.' for field in sorted(forbidden)
                })
        return attrs


class StudentRecordSerializerMixin:
    """Enforce student ownership before create/update writes reach the database."""

    def validate_student(self, student):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError('Authentication is required.')
        user = request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return student
        if user.role == User.Role.COUNSELOR:
            if (
                user.school_id
                and student.school_id == user.school_id
                and student.assigned_counselor_id == user.id
            ):
                return student
            raise serializers.ValidationError('You can only manage assigned students in your school.')
        if user.is_product_admin:
            return student
        if user.is_organization:
            if user.school_id and student.school_id == user.school_id:
                return student
            raise serializers.ValidationError('This student does not belong to your school.')
        if student.user_id != user.id:
            raise serializers.ValidationError('You can only modify your own records.')
        return student


class VerifiedStudentRecordMixin(StudentRecordSerializerMixin):
    def validate_verified(self, value):
        request = self.context.get('request')
        if request and not request.user.is_counselor_like:
            current = getattr(self.instance, 'verified', False)
            if value != current:
                raise serializers.ValidationError('Only a counselor can verify records.')
        return value


class GoogleDocsModelSerializer(serializers.ModelSerializer):
    """Expose one validated Google Docs link and its embeddable preview URL."""

    google_docs_preview_url = serializers.SerializerMethodField()

    def validate_google_docs_url(self, value):
        return validate_google_docs_url(value)

    def get_google_docs_preview_url(self, obj) -> str | None:
        return google_docs_preview_url(obj.google_docs_url)


class UniversitySerializer(serializers.ModelSerializer):
    class Meta:
        model = University
        fields = '__all__'


class CollegeResearchProfileSerializer(serializers.Serializer):
    gpa = serializers.DecimalField(max_digits=4, decimal_places=2, min_value=0, max_value=5, required=False)
    ielts_score = serializers.DecimalField(max_digits=3, decimal_places=1, min_value=0, max_value=9, required=False)
    sat_score = serializers.IntegerField(min_value=400, max_value=1600, required=False)
    target_major = serializers.CharField(max_length=160, required=False, allow_blank=False)
    target_countries = serializers.CharField(max_length=255, required=False, allow_blank=False)
    budget_usd = serializers.IntegerField(min_value=0, max_value=500000, required=False)
    scholarship_needed = serializers.BooleanField(required=False)

    def update_profile(self, profile):
        for field, value in self.validated_data.items():
            setattr(profile, field, value)
        if self.validated_data:
            profile.save(update_fields=[*self.validated_data.keys(), 'updated_at'])
        return profile


class CollegeAIQuestionSerializer(serializers.Serializer):
    question = serializers.CharField(min_length=3, max_length=400, trim_whitespace=True)


class PersonalityAssessmentSubmissionSerializer(serializers.Serializer):
    answers = serializers.DictField(
        child=serializers.IntegerField(min_value=1, max_value=5),
        allow_empty=False,
    )

    def validate_answers(self, value):
        from .ai_services import RIASEC_QUESTIONS

        expected = {item[0] for item in RIASEC_QUESTIONS}
        provided = set(value)
        if provided != expected:
            missing = sorted(expected - provided)
            extra = sorted(provided - expected)
            detail = []
            if missing:
                detail.append(f'Missing answers: {", ".join(missing)}.')
            if extra:
                detail.append(f'Unknown answers: {", ".join(extra)}.')
            raise serializers.ValidationError(' '.join(detail))
        return value


class ScholarshipSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source='university.name', read_only=True)

    class Meta:
        model = Scholarship
        fields = '__all__'


class OpportunityProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpportunityProgram
        fields = '__all__'


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

    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ('assigned_by', 'submitted_at', 'is_self_assigned')

    def validate_student(self, student):
        request = self.context.get('request')
        if request and request.user.role == request.user.Role.TEACHER:
            if request.user.school_id and student.school_id == request.user.school_id:
                return student
            raise serializers.ValidationError('Teachers can only assign work to students in their school.')
        return super().validate_student(student)

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

    def get_submission_preview_url(self, obj) -> str | None:
        return google_docs_preview_url(obj.submission_url)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            for field in ('student_response', 'submission_url', 'submission_file', 'submission_preview_url'):
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

    @staticmethod
    def _extension(upload):
        return Path(upload.name or '').suffix.lower()

    def validate_file(self, upload):
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
            if 'file' in attrs or 'google_docs_url' in attrs or not self.instance:
                attrs['status'] = Document.Status.UPLOADED
                status_value = Document.Status.UPLOADED
        if status_value != Document.Status.REQUIRED and not file_value and not docs_value:
            raise serializers.ValidationError({
                'file': 'Upload a file or add a Google Docs link before marking this document as uploaded.'
            })
        return attrs

    @staticmethod
    def _file_metadata(upload):
        content_type = mimetypes.guess_type(upload.name or '')[0] or 'application/octet-stream'
        return {
            'original_file_name': Path(upload.name or 'document').name[:255],
            'file_content_type': content_type[:120],
            'file_size': upload.size,
        }

    def create(self, validated_data):
        upload = validated_data.get('file')
        if upload:
            validated_data.update(self._file_metadata(upload))
            validated_data['uploaded_by'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        upload = validated_data.get('file')
        old_name = instance.file.name if upload and instance.file else ''
        old_storage = instance.file.storage if old_name else None
        if upload:
            validated_data.update(self._file_metadata(upload))
            validated_data['uploaded_by'] = self.context['request'].user
        updated = super().update(instance, validated_data)
        if old_name and old_name != updated.file.name:
            transaction.on_commit(lambda: old_storage.delete(old_name))
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

    def get_has_file(self, obj) -> bool:
        return bool(obj.file)

    def get_file_previewable(self, obj) -> bool:
        return Path(obj.original_file_name or obj.file.name if obj.file else '').suffix.lower() in {
            '.pdf', '.png', '.jpg', '.jpeg', '.webp', '.txt', '.csv',
        }

    def _file_url(self, obj, download=False):
        if not obj.file:
            return None
        request = self.context.get('request')
        path = reverse('documents-file', kwargs={'pk': obj.pk})
        if download:
            path += '?download=1'
        return request.build_absolute_uri(path) if request else path

    def get_file_preview_url(self, obj) -> str | None:
        return self._file_url(obj)

    def get_file_download_url(self, obj) -> str | None:
        return self._file_url(obj, download=True)


class PrivateEvidenceSerializerMixin:
    evidence_resource = ''

    def validate_proof_file(self, upload):
        if upload is None:
            return None
        return validate_private_upload(upload)

    def get_has_proof_file(self, obj) -> bool:
        return bool(obj.proof_file)

    def get_proof_file_previewable(self, obj) -> bool:
        return Path(obj.proof_file_name or obj.proof_file.name if obj.proof_file else '').suffix.lower() in {
            '.pdf', '.png', '.jpg', '.jpeg', '.webp', '.txt', '.csv',
        }

    def _proof_file_url(self, obj, download=False):
        if not obj.proof_file:
            return None
        request = self.context.get('request')
        path = reverse(f'{self.evidence_resource}-proof-file', kwargs={'pk': obj.pk})
        if download:
            path += '?download=1'
        return request.build_absolute_uri(path) if request else path

    def get_proof_file_preview_url(self, obj) -> str | None:
        return self._proof_file_url(obj) if self.get_proof_file_previewable(obj) else None

    def get_proof_file_download_url(self, obj) -> str | None:
        return self._proof_file_url(obj, download=True)

    def get_proof_resource(self, obj) -> str:
        return self.evidence_resource

    @staticmethod
    def _proof_metadata(upload):
        return {
            'proof_file_name': Path(upload.name or 'evidence').name[:255],
            'proof_file_content_type': (mimetypes.guess_type(upload.name or '')[0] or 'application/octet-stream')[:120],
            'proof_file_size': upload.size,
        }

    def create(self, validated_data):
        upload = validated_data.get('proof_file')
        if upload:
            validated_data.update(self._proof_metadata(upload))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        proof_supplied = 'proof_file' in validated_data
        upload = validated_data.get('proof_file')
        old_name = instance.proof_file.name if proof_supplied and instance.proof_file else ''
        old_storage = instance.proof_file.storage if old_name else None
        if upload:
            validated_data.update(self._proof_metadata(upload))
        elif proof_supplied:
            validated_data.update({
                'proof_file_name': '',
                'proof_file_content_type': '',
                'proof_file_size': 0,
            })
        updated = super().update(instance, validated_data)
        updated_name = updated.proof_file.name if updated.proof_file else ''
        if old_name and old_name != updated_name:
            transaction.on_commit(lambda: old_storage.delete(old_name))
        return updated


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


class ActivitySerializer(VerifiedStudentRecordMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = '__all__'

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

    class Meta:
        model = RecommendationLetter
        fields = '__all__'

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            for field in ('recommender_email', 'file', 'google_docs_url', 'google_docs_preview_url', 'notes'):
                data.pop(field, None)
        return data

    def validate_status(self, value):
        request = self.context.get('request')
        if request and not request.user.is_counselor_like and value == RecommendationLetter.Status.APPROVED:
            raise serializers.ValidationError('Only a counselor can approve recommendation letters.')
        return value


class EssayRevisionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = EssayRevision
        fields = '__all__'


class EssayAIReviewSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True)

    class Meta:
        model = EssayAIReview
        fields = (
            'id', 'essay', 'essay_version', 'model', 'mode', 'result',
            'requested_by_name', 'created_at',
        )
        read_only_fields = fields


class EssaySerializer(StudentRecordSerializerMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()
    university_name = serializers.SerializerMethodField()
    revisions = EssayRevisionSerializer(many=True, read_only=True)

    class Meta:
        model = Essay
        fields = '__all__'

    def validate_status(self, value):
        request = self.context.get('request')
        if request and not request.user.is_counselor_like and value == Essay.Status.APPROVED:
            raise serializers.ValidationError('Only a counselor can approve essays.')
        return value

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

    def get_university_name(self, obj) -> str | None:
        return obj.application.university.name if obj.application else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            for field in ('prompt', 'content', 'counselor_comment', 'google_docs_url', 'google_docs_preview_url', 'revisions'):
                data.pop(field, None)
        return data


class MeetingNoteSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    counselor_name = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = MeetingNote
        fields = '__all__'

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


class SchoolVisibilityUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'full_name', 'phone', 'is_active')

    def get_full_name(self, obj) -> str:
        return obj.get_full_name() or obj.username


class SchoolVisibilityStudentSerializer(serializers.ModelSerializer):
    user = SchoolVisibilityUserSerializer(read_only=True)
    counselor_name = serializers.SerializerMethodField()
    progress_percent = serializers.IntegerField(read_only=True)
    task_progress_percent = serializers.IntegerField(read_only=True)
    roadmap_progress_percent = serializers.IntegerField(read_only=True)
    journey_progress_percent = serializers.IntegerField(read_only=True)
    eligible_level = serializers.IntegerField(read_only=True)
    xp_progress_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = StudentProfile
        fields = (
            'id', 'user', 'grade', 'school', 'school_name', 'gpa', 'ielts_score', 'sat_score',
            'target_major', 'target_countries', 'budget_usd', 'scholarship_needed', 'parent_contact',
            'xp_total', 'level', 'eligible_level', 'xp_progress_percent', 'progress_percent',
            'task_progress_percent', 'roadmap_progress_percent', 'journey_progress_percent',
            'counselor_name', 'created_at', 'updated_at',
        )

    def get_counselor_name(self, obj) -> str | None:
        return obj.assigned_counselor.get_full_name() or obj.assigned_counselor.username if obj.assigned_counselor else None


class SchoolVisibilityTaskSerializer(serializers.ModelSerializer):
    assigned_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = (
            'id', 'title', 'description', 'due_date', 'priority', 'status', 'is_self_assigned',
            'assigned_by_name', 'submitted_at', 'created_at', 'updated_at',
        )

    def get_assigned_by_name(self, obj) -> str | None:
        return obj.assigned_by.get_full_name() or obj.assigned_by.username if obj.assigned_by else None


class SchoolVisibilityRoadmapSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoadmapMission
        fields = ('id', 'title', 'category', 'description', 'level', 'sequence', 'due_date', 'status', 'created_at', 'updated_at')


class SchoolVisibilityApplicationSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source='university.name', read_only=True)
    university_country = serializers.CharField(source='university.country', read_only=True)

    class Meta:
        model = Application
        fields = (
            'id', 'university', 'university_name', 'university_country', 'program', 'tier', 'status',
            'deadline', 'scholarship_deadline', 'created_at', 'updated_at',
        )


class SchoolVisibilityDocumentSerializer(serializers.ModelSerializer):
    has_file = serializers.SerializerMethodField()
    file_name = serializers.CharField(source='original_file_name', read_only=True)
    file_preview_url = serializers.SerializerMethodField()
    file_download_url = serializers.SerializerMethodField()
    google_docs_preview_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            'id', 'title', 'document_type', 'status', 'has_file', 'file_name', 'file_content_type',
            'file_size', 'file_preview_url', 'file_download_url', 'google_docs_preview_url',
            'created_at', 'updated_at',
        )

    def get_has_file(self, obj) -> bool:
        return bool(obj.file)

    def get_file_preview_url(self, obj) -> str | None:
        request = self.context.get('request')
        return request.build_absolute_uri(reverse('documents-file', args=[obj.pk])) if request and obj.file else None

    def get_file_download_url(self, obj) -> str | None:
        request = self.context.get('request')
        return request.build_absolute_uri(f"{reverse('documents-file', args=[obj.pk])}?download=1") if request and obj.file else None

    def get_google_docs_preview_url(self, obj) -> str | None:
        return google_docs_preview_url(obj.google_docs_url)


class SchoolVisibilityEssaySerializer(serializers.ModelSerializer):
    university_name = serializers.SerializerMethodField()

    class Meta:
        model = Essay
        fields = ('id', 'title', 'status', 'version', 'application', 'university_name', 'created_at', 'updated_at')

    def get_university_name(self, obj) -> str | None:
        return obj.application.university.name if obj.application else None


class SchoolVisibilityRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecommendationLetter
        fields = (
            'id', 'recommender_name', 'recommender_title', 'relationship', 'status', 'deadline',
            'created_at', 'updated_at',
        )


class SchoolVisibilityBookingSerializer(serializers.ModelSerializer):
    participant_name = serializers.SerializerMethodField()
    participant_role = serializers.CharField(source='participant.role', read_only=True)

    class Meta:
        model = Booking
        fields = (
            'id', 'topic', 'starts_at', 'duration_minutes', 'status', 'participant_name',
            'participant_role', 'created_at', 'updated_at',
        )

    def get_participant_name(self, obj) -> str | None:
        return obj.participant.get_full_name() or obj.participant.username if obj.participant else None


class SchoolVisibilityProgramServiceSerializer(serializers.ModelSerializer):
    mentor_name = serializers.SerializerMethodField()

    class Meta:
        model = ProgramService
        fields = (
            'id', 'name', 'category', 'mentor_name', 'total_hours', 'used_hours', 'unlimited',
            'status', 'created_at', 'updated_at',
        )

    def get_mentor_name(self, obj) -> str | None:
        return obj.mentor.get_full_name() or obj.mentor.username if obj.mentor else None


class SchoolVisibilityAchievementSerializer(PrivateEvidenceSerializerMixin, serializers.ModelSerializer):
    evidence_resource = 'achievements'
    has_proof_file = serializers.SerializerMethodField()
    proof_file_previewable = serializers.SerializerMethodField()
    proof_file_preview_url = serializers.SerializerMethodField()
    proof_file_download_url = serializers.SerializerMethodField()
    proof_resource = serializers.SerializerMethodField()

    class Meta:
        model = Achievement
        fields = (
            'id', 'title', 'category', 'description', 'impact', 'date', 'verified',
            'has_proof_file', 'proof_file_name', 'proof_file_content_type', 'proof_file_size',
            'proof_file_previewable', 'proof_file_preview_url', 'proof_file_download_url',
            'proof_resource', 'created_at', 'updated_at',
        )


class SchoolVisibilityResearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Research
        fields = ('id', 'title', 'field', 'role', 'summary', 'outcome', 'start_date', 'end_date', 'link', 'verified', 'created_at', 'updated_at')


class SchoolVisibilityProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ('id', 'title', 'role', 'description', 'impact', 'technologies', 'link', 'date', 'verified', 'created_at', 'updated_at')


class SchoolVisibilityInternshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Internship
        fields = ('id', 'organization', 'position', 'description', 'start_date', 'end_date', 'is_current', 'supervisor', 'verified', 'created_at', 'updated_at')


class SchoolVisibilityActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = ('id', 'name', 'activity_type', 'role', 'description', 'impact', 'hours_per_week', 'weeks_per_year', 'start_date', 'end_date', 'verified', 'created_at', 'updated_at')


class SchoolVisibilityHonorSerializer(PrivateEvidenceSerializerMixin, serializers.ModelSerializer):
    evidence_resource = 'honors'
    has_proof_file = serializers.SerializerMethodField()
    proof_file_previewable = serializers.SerializerMethodField()
    proof_file_preview_url = serializers.SerializerMethodField()
    proof_file_download_url = serializers.SerializerMethodField()
    proof_resource = serializers.SerializerMethodField()

    class Meta:
        model = Honor
        fields = (
            'id', 'title', 'issuer', 'level', 'award_date', 'description', 'verified',
            'has_proof_file', 'proof_file_name', 'proof_file_content_type', 'proof_file_size',
            'proof_file_previewable', 'proof_file_preview_url', 'proof_file_download_url',
            'proof_resource', 'created_at', 'updated_at',
        )


class NotificationSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = '__all__'

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


class RoadmapMissionSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    assigned_by_name = serializers.SerializerMethodField()
    prerequisite_title = serializers.CharField(source='prerequisite.title', read_only=True)
    prerequisite_sequence = serializers.IntegerField(source='prerequisite.sequence', read_only=True)
    xp_reward = serializers.SerializerMethodField()
    approval_status = serializers.SerializerMethodField()

    class Meta:
        model = RoadmapMission
        fields = '__all__'
        read_only_fields = ('assigned_by',)

    def validate_student(self, student):
        request = self.context.get('request')
        if request and request.user.role == request.user.Role.TEACHER:
            if request.user.school_id and student.school_id == request.user.school_id:
                return student
            raise serializers.ValidationError('Teachers can only assign work to students in their school.')
        return super().validate_student(student)

    def validate_status(self, value):
        request = self.context.get('request')
        current = getattr(self.instance, 'status', None)
        if request and request.user.is_task_manager and value == RoadmapMission.Status.COMPLETED and current != RoadmapMission.Status.COMPLETED:
            raise serializers.ValidationError('Use the approve action so XP is recorded.')
        if request and not request.user.is_task_manager and value != RoadmapMission.Status.SUBMITTED:
            raise serializers.ValidationError(
                'Students cannot choose a mission status. Use Submit mission when the work is ready.'
            )
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        if 'progress_percent' in self.initial_data:
            raise serializers.ValidationError({
                'progress_percent': 'Manual mission progress has been removed. Progress is calculated from approved missions.'
            })
        student = attrs.get('student', getattr(self.instance, 'student', None))
        prerequisite = attrs.get('prerequisite', getattr(self.instance, 'prerequisite', None))
        if prerequisite and student and prerequisite.student_id != student.id:
            raise serializers.ValidationError({
                'prerequisite': 'The prerequisite must belong to the same student.'
            })
        if prerequisite and self.instance and prerequisite.id == self.instance.id:
            raise serializers.ValidationError({
                'prerequisite': 'A mission cannot be its own prerequisite.'
            })
        if request and request.user.role == request.user.Role.STUDENT and self.instance:
            forbidden = set(attrs) - {'status', 'reflection'}
            if forbidden:
                raise serializers.ValidationError({
                    field: 'Only a teacher or counselor can change this field.' for field in sorted(forbidden)
                })
            if self.instance.status == RoadmapMission.Status.SUBMITTED:
                raise serializers.ValidationError({
                    'status': 'This mission is already submitted and awaiting staff approval.'
                })
            if self.instance.status == RoadmapMission.Status.COMPLETED:
                raise serializers.ValidationError({
                    'status': 'An approved mission cannot be changed by a student.'
                })
            if attrs.get('status') != RoadmapMission.Status.SUBMITTED:
                raise serializers.ValidationError({
                    'status': 'Use Submit mission when the work is ready.'
                })
            reflection = attrs.get('reflection', self.instance.reflection)
            if not reflection or not reflection.strip():
                raise serializers.ValidationError({
                    'reflection': 'Add a reflection before submitting the mission.'
                })
            if prerequisite and prerequisite.status != RoadmapMission.Status.COMPLETED:
                raise serializers.ValidationError({
                    'status': 'Complete the previous Level 1 mission before submitting this one.'
                })
        return attrs

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

    def get_assigned_by_name(self, obj) -> str | None:
        if not obj.assigned_by:
            return None
        return obj.assigned_by.get_full_name() or obj.assigned_by.username

    def get_xp_reward(self, obj) -> int:
        return 75

    def get_approval_status(self, obj) -> str:
        if obj.status == RoadmapMission.Status.SUBMITTED:
            return 'awaiting_approval'
        if obj.status == RoadmapMission.Status.COMPLETED:
            return 'approved'
        return 'not_submitted'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            data.pop('reflection', None)
        return data


class CounselorRoadmapTemplateMissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CounselorRoadmapTemplateMission
        fields = ('id', 'title', 'description', 'sequence', 'due_days', 'is_required')
        read_only_fields = ('id',)


class CounselorRoadmapTemplateSerializer(serializers.ModelSerializer):
    missions = CounselorRoadmapTemplateMissionSerializer(many=True)

    class Meta:
        model = CounselorRoadmapTemplate
        fields = ('id', 'name', 'description', 'kind', 'is_active', 'missions', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_missions(self, missions):
        if not missions:
            raise serializers.ValidationError('Add at least one mission.')
        sequences = [mission['sequence'] for mission in missions]
        if len(sequences) != len(set(sequences)):
            raise serializers.ValidationError('Mission sequence numbers must be unique.')
        return missions

    @transaction.atomic
    def create(self, validated_data):
        missions = validated_data.pop('missions')
        template = CounselorRoadmapTemplate.objects.create(
            **validated_data,
            created_by=self.context['request'].user,
        )
        CounselorRoadmapTemplateMission.objects.bulk_create([
            CounselorRoadmapTemplateMission(template=template, **mission) for mission in missions
        ])
        return template

    @transaction.atomic
    def update(self, instance, validated_data):
        missions = validated_data.pop('missions', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if missions is not None:
            instance.missions.all().delete()
            CounselorRoadmapTemplateMission.objects.bulk_create([
                CounselorRoadmapTemplateMission(template=instance, **mission) for mission in missions
            ])
        return instance


class CounselorRoadmapMissionSerializer(serializers.ModelSerializer):
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CounselorRoadmapMission
        fields = '__all__'
        read_only_fields = (
            'roadmap', 'source_template_mission', 'title', 'description', 'sequence', 'due_date',
            'is_required', 'status', 'admin_feedback', 'submitted_at', 'approved_at', 'approved_by',
        )

    def get_approved_by_name(self, obj) -> str | None:
        return obj.approved_by.get_full_name() or obj.approved_by.username if obj.approved_by else None


class CounselorRoadmapSerializer(serializers.ModelSerializer):
    title = serializers.CharField(required=False, allow_blank=True)
    missions = CounselorRoadmapMissionSerializer(many=True, read_only=True)
    counselor_name = serializers.SerializerMethodField()
    school_name = serializers.CharField(source='school.name', read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = CounselorRoadmap
        fields = '__all__'
        read_only_fields = ('school', 'kind', 'status', 'assigned_by', 'completed_at')

    def get_counselor_name(self, obj) -> str:
        return obj.counselor.get_full_name() or obj.counselor.username

    def validate(self, attrs):
        attrs = super().validate(attrs)
        counselor = attrs.get('counselor')
        template = attrs.get('template')
        if self.instance and ({'counselor', 'template'} & set(attrs)):
            raise serializers.ValidationError('An assigned roadmap cannot change counselor or template. Cancel and reassign it.')
        if counselor and counselor.role != User.Role.COUNSELOR:
            raise serializers.ValidationError({'counselor': 'Select a counselor account.'})
        if counselor and not counselor.is_active:
            raise serializers.ValidationError({'counselor': 'Select an active counselor.'})
        if template and not template.is_active:
            raise serializers.ValidationError({'template': 'Select an active template.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        counselor = validated_data['counselor']
        template = validated_data['template']
        validated_data['title'] = validated_data.get('title') or template.name
        roadmap = CounselorRoadmap.objects.create(
            **validated_data,
            school=counselor.school,
            kind=template.kind,
            assigned_by=self.context['request'].user,
        )
        today = timezone.localdate()
        CounselorRoadmapMission.objects.bulk_create([
            CounselorRoadmapMission(
                roadmap=roadmap,
                source_template_mission=mission,
                title=mission.title,
                description=mission.description,
                sequence=mission.sequence,
                due_date=today + timedelta(days=mission.due_days),
                is_required=mission.is_required,
            )
            for mission in template.missions.all()
        ])
        return roadmap


class XPTransactionSerializer(serializers.ModelSerializer):
    awarded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = XPTransaction
        fields = '__all__'

    def get_awarded_by_name(self, obj) -> str | None:
        if not obj.awarded_by:
            return None
        return obj.awarded_by.get_full_name() or obj.awarded_by.username


class LevelApprovalSerializer(serializers.ModelSerializer):
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = LevelApproval
        fields = '__all__'

    def get_approved_by_name(self, obj) -> str | None:
        if not obj.approved_by:
            return None
        return obj.approved_by.get_full_name() or obj.approved_by.username


class CommunityPostSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.user.get_full_name', read_only=True)
    author_initials = serializers.SerializerMethodField()
    likes_count = serializers.IntegerField(source='liked_by.count', read_only=True)
    liked_by_me = serializers.SerializerMethodField()

    class Meta:
        model = CommunityPost
        fields = '__all__'
        read_only_fields = ('author', 'liked_by')

    def get_author_initials(self, obj) -> str:
        name = obj.author.user.get_full_name() or obj.author.user.username
        return ''.join(part[0] for part in name.split()[:2]).upper()

    def get_liked_by_me(self, obj) -> bool:
        request = self.context.get('request')
        if not request or not hasattr(request.user, 'student_profile'):
            return False
        return obj.liked_by.filter(id=request.user.student_profile.id).exists()


class BookingSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    participant = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            is_active=True,
            role__in=[User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION],
        ),
        required=True,
        allow_null=False,
    )
    participant_name = serializers.SerializerMethodField()
    participant_role = serializers.CharField(source='participant.role', read_only=True)
    participant_detail = UserSerializer(source='participant', read_only=True)
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ('student', 'status')

    def get_participant_name(self, obj) -> str | None:
        if not obj.participant:
            return None
        return obj.participant.get_full_name() or obj.participant.username

    def get_student_name(self, obj) -> str:
        return obj.student.user.get_full_name() or obj.student.user.username

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            data.pop('notes', None)
        return data

    def validate_participant(self, participant):
        request = self.context.get('request')
        if not request or request.user.role != User.Role.STUDENT or not hasattr(request.user, 'student_profile'):
            raise serializers.ValidationError('Only students can request meetings.')
        profile = request.user.student_profile
        assigned_counselor = participant.id == profile.assigned_counselor_id
        same_school_staff = bool(
            profile.school_id
            and participant.school_id == profile.school_id
            and participant.role in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}
        )
        if not (assigned_counselor or same_school_staff):
            raise serializers.ValidationError(
                'Choose your assigned counselor, teacher, or a representative from your school.'
            )
        return participant

    def validate_starts_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError('Choose a future meeting date and time.')
        return value

    def validate_duration_minutes(self, value):
        if value not in {30, 45, 60}:
            raise serializers.ValidationError('Choose a 30, 45, or 60 minute meeting.')
        return value


class StudentMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    recipient_name = serializers.CharField(source='recipient.get_full_name', read_only=True)

    class Meta:
        model = StudentMessage
        fields = '__all__'
        read_only_fields = ('student', 'sender', 'recipient', 'is_read')


class ChannelMembershipSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source='user', read_only=True)

    class Meta:
        model = ChannelMembership
        fields = ('id', 'channel', 'user', 'user_detail', 'role', 'joined_at', 'last_read_at', 'notifications_enabled', 'muted_until')
        read_only_fields = ('channel', 'joined_at', 'last_read_at', 'muted_until')


class MessageChannelSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    school_name = serializers.CharField(source='school.name', read_only=True)
    members_count = serializers.IntegerField(source='memberships.count', read_only=True)
    is_member = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = MessageChannel
        fields = (
            'id', 'kind', 'name', 'display_name', 'description', 'school', 'school_name',
            'created_by', 'is_public', 'is_archived', 'last_message_at', 'members_count',
            'is_member', 'my_role', 'unread_count', 'last_message', 'created_at', 'updated_at',
        )
        read_only_fields = ('created_by', 'last_message_at')

    def _membership(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        cached = getattr(obj, '_current_membership', None)
        if cached is not None:
            return cached
        prefetched = getattr(obj, '_prefetched_objects_cache', {}).get('memberships')
        if prefetched is not None:
            return next((membership for membership in prefetched if membership.user_id == request.user.id), None)
        return obj.memberships.filter(user=request.user).first()

    def get_display_name(self, obj) -> str:
        request = self.context.get('request')
        if obj.kind == MessageChannel.Kind.DIRECT and request and request.user.is_authenticated:
            prefetched = getattr(obj, '_prefetched_objects_cache', {}).get('memberships')
            other = next((membership for membership in prefetched or [] if membership.user_id != request.user.id), None)
            if prefetched is None:
                other = obj.memberships.exclude(user=request.user).select_related('user').first()
            if other:
                return other.user.get_full_name() or other.user.username
        return obj.name or obj.get_kind_display()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance:
            immutable = {'kind', 'school', 'is_public'} & set(attrs)
            if immutable:
                raise serializers.ValidationError({
                    field: 'This channel setting cannot be changed after creation.'
                    for field in sorted(immutable)
                })
        return attrs

    def get_is_member(self, obj) -> bool:
        return self._membership(obj) is not None

    def get_my_role(self, obj) -> str | None:
        membership = self._membership(obj)
        return membership.role if membership else None

    def get_unread_count(self, obj) -> int:
        request = self.context.get('request')
        membership = self._membership(obj)
        if not request or not membership:
            return 0
        messages = obj.messages.filter(deleted_at__isnull=True).exclude(sender=request.user)
        if membership.last_read_at:
            messages = messages.filter(created_at__gt=membership.last_read_at)
        return messages.count()

    def get_last_message(self, obj) -> dict | None:
        request = self.context.get('request')
        message = obj.messages.select_related('sender').order_by('-created_at', '-id').first()
        if not message:
            return None
        can_reveal = bool(
            request
            and request.user.is_authenticated
            and message.sender_id == request.user.id
        )
        anonymous = message.is_anonymous and not can_reveal
        sender_name = 'Deleted user'
        if message.sender:
            sender_name = message.sender.get_full_name() or message.sender.username
        return {
            'body': 'Message deleted' if message.deleted_at else message.body[:160],
            'sender_name': 'Anonymous' if anonymous else sender_name,
            'created_at': message.created_at,
        }


class ChannelMessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.SerializerMethodField()
    sender_name = serializers.SerializerMethodField()
    parent_preview = serializers.SerializerMethodField()
    replies_count = serializers.IntegerField(source='replies.count', read_only=True)
    is_reported_by_me = serializers.SerializerMethodField()

    class Meta:
        model = ChannelMessage
        fields = (
            'id', 'channel', 'sender_id', 'sender_name', 'parent', 'parent_preview',
            'replies_count', 'body', 'is_anonymous', 'is_edited', 'is_accepted_answer',
            'is_reported_by_me', 'deleted_at', 'created_at', 'updated_at',
        )
        read_only_fields = ('sender_id', 'sender_name', 'is_edited', 'is_accepted_answer', 'deleted_at')

    def _can_reveal_sender(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.sender_id == request.user.id

    def get_sender_id(self, obj) -> int | None:
        if obj.is_anonymous and not self._can_reveal_sender(obj):
            return None
        return obj.sender_id

    def get_sender_name(self, obj) -> str:
        if obj.is_anonymous and not self._can_reveal_sender(obj):
            return 'Anonymous'
        if not obj.sender:
            return 'Deleted user'
        return obj.sender.get_full_name() or obj.sender.username

    def get_parent_preview(self, obj) -> dict | None:
        if not obj.parent:
            return None
        return {'id': obj.parent_id, 'body': obj.parent.body[:120]}

    def get_is_reported_by_me(self, obj) -> bool:
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.reports.filter(reporter=request.user).exists()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        if self.instance:
            forbidden = set(attrs) - {'body', 'is_anonymous'}
            if forbidden:
                raise serializers.ValidationError({
                    field: 'This field cannot be changed after posting.' for field in sorted(forbidden)
                })
        channel = attrs.get('channel', getattr(self.instance, 'channel', None))
        if request and channel:
            if channel.is_archived:
                raise serializers.ValidationError('This channel is archived.')
            membership = channel.memberships.filter(user=request.user).first()
            if not membership:
                raise serializers.ValidationError('Join the channel before posting.')
            if not self.instance and membership.muted_until and membership.muted_until > timezone.now():
                raise serializers.ValidationError({
                    'channel': f'You are muted in this channel until {membership.muted_until.isoformat()}.'
                })
            is_anonymous = attrs.get('is_anonymous', getattr(self.instance, 'is_anonymous', False))
            if is_anonymous and channel.kind not in {
                MessageChannel.Kind.COMMUNITY,
                MessageChannel.Kind.DISCUSSION,
            }:
                raise serializers.ValidationError({'is_anonymous': 'Anonymous mode is only available in Community and Discussions.'})
            parent = attrs.get('parent')
            if parent and parent.channel_id != channel.id:
                raise serializers.ValidationError({'parent': 'Reply must belong to the same channel.'})
        return attrs


class MessageReportSerializer(serializers.ModelSerializer):
    channel_id = serializers.IntegerField(source='message.channel_id', read_only=True)
    channel_name = serializers.SerializerMethodField()
    message_body = serializers.SerializerMethodField()
    message_is_anonymous = serializers.BooleanField(source='message.is_anonymous', read_only=True)
    message_deleted_at = serializers.DateTimeField(source='message.deleted_at', read_only=True)
    sender_id = serializers.IntegerField(source='message.sender_id', read_only=True)
    sender_name = serializers.SerializerMethodField()
    reporter_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = MessageReport
        fields = (
            'id', 'message', 'channel_id', 'channel_name', 'message_body',
            'message_is_anonymous', 'message_deleted_at', 'sender_id', 'sender_name',
            'reporter', 'reporter_name', 'reason', 'details', 'status', 'action',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'moderator_note',
            'created_at', 'updated_at',
        )
        read_only_fields = fields

    def get_channel_name(self, obj) -> str:
        return obj.message.channel.name or obj.message.channel.get_kind_display()

    def get_message_body(self, obj) -> str:
        return 'Message deleted' if obj.message.deleted_at else obj.message.body

    def get_sender_name(self, obj) -> str:
        sender = obj.message.sender
        if not sender:
            return 'Deleted user'
        return sender.get_full_name() or sender.username

    def get_reporter_name(self, obj) -> str:
        return obj.reporter.get_full_name() or obj.reporter.username

    def get_reviewed_by_name(self, obj) -> str | None:
        if not obj.reviewed_by:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.username


class ProgramServiceSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    mentor_name = serializers.SerializerMethodField()
    mentor_role = serializers.CharField(source='mentor.role', read_only=True)
    student_name = serializers.SerializerMethodField()
    remaining_hours = serializers.SerializerMethodField()

    class Meta:
        model = ProgramService
        fields = '__all__'

    def get_mentor_name(self, obj) -> str | None:
        if not obj.mentor:
            return None
        return obj.mentor.get_full_name() or obj.mentor.username

    def get_student_name(self, obj) -> str:
        return obj.student.user.get_full_name() or obj.student.user.username

    def get_remaining_hours(self, obj) -> Decimal | None:
        if obj.unlimited or obj.total_hours is None:
            return None
        return max(obj.total_hours - obj.used_hours, 0)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        student = attrs.get('student', getattr(self.instance, 'student', None))
        mentor = attrs.get('mentor', getattr(self.instance, 'mentor', None))
        unlimited = attrs.get('unlimited', getattr(self.instance, 'unlimited', False))
        total_hours = attrs.get('total_hours', getattr(self.instance, 'total_hours', None))
        used_hours = attrs.get('used_hours', getattr(self.instance, 'used_hours', 0))
        if not unlimited and (total_hours is None or total_hours <= 0):
            raise serializers.ValidationError({'total_hours': 'Set allocated hours or mark the service unlimited.'})
        if not unlimited and used_hours > total_hours:
            raise serializers.ValidationError({'used_hours': 'Used hours cannot exceed allocated hours.'})
        if mentor:
            if mentor.role not in {User.Role.COUNSELOR, User.Role.TEACHER}:
                raise serializers.ValidationError({'mentor': 'Mentor must be a counselor or teacher.'})
            if student and (not mentor.school_id or mentor.school_id != student.school_id):
                raise serializers.ValidationError({'mentor': 'Mentor and student must belong to the same school.'})
        return attrs


class ScreenTimeDailySerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = ScreenTimeDaily
        fields = ('id', 'user', 'user_name', 'date', 'page', 'active_seconds', 'sessions', 'last_seen_at')
        read_only_fields = fields

    def get_user_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.username


class ParentStudentLinkSerializer(serializers.ModelSerializer):
    parent_name = serializers.SerializerMethodField()
    parent_email = serializers.EmailField(source='parent.email', read_only=True)
    student_name = serializers.SerializerMethodField()
    relationship_display = serializers.CharField(source='get_relationship_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ParentStudentLink
        fields = (
            'id', 'parent', 'parent_name', 'parent_email', 'student', 'student_name',
            'relationship', 'relationship_display', 'status', 'status_display',
            'can_view_applications', 'can_view_documents', 'can_view_meetings',
            'invited_by', 'invited_at', 'consented_at', 'revoked_at', 'created_at', 'updated_at',
        )
        read_only_fields = fields

    def get_parent_name(self, obj) -> str:
        return obj.parent.get_full_name() or obj.parent.username

    def get_student_name(self, obj) -> str:
        return obj.student.user.get_full_name() or obj.student.user.username


class ParentInviteSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=StudentProfile.objects.select_related('user', 'school'))
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False, validators=[validate_password])
    relationship = serializers.ChoiceField(choices=ParentStudentLink.Relationship.choices)
    can_view_applications = serializers.BooleanField(default=True)
    can_view_documents = serializers.BooleanField(default=True)
    can_view_meetings = serializers.BooleanField(default=True)


class ResourceLibraryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceLibraryItem
        fields = '__all__'


class StoreItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreItem
        fields = '__all__'


class SupportTicketSerializer(serializers.ModelSerializer):
    requester_name = serializers.SerializerMethodField()
    requester_role = serializers.CharField(source='requester.role', read_only=True)
    responded_by_name = serializers.SerializerMethodField()
    has_unread_response = serializers.BooleanField(read_only=True)

    class Meta:
        model = SupportTicket
        fields = (
            'id', 'requester', 'requester_name', 'requester_role', 'category',
            'subject', 'message', 'status', 'admin_response', 'responded_by',
            'responded_by_name', 'responded_at', 'requester_viewed_at',
            'has_unread_response', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'requester', 'responded_by', 'responded_by_name', 'responded_at',
            'requester_viewed_at', 'has_unread_response', 'created_at', 'updated_at',
        )

    def get_requester_name(self, obj) -> str:
        return obj.requester.get_full_name() or obj.requester.username

    def get_responded_by_name(self, obj) -> str | None:
        if not obj.responded_by:
            return None
        return obj.responded_by.get_full_name() or obj.responded_by.username

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        is_product_admin = bool(
            user
            and user.is_authenticated
            and (user.is_superuser or user.role == User.Role.ADMIN)
        )
        if not is_product_admin and {'status', 'admin_response'}.intersection(self.initial_data):
            raise serializers.ValidationError('Only an admin can set ticket status or support response.')
        return attrs
