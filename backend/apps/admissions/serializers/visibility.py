"""Admissions API serializers — visibility."""
from rest_framework import serializers
from django.urls import reverse
from apps.users.models import User
from ..exam_scores import IELTS_FIELDS, SAT_FIELDS
from ..models import (
    Achievement,
    Activity,
    Application,
    Booking,
    Document,
    Essay,
    Honor,
    Internship,
    ProgramService,
    Project,
    RecommendationLetter,
    Research,
    RoadmapMission,
    StudentProfile,
    Task,
)
from .common import PrivateEvidenceSerializerMixin, google_docs_preview_url


class SchoolVisibilityUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'full_name', 'phone', 'is_active')

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


EXAM_FIELDS = (*IELTS_FIELDS, *SAT_FIELDS)


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
            'id', 'user', 'grade', 'school', 'school_name', 'gpa', 'gpa_scale', *EXAM_FIELDS,
            'target_major', 'target_countries', 'budget_usd', 'scholarship_needed', 'parent_contact',
            'xp_total', 'level', 'eligible_level', 'xp_progress_percent', 'progress_percent',
            'task_progress_percent', 'roadmap_progress_percent', 'journey_progress_percent',
            'counselor_name', 'created_at', 'updated_at',
        )

    def get_counselor_name(self, obj):
        return obj.assigned_counselor.get_full_name() or obj.assigned_counselor.username if obj.assigned_counselor else None


class SchoolVisibilityTaskSerializer(serializers.ModelSerializer):
    assigned_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = (
            'id', 'title', 'description', 'due_date', 'priority', 'status', 'is_self_assigned',
            'assigned_by_name', 'submitted_at', 'created_at', 'updated_at',
        )

    def get_assigned_by_name(self, obj):
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

    def get_has_file(self, obj):
        return bool(obj.file)

    def get_file_preview_url(self, obj):
        request = self.context.get('request')
        return request.build_absolute_uri(reverse('documents-file', args=[obj.pk])) if request and obj.file else None

    def get_file_download_url(self, obj):
        request = self.context.get('request')
        return request.build_absolute_uri(f"{reverse('documents-file', args=[obj.pk])}?download=1") if request and obj.file else None

    def get_google_docs_preview_url(self, obj):
        return google_docs_preview_url(obj.google_docs_url)


class SchoolVisibilityEssaySerializer(serializers.ModelSerializer):
    university_name = serializers.SerializerMethodField()

    class Meta:
        model = Essay
        fields = ('id', 'title', 'status', 'version', 'application', 'university_name', 'created_at', 'updated_at')

    def get_university_name(self, obj):
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

    def get_participant_name(self, obj):
        return obj.participant.get_full_name() or obj.participant.username if obj.participant else None


class SchoolVisibilityProgramServiceSerializer(serializers.ModelSerializer):
    mentor_name = serializers.SerializerMethodField()

    class Meta:
        model = ProgramService
        fields = (
            'id', 'name', 'category', 'mentor_name', 'total_hours', 'used_hours', 'unlimited',
            'status', 'created_at', 'updated_at',
        )

    def get_mentor_name(self, obj):
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


class SchoolVisibilityActivitySerializer(PrivateEvidenceSerializerMixin, serializers.ModelSerializer):
    evidence_resource = 'activities'
    has_proof_file = serializers.SerializerMethodField()
    proof_file_previewable = serializers.SerializerMethodField()
    proof_file_preview_url = serializers.SerializerMethodField()
    proof_file_download_url = serializers.SerializerMethodField()
    proof_resource = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = (
            'id', 'name', 'activity_type', 'role', 'description', 'impact', 'hours_per_week', 'weeks_per_year',
            'start_date', 'end_date', 'verified',
            'has_proof_file', 'proof_file_name', 'proof_file_content_type', 'proof_file_size',
            'proof_file_previewable', 'proof_file_preview_url', 'proof_file_download_url',
            'proof_resource', 'created_at', 'updated_at',
        )


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
