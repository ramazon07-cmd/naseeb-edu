"""Admissions API views — roadmaps."""
from datetime import timedelta
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.users.models import User
from ..models import (
    ActivityLog,
    RoadmapMission,
    CounselorRoadmap,
    CounselorRoadmapMission,
    CounselorRoadmapTemplate,
    StudentProfile,
    XPTransaction,
)
from ..serializers import (
    RoadmapMissionSerializer,
    CounselorRoadmapSerializer,
    CounselorRoadmapTemplateSerializer,
    StudentProfileSerializer,
)
from ..services import ROADMAP_APPROVAL_XP, award_approval_xp, extend_level_one_roadmap
from apps.users.services import audit_product_action
from ..params import int_param
from ..scoping import visible_students
from .common import RECORD_ORDERING, StaffControlledWorkMixin, StudentRecordListMixin


class RoadmapMissionViewSet(StudentRecordListMixin, StaffControlledWorkMixin, viewsets.ModelViewSet):
    serializer_class = RoadmapMissionSerializer
    queryset = RoadmapMission.objects.select_related('student__user', 'assigned_by', 'prerequisite').all()
    search_fields = ('title',)
    choice_filters = {'status': ('status', RoadmapMission.Status.choices)}
    int_filters = {**StudentRecordListMixin.int_filters, 'level': 'level'}
    date_filters = {**StudentRecordListMixin.date_filters, 'due': 'due_date'}
    ordering_options = {**RECORD_ORDERING, 'sequence': ('level', 'sequence', 'id')}

    def get_queryset(self):
        return self.filter_work_for_user(self.queryset)

    def perform_create(self, serializer):
        serializer.save(assigned_by=self.request.user)

    @action(detail=False, methods=['post'], url_path='extend-level-one')
    def extend_level_one(self, request):
        if not request.user.is_task_manager:
            return Response({'detail': 'Only a teacher or counselor can extend Level 1.'}, status=403)
        student_id = int_param(request.data, 'student')
        if not student_id:
            return Response({'student': ['Select a student.']}, status=400)

        students = visible_students(request.user, StudentProfile.objects.select_related('user', 'assigned_counselor'))
        student = students.filter(pk=student_id).first()
        if not student:
            return Response({'student': ['Student is outside your assigned scope.']}, status=403)

        missions, created_count = extend_level_one_roadmap(
            student=student,
            assigned_by=request.user,
        )
        return Response({
            'student': student.id,
            'level': 1,
            'created_count': created_count,
            'total_count': len(missions),
            'missions': RoadmapMissionSerializer(missions, many=True, context={'request': request}).data,
        })

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if not request.user.is_task_manager:
            return Response({'detail': 'Only a teacher or counselor can approve roadmap missions.'}, status=403)
        scoped_mission = self.get_object()
        with transaction.atomic():
            mission = RoadmapMission.objects.select_for_update(of=('self',)).select_related('student').get(pk=scoped_mission.pk)
            if mission.status not in {RoadmapMission.Status.SUBMITTED, RoadmapMission.Status.COMPLETED}:
                return Response({'detail': 'The student must submit the mission before approval.'}, status=400)
            newly_approved = mission.status != RoadmapMission.Status.COMPLETED
            mission.status = RoadmapMission.Status.COMPLETED
            mission.save(update_fields=['status', 'updated_at'])
            _, xp_created = award_approval_xp(
                student=mission.student,
                source_type=XPTransaction.Source.ROADMAP,
                source_id=mission.id,
                amount=ROADMAP_APPROVAL_XP,
                reason=f'Roadmap mission approved: {mission.title}',
                awarded_by=request.user,
            )
            if newly_approved:
                ActivityLog.objects.create(
                    actor=request.user,
                    student=mission.student,
                    action=f'Roadmap mission approved: {mission.title} (+{ROADMAP_APPROVAL_XP} XP)',
                    metadata={'roadmap_mission': mission.id},
                )
        mission.student.refresh_from_db()
        data = RoadmapMissionSerializer(mission, context={'request': request}).data
        data['xp_awarded'] = ROADMAP_APPROVAL_XP if xp_created else 0
        data['student_leveling'] = StudentProfileSerializer(mission.student, context={'request': request}).data
        return Response(data)


class CounselorRoadmapTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = CounselorRoadmapTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = CounselorRoadmapTemplate.objects.prefetch_related('missions').all()

    def get_queryset(self):
        user = self.request.user
        if not (user.is_product_admin or user.role == User.Role.COUNSELOR):
            return self.queryset.none()
        queryset = self.queryset
        if user.role == User.Role.COUNSELOR:
            queryset = queryset.filter(is_active=True)
        kind = self.request.query_params.get('kind')
        active = self.request.query_params.get('is_active')
        search = self.request.query_params.get('search', '').strip()
        if kind:
            queryset = queryset.filter(kind=kind)
        if active in {'true', 'false'}:
            queryset = queryset.filter(is_active=active == 'true')
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return queryset

    def create(self, request, *args, **kwargs):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can create roadmap templates.'}, status=403)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can edit roadmap templates.'}, status=403)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can delete roadmap templates.'}, status=403)
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        template = serializer.save()
        audit_product_action(actor=self.request.user, action='counselor_roadmap_template.created', target=template)

    def perform_update(self, serializer):
        template = serializer.save()
        audit_product_action(actor=self.request.user, action='counselor_roadmap_template.updated', target=template)


class CounselorRoadmapViewSet(viewsets.ModelViewSet):
    serializer_class = CounselorRoadmapSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = CounselorRoadmap.objects.select_related(
        'counselor', 'school', 'template', 'assigned_by'
    ).prefetch_related('missions__approved_by').all()

    def get_queryset(self):
        user = self.request.user
        if user.is_product_admin:
            queryset = self.queryset
            counselor = int_param(self.request.query_params, 'counselor')
            school = int_param(self.request.query_params, 'school')
            status_value = self.request.query_params.get('status')
            if counselor:
                queryset = queryset.filter(counselor_id=counselor)
            if school:
                queryset = queryset.filter(school_id=school)
            if status_value:
                queryset = queryset.filter(status=status_value)
            return queryset
        if user.role == User.Role.COUNSELOR:
            return self.queryset.filter(counselor=user)
        return self.queryset.none()

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                return self._create_roadmap(request, *args, **kwargs)
        except IntegrityError:
            # unique_active_counselor_roadmap_kind: lost a race with another create.
            return Response({'detail': 'This counselor already has an active roadmap of this type.'}, status=409)

    def _create_roadmap(self, request, *args, **kwargs):
        if request.user.is_product_admin:
            response = super().create(request, *args, **kwargs)
            roadmap = CounselorRoadmap.objects.get(pk=response.data['id'])
            audit_product_action(actor=request.user, action='counselor_roadmap.assigned', target=roadmap)
            return response
        if request.user.role != User.Role.COUNSELOR:
            return Response({'detail': 'Only a counselor or product admin can start a counselor roadmap.'}, status=403)

        template_id = int_param(request.data, 'template')
        template = None
        if template_id:
            template = CounselorRoadmapTemplate.objects.filter(pk=template_id, is_active=True).first()
            if not template:
                return Response({'template': ['Select an active roadmap template.']}, status=400)
            roadmap_kind = template.kind
        else:
            roadmap_kind = str(request.data.get('kind') or '').strip()
            if roadmap_kind not in CounselorRoadmapTemplate.Kind.values:
                return Response({'kind': ['Select a roadmap type.']}, status=400)
            title = str(request.data.get('title') or '').strip()
            if not title:
                return Response({'title': ['Add a title for your roadmap.']}, status=400)
            if len(title) > CounselorRoadmap._meta.get_field('title').max_length:
                return Response({'title': ['Roadmap title is too long.']}, status=400)
            raw_missions = request.data.get('missions')
            if not isinstance(raw_missions, list) or not raw_missions:
                return Response({'missions': ['Add at least one roadmap mission.']}, status=400)
            if len(raw_missions) > 30:
                return Response({'missions': ['Use 30 missions or fewer.']}, status=400)
            mission_titles = []
            for item in raw_missions:
                mission_title = str(item.get('title') if isinstance(item, dict) else item).strip()
                if not mission_title:
                    return Response({'missions': ['Mission titles cannot be empty.']}, status=400)
                if len(mission_title) > CounselorRoadmapMission._meta.get_field('title').max_length:
                    return Response({'missions': ['A mission title is too long.']}, status=400)
                mission_titles.append(mission_title)

        if CounselorRoadmap.objects.filter(
            counselor=request.user,
            kind=roadmap_kind,
            status=CounselorRoadmap.Status.ACTIVE,
        ).exists():
            return Response({'detail': 'You already have an active roadmap of this type.'}, status=409)

        if template:
            payload = request.data.copy()
            payload['counselor'] = request.user.pk
            serializer = self.get_serializer(data=payload)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=201, headers=self.get_success_headers(serializer.data))

        with transaction.atomic():
            roadmap = CounselorRoadmap.objects.create(
                counselor=request.user,
                school=request.user.school,
                template=None,
                title=title,
                kind=roadmap_kind,
                assigned_by=request.user,
            )
            today = timezone.localdate()
            CounselorRoadmapMission.objects.bulk_create([
                CounselorRoadmapMission(
                    roadmap=roadmap,
                    title=mission_title,
                    sequence=index,
                    due_date=today + timedelta(days=index * 7),
                    is_required=True,
                )
                for index, mission_title in enumerate(mission_titles, start=1)
            ])
        return Response(self.get_serializer(roadmap).data, status=201)

    def update(self, request, *args, **kwargs):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can edit counselor roadmaps.'}, status=403)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can cancel counselor roadmaps.'}, status=403)
        roadmap = self.get_object()
        roadmap.status = CounselorRoadmap.Status.CANCELLED
        roadmap.save(update_fields=['status', 'updated_at'])
        audit_product_action(actor=request.user, action='counselor_roadmap.cancelled', target=roadmap)
        return Response(status=204)

    @staticmethod
    def lock_active_roadmap(roadmap):
        """Lock the roadmap row; cancelled or completed roadmaps accept no mission changes."""
        locked = CounselorRoadmap.objects.select_for_update().get(pk=roadmap.pk)
        return locked.status == CounselorRoadmap.Status.ACTIVE

    @action(detail=True, methods=['post'], url_path='submit-mission')
    def submit_mission(self, request, pk=None):
        roadmap = self.get_object()
        if request.user.role != User.Role.COUNSELOR or roadmap.counselor_id != request.user.id:
            return Response({'detail': 'Only the assigned counselor can submit this mission.'}, status=403)
        mission_id = int_param(request.data, 'mission')
        note = str(request.data.get('counselor_note', '')).strip()
        if not note:
            return Response({'counselor_note': ['Add a completion note before submitting.']}, status=400)
        with transaction.atomic():
            if not self.lock_active_roadmap(roadmap):
                return Response({'detail': 'Missions can only be submitted on an active roadmap.'}, status=409)
            mission = CounselorRoadmapMission.objects.select_for_update().filter(
                pk=mission_id,
                roadmap=roadmap,
            ).first()
            if not mission:
                return Response({'mission': ['Mission does not belong to this roadmap.']}, status=400)
            if mission.status == CounselorRoadmapMission.Status.APPROVED:
                return Response({'detail': 'An approved mission cannot be resubmitted.'}, status=409)
            mission.status = CounselorRoadmapMission.Status.SUBMITTED
            mission.counselor_note = note
            mission.submitted_at = timezone.now()
            mission.admin_feedback = ''
            mission.save(update_fields=['status', 'counselor_note', 'submitted_at', 'admin_feedback', 'updated_at'])
        roadmap = self.queryset.get(pk=roadmap.pk)
        return Response(self.get_serializer(roadmap).data)

    @action(detail=True, methods=['post'], url_path='review-mission')
    def review_mission(self, request, pk=None):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can review counselor missions.'}, status=403)
        roadmap = self.get_object()
        decision = request.data.get('decision')
        if decision not in {'approve', 'request_changes'}:
            return Response({'decision': ['Choose approve or request_changes.']}, status=400)
        with transaction.atomic():
            if not self.lock_active_roadmap(roadmap):
                return Response({'detail': 'Missions can only be reviewed on an active roadmap.'}, status=409)
            mission = CounselorRoadmapMission.objects.select_for_update().filter(
                pk=int_param(request.data, 'mission'), roadmap=roadmap
            ).first()
            if not mission or mission.status != CounselorRoadmapMission.Status.SUBMITTED:
                return Response({'mission': ['Select a submitted mission from this roadmap.']}, status=400)
            mission.admin_feedback = str(request.data.get('admin_feedback', '')).strip()
            if decision == 'approve':
                mission.status = CounselorRoadmapMission.Status.APPROVED
                mission.approved_at = timezone.now()
                mission.approved_by = request.user
            else:
                if not mission.admin_feedback:
                    return Response({'admin_feedback': ['Explain the requested changes.']}, status=400)
                mission.status = CounselorRoadmapMission.Status.CHANGES_REQUESTED
                mission.approved_at = None
                mission.approved_by = None
            mission.save()
            required = roadmap.missions.filter(is_required=True)
            if required.exists() and not required.exclude(status=CounselorRoadmapMission.Status.APPROVED).exists():
                roadmap.status = CounselorRoadmap.Status.COMPLETED
                roadmap.completed_at = timezone.now()
                roadmap.save(update_fields=['status', 'completed_at', 'updated_at'])
        audit_product_action(
            actor=request.user,
            action=f'counselor_roadmap_mission.{decision}',
            target=mission,
            metadata={'roadmap': roadmap.pk},
        )
        roadmap = self.queryset.get(pk=roadmap.pk)
        return Response(self.get_serializer(roadmap).data)
