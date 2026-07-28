from rest_framework import serializers
from urllib.parse import urlparse
from django.contrib.auth.password_validation import validate_password
from django.db.models import Count
from django.utils import timezone
from apps.users.models import User
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
    EssayRevision,
    Honor,
    Internship,
    LevelApproval,
    MeetingNote,
    MessageChannel,
    MessageReport,
    Notification,
    OpportunityProgram,
    ProgramService,
    Project,
    RecommendationLetter,
    Research,
    ResourceLibraryItem,
    RoadmapMission,
    School,
    Scholarship,
    StoreItem,
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


class SchoolSerializer(serializers.ModelSerializer):
    students_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = School
        fields = '__all__'


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
        return User.objects.create_user(
            **validated_data,
            role=User.Role.ORGANIZATION,
            school=self.context['school'],
        )


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

    def get_task_status_counts(self, obj):
        counts = {choice: 0 for choice, _ in Task.Status.choices}
        for row in obj.tasks.values('status').annotate(total=Count('id')):
            counts[row['status']] = row['total']
        return counts

    def get_roadmap_status_counts(self, obj):
        counts = {choice: 0 for choice, _ in RoadmapMission.Status.choices}
        for row in obj.roadmap_missions.values('status').annotate(total=Count('id')):
            counts[row['status']] = row['total']
        return counts

    def validate(self, attrs):
        request = self.context.get('request')
        user = attrs.get('user', getattr(self.instance, 'user', None))
        school = attrs.get('school', getattr(self.instance, 'school', None))
        if user and user.role != user.Role.STUDENT:
            raise serializers.ValidationError({'user': 'Student profile requires a student user.'})
        if request and request.user.is_organization:
            if not request.user.school_id or not school or school.id != request.user.school_id:
                raise serializers.ValidationError({'school': 'Organization users can only manage their own school.'})
            if user and user.school_id != request.user.school_id:
                raise serializers.ValidationError({'user': 'This user does not belong to your school.'})
            if 'assigned_counselor' in attrs:
                current = getattr(self.instance, 'assigned_counselor', None)
                if attrs['assigned_counselor'] != current:
                    raise serializers.ValidationError({'assigned_counselor': 'Only a counselor can change this assignment.'})
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
            if student.assigned_counselor_id == user.id:
                return student
            raise serializers.ValidationError('You can only manage students assigned to you.')
        if user.is_staff:
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

    def get_google_docs_preview_url(self, obj):
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


class ApplicationSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    university_detail = UniversitySerializer(source='university', read_only=True)
    student_name = serializers.SerializerMethodField()
    status_history = ApplicationStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Application
        fields = '__all__'

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

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
    student_name = serializers.SerializerMethodField()
    assigned_by_name = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    submission_preview_url = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ('assigned_by', 'submitted_at')

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
        if request and request.user.role == request.user.Role.STUDENT and self.instance:
            forbidden = set(attrs) - {'status', 'student_response', 'submission_url', 'submission_file'}
            if forbidden:
                raise serializers.ValidationError({
                    field: 'Only a teacher or counselor can change this field.' for field in sorted(forbidden)
                })
        return attrs

    def get_submission_preview_url(self, obj):
        return google_docs_preview_url(obj.submission_url)

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

    def get_assigned_by_name(self, obj) -> str | None:
        if not obj.assigned_by:
            return None
        return obj.assigned_by.get_full_name() or obj.assigned_by.username


class DocumentSerializer(StudentRecordSerializerMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = '__all__'

    def validate_status(self, value):
        request = self.context.get('request')
        if request and not request.user.is_counselor_like and value in {Document.Status.APPROVED, Document.Status.REJECTED}:
            raise serializers.ValidationError('Only a counselor can approve or reject documents.')
        return value

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username


class AchievementSerializer(VerifiedStudentRecordMixin, serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Achievement
        fields = '__all__'

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


class HonorSerializer(VerifiedStudentRecordMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Honor
        fields = '__all__'

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username


class RecommendationLetterSerializer(StudentRecordSerializerMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = RecommendationLetter
        fields = '__all__'

    def get_student_name(self, obj) -> str | None:
        return obj.student.user.get_full_name() or obj.student.user.username

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

    def get_author_initials(self, obj):
        name = obj.author.user.get_full_name() or obj.author.user.username
        return ''.join(part[0] for part in name.split()[:2]).upper()

    def get_liked_by_me(self, obj):
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

    def get_participant_name(self, obj):
        if not obj.participant:
            return None
        return obj.participant.get_full_name() or obj.participant.username

    def get_student_name(self, obj):
        return obj.student.user.get_full_name() or obj.student.user.username

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

    def get_display_name(self, obj):
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

    def get_is_member(self, obj):
        return self._membership(obj) is not None

    def get_my_role(self, obj):
        membership = self._membership(obj)
        return membership.role if membership else None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        membership = self._membership(obj)
        if not request or not membership:
            return 0
        messages = obj.messages.filter(deleted_at__isnull=True).exclude(sender=request.user)
        if membership.last_read_at:
            messages = messages.filter(created_at__gt=membership.last_read_at)
        return messages.count()

    def get_last_message(self, obj):
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

    def get_sender_id(self, obj):
        if obj.is_anonymous and not self._can_reveal_sender(obj):
            return None
        return obj.sender_id

    def get_sender_name(self, obj):
        if obj.is_anonymous and not self._can_reveal_sender(obj):
            return 'Anonymous'
        if not obj.sender:
            return 'Deleted user'
        return obj.sender.get_full_name() or obj.sender.username

    def get_parent_preview(self, obj):
        if not obj.parent:
            return None
        return {'id': obj.parent_id, 'body': obj.parent.body[:120]}

    def get_is_reported_by_me(self, obj):
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

    def get_channel_name(self, obj):
        return obj.message.channel.name or obj.message.channel.get_kind_display()

    def get_message_body(self, obj):
        return 'Message deleted' if obj.message.deleted_at else obj.message.body

    def get_sender_name(self, obj):
        sender = obj.message.sender
        if not sender:
            return 'Deleted user'
        return sender.get_full_name() or sender.username

    def get_reporter_name(self, obj):
        return obj.reporter.get_full_name() or obj.reporter.username

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.username


class ProgramServiceSerializer(serializers.ModelSerializer):
    mentor_name = serializers.SerializerMethodField()
    remaining_hours = serializers.SerializerMethodField()

    class Meta:
        model = ProgramService
        fields = '__all__'

    def get_mentor_name(self, obj):
        if not obj.mentor:
            return None
        return obj.mentor.get_full_name() or obj.mentor.username

    def get_remaining_hours(self, obj):
        if obj.unlimited or obj.total_hours is None:
            return None
        return max(obj.total_hours - obj.used_hours, 0)


class ResourceLibraryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceLibraryItem
        fields = '__all__'


class StoreItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreItem
        fields = '__all__'
