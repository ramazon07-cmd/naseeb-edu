"""Admissions API serializers — students."""
from rest_framework import serializers
from apps.users.images import image_version
from apps.users.models import User
from apps.users.serializers import UserSerializer
from ..models import (
    LevelApproval,
    RoadmapMission,
    StudentProfile,
    Task,
    XPTransaction,
)
from ..exam_scores import EXAM_KEYS
from ..onboarding import band_field, profile_readiness, sat_total_field, validate_half_band
from .common import validate_gpa_on_scale


class StudentProfileSerializer(serializers.ModelSerializer):
    STUDENT_EDITABLE_FIELDS = {
        'grade', 'gpa', 'gpa_scale', 'ielts_score', 'sat_score',
        'target_major', 'target_countries', 'budget_usd', 'scholarship_needed',
        'parent_contact', 'notes',
    }
    # Same rules as onboarding, checked here so a bad score is a 400, not a database error.
    ielts_score = band_field(validators=[validate_half_band])
    sat_score = sat_total_field()
    user_detail = UserSerializer(source='user', read_only=True)
    counselor_name = serializers.SerializerMethodField()
    progress_percent = serializers.IntegerField(read_only=True)
    task_progress_percent = serializers.IntegerField(read_only=True)
    roadmap_progress_percent = serializers.IntegerField(read_only=True)
    journey_progress_percent = serializers.IntegerField(read_only=True)
    is_at_risk = serializers.BooleanField(read_only=True)
    readiness_items_done = serializers.SerializerMethodField()
    readiness_items_total = serializers.SerializerMethodField()
    level_missions_approved = serializers.SerializerMethodField()
    level_missions_total = serializers.SerializerMethodField()
    applications_total = serializers.SerializerMethodField()
    applications_submitted = serializers.SerializerMethodField()
    applications_accepted = serializers.SerializerMethodField()
    achievements_total = serializers.SerializerMethodField()
    task_status_counts = serializers.SerializerMethodField()
    roadmap_status_counts = serializers.SerializerMethodField()
    eligible_level = serializers.IntegerField(read_only=True)
    next_level_xp = serializers.IntegerField(read_only=True)
    xp_progress_percent = serializers.IntegerField(read_only=True)
    level_up_pending = serializers.BooleanField(read_only=True)
    roadmap_stars = serializers.IntegerField(read_only=True)
    photo = serializers.ImageField(write_only=True, required=False, allow_null=True)
    has_photo = serializers.SerializerMethodField()
    photo_version = serializers.SerializerMethodField()
    profile_readiness = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = '__all__'
        # Test detail is written only through onboarding, which validates it as a whole.
        read_only_fields = (
            'xp_total', 'level', 'application_profile', 'profile_completed_at', 'deactivated_at',
            *sorted(EXAM_KEYS - {'ielts_score', 'sat_score'}),
        )

    UNAVAILABLE_USER = 'Select a student account from your school that has no profile yet.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The lookup itself is scoped, so a missing id, another school's user,
        # a non-student and an account that already has a profile all produce
        # the same error (no account enumeration).
        field = self.fields['user']
        field.error_messages['does_not_exist'] = self.UNAVAILABLE_USER
        field.error_messages['incorrect_type'] = self.UNAVAILABLE_USER
        candidates = User.objects.filter(role=User.Role.STUDENT, is_active=True, student_profile__isnull=True)
        request = self.context.get('request')
        requester = getattr(request, 'user', None)
        if requester is None or not requester.is_authenticated:
            field.queryset = candidates.none()
        elif not requester.is_product_admin:
            field.queryset = candidates.filter(school_id=requester.school_id) if requester.school_id else candidates.none()
        else:
            field.queryset = candidates

    def get_has_photo(self, obj) -> bool:
        return bool(obj.photo)

    def get_photo_version(self, obj) -> str | None:
        return image_version(obj.photo)

    def get_profile_readiness(self, obj) -> dict:
        return profile_readiness(obj)

    def get_counselor_name(self, obj) -> str | None:
        if not obj.assigned_counselor:
            return None
        return obj.assigned_counselor.get_full_name() or obj.assigned_counselor.username

    def get_readiness_items_done(self, obj) -> int:
        return obj.progress_stats.readiness_items_done

    def get_readiness_items_total(self, obj) -> int:
        return obj.progress_stats.readiness_items_total

    def get_level_missions_approved(self, obj) -> int:
        return obj.progress_stats.level_missions(obj.level)[0]

    def get_level_missions_total(self, obj) -> int:
        return obj.progress_stats.level_missions(obj.level)[1]

    def get_applications_total(self, obj) -> int:
        return obj.progress_stats.applications_total

    def get_applications_submitted(self, obj) -> int:
        return obj.progress_stats.applications_done

    def get_applications_accepted(self, obj) -> int:
        return obj.progress_stats.applications_accepted

    def get_achievements_total(self, obj) -> int:
        return obj.progress_stats.achievements_total

    def get_task_status_counts(self, obj):
        counts = {choice: 0 for choice, _ in Task.Status.choices}
        counts.update(obj.progress_stats.task_counts)
        return counts

    def get_roadmap_status_counts(self, obj):
        counts = {choice: 0 for choice, _ in RoadmapMission.Status.choices}
        counts.update(obj.progress_stats.mission_counts)
        return counts

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user.is_organization:
            data.pop('notes', None)
        return data

    def validate(self, attrs):
        request = self.context.get('request')
        if self.instance and 'user' in attrs and attrs['user'] != self.instance.user:
            raise serializers.ValidationError({'user': 'A profile cannot be moved to another account.'})
        if not self.instance and request and not request.user.is_product_admin:
            # School staff always create profiles in their own active school.
            own_school = request.user.school
            if own_school is None or not own_school.is_active:
                raise serializers.ValidationError({'school': 'Your account is not connected to an active school.'})
            attrs['school'] = own_school
        if not self.instance:
            school = attrs.get('school')
            user = attrs.get('user')
            if school is None or not school.is_active:
                raise serializers.ValidationError({'school': 'Select an active school.'})
            if user is not None and user.school_id not in {None, school.id}:
                raise serializers.ValidationError({'user': self.UNAVAILABLE_USER})
            attrs.setdefault('school_name', school.name)
        if self.instance and request and request.user.role != User.Role.STUDENT:
            protected = set(attrs) - {'assigned_counselor', 'school', 'notes'}
            if protected:
                raise serializers.ValidationError({key: 'Only the student can edit their profile.' for key in protected})
        user = attrs.get('user', getattr(self.instance, 'user', None))
        school = attrs.get('school', getattr(self.instance, 'school', None))
        assigned_counselor = attrs.get(
            'assigned_counselor', getattr(self.instance, 'assigned_counselor', None)
        )
        if 'assigned_counselor' not in attrs and assigned_counselor and school and assigned_counselor.school_id != school.id:
            # A move unassigns a counselor who stays behind (see move_student).
            assigned_counselor = None
        if user and user.role != user.Role.STUDENT:
            raise serializers.ValidationError({'user': 'Student profile requires a student user.'})
        if (
            self.instance
            and 'school' in attrs
            and attrs['school'] != self.instance.school
            and not (request and request.user.is_product_admin)
        ):
            raise serializers.ValidationError({'school': 'Only a product admin can move a student to another school.'})
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
        if 'gpa' in attrs or 'gpa_scale' in attrs:
            validate_gpa_on_scale(
                attrs.get('gpa', getattr(self.instance, 'gpa', None)),
                attrs.get('gpa_scale', getattr(self.instance, 'gpa_scale', None)),
            )
        return attrs


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
