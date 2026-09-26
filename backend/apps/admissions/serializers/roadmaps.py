"""Admissions API serializers — roadmaps."""
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from apps.users.models import User
from ..services import ROADMAP_APPROVAL_XP
from ..models import (
    RoadmapMission,
    CounselorRoadmap,
    CounselorRoadmapMission,
    CounselorRoadmapTemplate,
    CounselorRoadmapTemplateMission,
)
from .common import GoogleDocsModelSerializer, StudentRecordSerializerMixin


class RoadmapMissionSerializer(StudentRecordSerializerMixin, GoogleDocsModelSerializer):
    student_name = serializers.SerializerMethodField()
    assigned_by_name = serializers.SerializerMethodField()
    prerequisite_title = serializers.CharField(source='prerequisite.title', read_only=True)
    prerequisite_sequence = serializers.IntegerField(source='prerequisite.sequence', read_only=True)
    # Lets a paged list tell a locked mission apart without loading its prerequisite.
    prerequisite_status = serializers.SerializerMethodField()
    xp_reward = serializers.SerializerMethodField()
    approval_status = serializers.SerializerMethodField()

    class Meta:
        model = RoadmapMission
        fields = '__all__'
        read_only_fields = ('assigned_by',)

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
            forbidden = set(attrs) - {'status', 'reflection', 'google_docs_url'}
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
            docs_url = attrs.get('google_docs_url', self.instance.google_docs_url)
            if not (reflection or '').strip() and not (docs_url or '').strip():
                raise serializers.ValidationError({
                    'reflection': 'Add a reflection or a Google Docs link before submitting the mission.'
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

    def get_prerequisite_status(self, obj) -> str | None:
        return obj.prerequisite.status if obj.prerequisite_id else None

    def get_xp_reward(self, obj) -> int:
        return ROADMAP_APPROVAL_XP

    def get_approval_status(self, obj):
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

    def get_approved_by_name(self, obj):
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

    def get_counselor_name(self, obj):
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
