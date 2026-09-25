"""Admissions API serializers — portal."""
from rest_framework import serializers
from django.utils import timezone
from apps.users.models import User
from apps.users.serializers import ContactSerializer
from ..models import (
    Booking,
    ProgramService,
    ScreenTimeDaily,
    StudentMessage,
)
from ..scoping import booking_participants_for, school_staff, tenant_school_id
from .common import StudentRecordSerializerMixin, scope_related_field

UNAVAILABLE_PARTICIPANT = 'Choose your assigned counselor, teacher, or a representative from your school.'
UNAVAILABLE_MENTOR = "Select a counselor or teacher from the student's school."


class BookingSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    # Narrowed to the requesting student's school staff in get_fields().
    participant = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.none(),
        required=True,
        allow_null=False,
    )
    participant_name = serializers.SerializerMethodField()
    participant_role = serializers.CharField(source='participant.role', read_only=True)
    participant_detail = ContactSerializer(source='participant', read_only=True)
    student_name = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)

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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            data.pop('notes', None)
        return data

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        profile = getattr(user, 'student_profile', None) if user and user.role == User.Role.STUDENT else None
        # Only staff of the student's current school; an assignment never
        # reaches across schools, and other ids fail like missing ones.
        scope_related_field(fields['participant'], booking_participants_for(profile), UNAVAILABLE_PARTICIPANT)
        return fields

    def validate_participant(self, participant):
        request = self.context.get('request')
        if not request or request.user.role != User.Role.STUDENT or not hasattr(request.user, 'student_profile'):
            raise serializers.ValidationError('Only students can request meetings.')
        return participant

    def validate_starts_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError('Choose a future meeting date and time.')
        return value

    def validate_duration_minutes(self, value):
        if value not in {30, 45, 60}:
            raise serializers.ValidationError('Choose a 30, 45, or 60 minute meeting.')
        return value


class BookingRescheduleSerializer(serializers.Serializer):
    """A new time for an existing request, checked by the same rules as a new one."""

    starts_at = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(required=False)

    validate_starts_at = BookingSerializer.validate_starts_at
    validate_duration_minutes = BookingSerializer.validate_duration_minutes


class StudentMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    recipient_name = serializers.CharField(source='recipient.get_full_name', read_only=True)

    class Meta:
        model = StudentMessage
        fields = '__all__'
        read_only_fields = ('student', 'sender', 'recipient', 'is_read')


class ProgramServiceSerializer(StudentRecordSerializerMixin, serializers.ModelSerializer):
    mentor_name = serializers.SerializerMethodField()
    mentor_role = serializers.CharField(source='mentor.role', read_only=True)
    student_name = serializers.SerializerMethodField()
    remaining_hours = serializers.SerializerMethodField()

    class Meta:
        model = ProgramService
        fields = '__all__'

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not user.is_product_admin:
            mentors = school_staff(tenant_school_id(user), roles=(User.Role.COUNSELOR, User.Role.TEACHER))
            scope_related_field(fields['mentor'], mentors, UNAVAILABLE_MENTOR)
        return fields

    def get_mentor_name(self, obj):
        if not obj.mentor:
            return None
        return obj.mentor.get_full_name() or obj.mentor.username

    def get_student_name(self, obj):
        return obj.student.user.get_full_name() or obj.student.user.username

    def get_remaining_hours(self, obj):
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

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
