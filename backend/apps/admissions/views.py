from datetime import date, timedelta
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.utils.text import slugify
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from pathlib import Path
import mimetypes
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers
from drf_spectacular.utils import extend_schema, inline_serializer

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
    ChallengeAttempt,
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
from .serializers import (
    AchievementSerializer,
    ActivitySerializer,
    ActivityLogSerializer,
    ApplicationSerializer,
    BookingSerializer,
    ChallengeAttemptSerializer,
    ChannelMembershipSerializer,
    ChannelMessageSerializer,
    CommunityPostSerializer,
    CollegeResearchProfileSerializer,
    DocumentSerializer,
    EssaySerializer,
    HonorSerializer,
    InternshipSerializer,
    LevelApprovalSerializer,
    MeetingNoteSerializer,
    MessageChannelSerializer,
    MessageReportSerializer,
    NotificationSerializer,
    OpportunityProgramSerializer,
    OrganizationAccountSerializer,
    ParentInviteSerializer,
    ParentStudentLinkSerializer,
    ProgramServiceSerializer,
    ProjectSerializer,
    RecommendationLetterSerializer,
    ResearchSerializer,
    ResourceLibraryItemSerializer,
    RoadmapMissionSerializer,
    CounselorRoadmapSerializer,
    CounselorRoadmapTemplateSerializer,
    SchoolSerializer,
    ScreenTimeDailySerializer,
    SchoolVisibilityAchievementSerializer,
    SchoolVisibilityActivitySerializer,
    SchoolVisibilityApplicationSerializer,
    SchoolVisibilityBookingSerializer,
    SchoolVisibilityDocumentSerializer,
    SchoolVisibilityEssaySerializer,
    SchoolVisibilityHonorSerializer,
    SchoolVisibilityInternshipSerializer,
    SchoolVisibilityProgramServiceSerializer,
    SchoolVisibilityProjectSerializer,
    SchoolVisibilityRecommendationSerializer,
    SchoolVisibilityResearchSerializer,
    SchoolVisibilityRoadmapSerializer,
    SchoolVisibilityStudentSerializer,
    SchoolVisibilityTaskSerializer,
    ScholarshipSerializer,
    StoreItemSerializer,
    SupportTicketSerializer,
    StudentProfileSerializer,
    StudentMessageSerializer,
    TaskSerializer,
    UniversitySerializer,
    XPTransactionSerializer,
)
from .services import (
    ROADMAP_APPROVAL_XP,
    TASK_XP_BY_PRIORITY,
    award_approval_xp,
    extend_level_one_roadmap,
)
from apps.users.services import audit_product_action


class CounselorOrOwnerPermission(permissions.BasePermission):
    organization_read_resources = {
        'tasks', 'applications', 'documents', 'essays', 'achievements',
        'researches', 'projects', 'internships', 'activities',
        'honors', 'recommendations',
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        user = request.user
        if user.is_counselor_like:
            return True
        if user.role == User.Role.TEACHER:
            return bool(
                view.basename == 'students'
                and (request.method in permissions.SAFE_METHODS or view.action == 'approve_level')
            )
        if user.is_organization:
            if view.basename == 'schools':
                return request.method in permissions.SAFE_METHODS
            if view.basename == 'students':
                return True
            return (
                request.method in permissions.SAFE_METHODS
                and view.basename in self.organization_read_resources
            )
        if request.method in permissions.SAFE_METHODS:
            return True
        if view.basename == 'notifications' and view.action == 'read':
            return True
        if view.basename == 'students':
            return view.action in {'update', 'partial_update'}
        if view.basename == 'tasks' and view.action == 'create':
            return False
        return view.basename in {
            'applications', 'documents', 'essays', 'tasks', 'achievements', 'researches', 'projects',
            'internships', 'activities', 'honors', 'recommendations',
        }

    def has_object_permission(self, request, view, obj):
        if request.user.is_counselor_like:
            return True
        if request.user.role == User.Role.TEACHER:
            student = obj if isinstance(obj, StudentProfile) else getattr(obj, 'student', None)
            return bool(
                (request.method in permissions.SAFE_METHODS or view.action == 'approve_level')
                and isinstance(student, StudentProfile)
                and request.user.school_id
                and student.school_id == request.user.school_id
            )
        if isinstance(obj, School) and request.user.is_organization:
            return request.method in permissions.SAFE_METHODS and obj.id == request.user.school_id
        student = getattr(obj, 'student', obj if isinstance(obj, StudentProfile) else None)
        if request.user.is_organization:
            owns_student = bool(
                isinstance(student, StudentProfile)
                and request.user.school_id
                and student.school_id == request.user.school_id
            )
            if not owns_student:
                return False
            if view.basename == 'students':
                return True
            return request.method in permissions.SAFE_METHODS
        if student and getattr(student, 'user_id', None) == request.user.id:
            if view.basename == 'notifications' and view.action == 'read':
                return True
            if view.basename == 'students':
                return view.action in {'retrieve', 'update', 'partial_update'}
            return request.method in permissions.SAFE_METHODS or view.basename in {
                'applications', 'documents', 'essays', 'tasks', 'achievements', 'researches', 'projects',
                'internships', 'activities', 'honors', 'recommendations',
            }
        return False


class SupportTicketPermission(permissions.BasePermission):
    allowed_roles = {
        User.Role.ADMIN,
        User.Role.COUNSELOR,
        User.Role.ORGANIZATION,
        User.Role.STUDENT,
    }

    @staticmethod
    def is_product_admin(user):
        return bool(user.is_superuser or user.role == User.Role.ADMIN)

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or user.role not in self.allowed_roles:
            return False
        if view.action in {'update', 'partial_update'}:
            return self.is_product_admin(user)
        return True

    def has_object_permission(self, request, view, obj):
        if self.is_product_admin(request.user):
            return True
        if obj.requester_id != request.user.id:
            return False
        return request.method in permissions.SAFE_METHODS or view.action == 'mark_viewed'


class ScopedQuerysetMixin:
    permission_classes = [CounselorOrOwnerPermission]

    def filter_for_user(self, queryset):
        user = self.request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return queryset
        if user.role == User.Role.COUNSELOR:
            if not user.school_id:
                return queryset.none()
            if queryset.model == StudentProfile:
                return queryset.filter(assigned_counselor=user, school_id=user.school_id)
            if hasattr(queryset.model, 'student'):
                return queryset.filter(
                    student__assigned_counselor=user,
                    student__school_id=user.school_id,
                )
            return queryset
        if user.is_product_admin:
            return queryset
        if user.is_organization:
            if not user.school_id:
                return queryset.none()
            if queryset.model == StudentProfile:
                return queryset.filter(school_id=user.school_id)
            if hasattr(queryset.model, 'student'):
                return queryset.filter(student__school_id=user.school_id)
            return queryset.none()
        if queryset.model == StudentProfile:
            return queryset.filter(user=user)
        if hasattr(queryset.model, 'student'):
            return queryset.filter(student__user=user)
        return queryset.none()


class StudentProfileViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = StudentProfileSerializer
    queryset = StudentProfile.objects.select_related('user', 'assigned_counselor', 'school').order_by('user__first_name', 'user__last_name', 'id')

    def get_queryset(self):
        if self.request.user.role == User.Role.TEACHER:
            if not self.request.user.school_id:
                return self.queryset.none()
            return self.queryset.filter(school_id=self.request.user.school_id)
        return self.filter_for_user(self.queryset)

    def retrieve(self, request, *args, **kwargs):
        student = self.get_object()
        if request.user.is_product_admin:
            audit_product_action(actor=request.user, action='student_360.viewed', target=student)
        return Response(self.get_serializer(student).data)

    @action(detail=True, methods=['get'], url_path='data-visibility')
    def data_visibility(self, request, pk=None):
        if not (request.user.is_product_admin or request.user.is_organization):
            return Response({'detail': 'This view is available only to product admins and school accounts.'}, status=403)
        student = self.get_object()
        access_scope = 'global' if request.user.is_product_admin else 'own_school'
        audit_product_action(
            actor=request.user,
            action='student_visibility.viewed',
            target=student,
            metadata={'access_scope': access_scope, 'school': student.school_id},
        )
        context = {'request': request}
        return Response({
            'policy': {
                'version': 'school-student-visibility-v1',
                'access_scope': access_scope,
                'access_mode': 'read_only',
                'included': [
                    'identity_and_contact', 'academic_profile', 'progress_and_xp', 'task_metadata_and_status',
                    'roadmap_metadata_and_status', 'application_metadata_and_status', 'document_metadata_and_secure_file',
                    'essay_metadata_and_status', 'recommendation_metadata_and_status', 'portfolio_and_activities',
                    'meeting_schedule_and_status', 'program_usage',
                ],
                'excluded': [
                    'private_messages', 'message_moderation_reports', 'credentials_and_password_state',
                    'internal_counselor_notes', 'meeting_notes', 'application_portal_credentials',
                    'essay_draft_content_and_feedback', 'recommendation_files_and_private_notes',
                    'task_submission_content', 'roadmap_reflections', 'screen_time_detail', 'support_tickets',
                ],
            },
            'student': SchoolVisibilityStudentSerializer(student, context=context).data,
            'tasks': SchoolVisibilityTaskSerializer(student.tasks.select_related('assigned_by').all(), many=True, context=context).data,
            'roadmap': SchoolVisibilityRoadmapSerializer(student.roadmap_missions.all(), many=True, context=context).data,
            'applications': SchoolVisibilityApplicationSerializer(student.applications.select_related('university').all(), many=True, context=context).data,
            'documents': SchoolVisibilityDocumentSerializer(student.documents.all(), many=True, context=context).data,
            'essays': SchoolVisibilityEssaySerializer(student.essays.select_related('application__university').all(), many=True, context=context).data,
            'recommendations': SchoolVisibilityRecommendationSerializer(student.recommendations.all(), many=True, context=context).data,
            'achievements': SchoolVisibilityAchievementSerializer(student.achievements.all(), many=True, context=context).data,
            'researches': SchoolVisibilityResearchSerializer(student.researches.all(), many=True, context=context).data,
            'projects': SchoolVisibilityProjectSerializer(student.projects.all(), many=True, context=context).data,
            'internships': SchoolVisibilityInternshipSerializer(student.internships.all(), many=True, context=context).data,
            'activities': SchoolVisibilityActivitySerializer(student.activities.all(), many=True, context=context).data,
            'honors': SchoolVisibilityHonorSerializer(student.honors.all(), many=True, context=context).data,
            'meetings': SchoolVisibilityBookingSerializer(student.bookings.select_related('participant').all(), many=True, context=context).data,
            'program_usage': SchoolVisibilityProgramServiceSerializer(student.program_services.select_related('mentor').all(), many=True, context=context).data,
        })

    @action(detail=False, methods=['get'], url_path='assignment-candidates')
    def assignment_candidates(self, request):
        """Expose only the minimum student identity needed for a safe assignment picker."""
        user = request.user
        if user.role == User.Role.COUNSELOR:
            if not user.school_id:
                return Response({'detail': 'Your counselor account is not connected to a school.'}, status=400)
            candidates = self.queryset.filter(
                school_id=user.school_id,
                user__school_id=user.school_id,
                assigned_counselor__isnull=True,
            )
        elif user.is_product_admin:
            counselor_id = request.query_params.get('counselor')
            counselor = User.objects.filter(
                pk=counselor_id,
                role=User.Role.COUNSELOR,
                is_active=True,
                school__isnull=False,
            ).first()
            if not counselor:
                return Response({'counselor': ['Select an active counselor.']}, status=400)
            candidates = self.queryset.filter(
                school_id=counselor.school_id,
                user__school_id=counselor.school_id,
            ).exclude(
                assigned_counselor=counselor,
            )
        else:
            return Response({'detail': 'Only counselors and product admins can assign students.'}, status=403)

        return Response([
            {
                'id': student.id,
                'user_detail': {
                    'id': student.user_id,
                    'full_name': student.user.get_full_name() or student.user.username,
                    'email': student.user.email,
                },
                'grade': student.grade,
                'school': student.school_id,
                'school_name': student.school_name,
                'assigned_counselor': student.assigned_counselor_id,
                'counselor_name': (
                    student.assigned_counselor.get_full_name() or student.assigned_counselor.username
                    if student.assigned_counselor else None
                ),
            }
            for student in candidates
        ])

    @action(detail=False, methods=['post'], url_path='assign-counselor')
    def assign_counselor(self, request):
        user = request.user
        if not (user.role == User.Role.COUNSELOR or user.is_product_admin):
            return Response({'detail': 'Only counselors and product admins can assign students.'}, status=403)

        raw_student_ids = request.data.get('students')
        if not isinstance(raw_student_ids, list) or not raw_student_ids:
            return Response({'students': ['Select at least one student.']}, status=400)
        try:
            student_ids = list(dict.fromkeys(int(student_id) for student_id in raw_student_ids))
        except (TypeError, ValueError):
            return Response({'students': ['Student IDs must be integers.']}, status=400)

        if user.role == User.Role.COUNSELOR:
            counselor = user
            supplied_counselor = request.data.get('counselor')
            if supplied_counselor and str(supplied_counselor) != str(user.id):
                return Response({'counselor': ['Counselors can only connect students to themselves.']}, status=403)
        else:
            counselor = User.objects.filter(
                pk=request.data.get('counselor'),
                role=User.Role.COUNSELOR,
                is_active=True,
                school__isnull=False,
            ).first()
            if not counselor:
                return Response({'counselor': ['Select an active counselor.']}, status=400)

        if not counselor.school_id:
            return Response({'counselor': ['The counselor is not connected to a school.']}, status=400)

        with transaction.atomic():
            students = list(
                # Only the student row needs a write lock. Joining nullable
                # school/counselor relations here makes PostgreSQL reject the
                # SELECT FOR UPDATE (it cannot lock the nullable side of an
                # outer join). user is non-null and user.school_id is already
                # available without joining the school table.
                StudentProfile.objects.select_for_update()
                .select_related('user')
                .filter(pk__in=student_ids)
            )
            if len(students) != len(student_ids):
                return Response({'students': ['One or more students do not exist.']}, status=400)
            if any(
                student.school_id != counselor.school_id or student.user.school_id != counselor.school_id
                for student in students
            ):
                return Response({
                    'students': ['The counselor and every selected student must belong to the same school.']
                }, status=400)
            if user.role == User.Role.COUNSELOR and any(
                student.assigned_counselor_id is not None for student in students
            ):
                return Response({
                    'students': ['Counselors can connect only unassigned students from their own school.']
                }, status=409)

            reassigned_count = 0
            for student in students:
                if student.assigned_counselor_id and student.assigned_counselor_id != counselor.id:
                    reassigned_count += 1
                student.assigned_counselor = counselor
                student.save(update_fields=['assigned_counselor', 'updated_at'])
                ActivityLog.objects.create(
                    actor=user,
                    student=student,
                    action=f'Student assigned to counselor: {counselor.get_full_name() or counselor.username}',
                    metadata={'counselor': counselor.id, 'school': counselor.school_id},
                )
                if user.is_product_admin:
                    audit_product_action(
                        actor=user,
                        action='student.counselor_assigned',
                        target=student,
                        metadata={'counselor': counselor.id, 'school': counselor.school_id},
                    )

        return Response({
            'assigned_count': len(students),
            'reassigned_count': reassigned_count,
            'counselor': counselor.id,
            'school': counselor.school_id,
        })

    def perform_destroy(self, instance):
        student_user = instance.user
        ActivityLog.objects.create(
            actor=self.request.user,
            student=instance,
            action=f'Student profile deleted: {student_user.get_full_name() or student_user.username}',
        )
        # Deleting the user also removes the one-to-one profile and all related records.
        student_user.delete()

    @action(detail=True, methods=['post'], url_path='approve-level')
    def approve_level(self, request, pk=None):
        if not request.user.is_task_manager:
            return Response({'detail': 'Only a teacher or counselor can approve level changes.'}, status=403)
        with transaction.atomic():
            student = StudentProfile.objects.select_for_update().get(pk=self.get_object().pk)
            eligible_level = student.eligible_level
            if eligible_level <= student.level:
                return Response({'detail': 'This student has not reached the next XP threshold.'}, status=400)
            previous_level = student.level
            student.level = eligible_level
            student.save(update_fields=['level', 'updated_at'])
            LevelApproval.objects.create(
                student=student,
                from_level=previous_level,
                to_level=eligible_level,
                approved_by=request.user,
            )
            ActivityLog.objects.create(
                actor=request.user,
                student=student,
                action=f'Level approved: {previous_level} → {eligible_level}',
            )
        data = StudentProfileSerializer(student, context={'request': request}).data
        data['approved_from_level'] = previous_level
        return Response(data)

    @action(detail=True, methods=['get'], url_path='xp-history')
    def xp_history(self, request, pk=None):
        student = self.get_object()
        return Response({
            'xp_transactions': XPTransactionSerializer(
                student.xp_transactions.select_related('awarded_by').all()[:50],
                many=True,
            ).data,
            'level_approvals': LevelApprovalSerializer(
                student.level_approvals.select_related('approved_by').all()[:50],
                many=True,
            ).data,
        })

    @action(detail=False, methods=['post'], url_path='quick-create')
    def quick_create(self, request):
        if not (request.user.is_counselor_like or request.user.is_organization):
            return Response({'detail': 'Only counselors or school organizations can create students.'}, status=403)

        full_name = str(request.data.get('name') or request.data.get('full_name') or '').strip()
        email = str(request.data.get('email') or '').strip().lower()
        if not full_name:
            return Response({'name': ['This field is required.']}, status=400)
        if email and User.objects.filter(email=email).exists():
            return Response({'email': ['User with this email already exists.']}, status=400)
        password = str(request.data.get('password') or '')
        if not password:
            return Response({'password': ['Set a strong initial password for this student.']}, status=400)
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            return Response({'password': list(exc.messages)}, status=400)

        target_countries = str(
            request.data.get('countries') or request.data.get('target_countries') or ''
        ).strip()
        target_countries_max_length = StudentProfile._meta.get_field('target_countries').max_length
        if len(target_countries) > target_countries_max_length:
            return Response({
                'target_countries': [f'Use {target_countries_max_length} characters or fewer.'],
            }, status=400)

        parts = full_name.split()
        first_name = parts[0]
        last_name = ' '.join(parts[1:])
        base_username = slugify(email.split('@')[0] if email else full_name) or 'student'
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            counter += 1
            username = f'{base_username}{counter}'
        if not email:
            email = f'{username}@rbis.local'

        if request.user.is_organization:
            school = request.user.school
            if not school:
                return Response({'school': ['Your organization account is not connected to a school.']}, status=400)
        elif request.user.role == User.Role.COUNSELOR:
            school = request.user.school
            if not school or not school.is_active:
                return Response({'school': ['Your counselor account is not connected to an active school.']}, status=400)
            supplied_school = request.data.get('school')
            if supplied_school and str(supplied_school) != str(school.id):
                return Response({'school': ['Counselors can only add students to their own school.']}, status=400)
        else:
            school_id = request.data.get('school')
            if not school_id:
                return Response({'school': ['Select a school for this student.']}, status=400)
            school = School.objects.filter(id=school_id, is_active=True).first()
            if not school:
                return Response({'school': ['Selected school does not exist or is inactive.']}, status=400)

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=None,
                first_name=first_name,
                last_name=last_name,
                role=User.Role.STUDENT,
                phone=request.data.get('phone', ''),
                school=school,
            )
            user, _, _, _ = issue_temporary_credential(
                user=user,
                issued_by=request.user,
                raw_password=password,
                request=request,
            )
            student = StudentProfile.objects.create(
                user=user,
                assigned_counselor=(
                    request.user if request.user.role == User.Role.COUNSELOR else None
                ),
                school=school,
                school_name=school.name if school else request.data.get('school_name', 'Naseeb Edu'),
                grade=str(request.data.get('grade') or StudentProfile.Grade.GRADE_11).replace('-sinf', ''),
                gpa=request.data.get('gpa') or None,
                ielts_score=request.data.get('ielts') or request.data.get('ielts_score') or None,
                sat_score=request.data.get('sat') or request.data.get('sat_score') or None,
                target_major=request.data.get('major') or request.data.get('target_major') or '',
                target_countries=target_countries,
                budget_usd=request.data.get('budget_usd') or None,
                scholarship_needed=str(request.data.get('scholarship_needed', 'true')).lower() not in {'false', '0', 'no'},
                parent_contact=request.data.get('parent_contact', ''),
                notes=request.data.get('notes', ''),
            )
            ActivityLog.objects.create(actor=request.user, student=student, action=f'Student profile created: {full_name}')

        return Response(StudentProfileSerializer(student, context={'request': request}).data, status=201)


class SchoolViewSet(viewsets.ModelViewSet):
    serializer_class = SchoolSerializer
    permission_classes = [CounselorOrOwnerPermission]
    queryset = School.objects.annotate(students_count=Count('students')).order_by('name')

    def get_queryset(self):
        if self.request.user.is_product_admin:
            queryset = self.queryset
            search = self.request.query_params.get('search', '').strip()
            workspace_type = self.request.query_params.get('workspace_type')
            active = self.request.query_params.get('is_active')
            if search:
                queryset = queryset.filter(
                    Q(name__icontains=search) | Q(code__icontains=search)
                    | Q(contact_email__icontains=search)
                )
            if workspace_type:
                queryset = queryset.filter(workspace_type=workspace_type)
            if active in {'true', 'false'}:
                queryset = queryset.filter(is_active=active == 'true')
            return queryset
        if self.request.user.role == User.Role.COUNSELOR and self.request.user.school_id:
            return self.queryset.filter(id=self.request.user.school_id)
        if self.request.user.is_organization and self.request.user.school_id:
            return self.queryset.filter(id=self.request.user.school_id)
        return self.queryset.none()

    def create(self, request, *args, **kwargs):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can create schools.'}, status=403)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        school = serializer.save()
        audit_product_action(actor=self.request.user, action='school.created', target=school)

    def update(self, request, *args, **kwargs):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can edit schools.'}, status=403)
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        school = serializer.save()
        audit_product_action(actor=self.request.user, action='school.updated', target=school)

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can deactivate schools.'}, status=403)
        school = self.get_object()
        school.is_active = False
        school.save(update_fields=['is_active', 'updated_at'])
        audit_product_action(actor=request.user, action='school.deactivated', target=school)
        return Response(status=204)

    @action(detail=True, methods=['post'], url_path='create-account')
    def create_account(self, request, pk=None):
        school = self.get_object()
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can create organization accounts.'}, status=403)
        serializer = OrganizationAccountSerializer(
            data=request.data,
            context={'school': school, 'request': request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        audit_product_action(actor=request.user, action='organization_account.created', target=user, metadata={'school': school.pk})
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'school': school.id,
            'school_name': school.name,
        }, status=201)


class UniversityViewSet(viewsets.ModelViewSet):
    serializer_class = UniversitySerializer
    queryset = University.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        return [CounselorOrOwnerPermission()]


COLLEGE_RESEARCH_QUESTIONS = {
    'gpa': {'label': 'Current GPA', 'type': 'number', 'placeholder': 'Example: 4.90', 'step': '0.01', 'min': 0, 'max': 5},
    'sat_score': {'label': 'SAT score', 'type': 'number', 'placeholder': 'Example: 1490', 'min': 400, 'max': 1600},
    'ielts_score': {'label': 'IELTS score', 'type': 'number', 'placeholder': 'Example: 7.0', 'step': '0.5', 'min': 0, 'max': 9},
    'target_major': {'label': 'Target major', 'type': 'text', 'placeholder': 'Example: Computer Science'},
    'target_countries': {'label': 'Target countries', 'type': 'text', 'placeholder': 'Example: USA, Canada, Singapore'},
    'budget_usd': {'label': 'Annual budget (USD)', 'type': 'number', 'placeholder': 'Example: 20000', 'min': 0, 'max': 500000},
}


def build_college_research(profile):
    required_fields = tuple(COLLEGE_RESEARCH_QUESTIONS)
    missing_fields = [field for field in required_fields if getattr(profile, field) in (None, '')]
    profile_counts = {
        'achievements': profile.achievements.count(),
        'honors': profile.honors.count(),
        'researches': profile.researches.count(),
        'projects': profile.projects.count(),
        'internships': profile.internships.count(),
        'activities': profile.activities.count(),
    }
    snapshot = {
        'gpa': profile.gpa,
        'sat_score': profile.sat_score,
        'ielts_score': profile.ielts_score,
        'target_major': profile.target_major,
        'target_countries': profile.target_countries,
        'budget_usd': profile.budget_usd,
        'scholarship_needed': profile.scholarship_needed,
        'evidence': profile_counts,
    }
    if missing_fields:
        return {
            'ready': False,
            'missing_fields': missing_fields,
            'questions': [dict(field=field, **COLLEGE_RESEARCH_QUESTIONS[field]) for field in missing_fields],
            'profile_snapshot': snapshot,
            'recommendations': [],
        }

    sat = int(profile.sat_score)
    ielts = float(profile.ielts_score)
    gpa = float(profile.gpa)
    budget = int(profile.budget_usd)
    target_countries = [value.strip().lower() for value in profile.target_countries.split(',') if value.strip()]
    target_major = profile.target_major.strip().lower()
    evidence_total = sum(min(value, 2) for value in profile_counts.values())
    profile_strength_score = min(10, evidence_total * 2)
    recommendations = []

    for university in University.objects.all():
        reasons = []
        gaps = []

        gpa_scale = 5 if gpa > 4 else 4
        gpa_score = round(min(15, (gpa / gpa_scale) * 15))
        academic_score = gpa_score
        if university.sat_min:
            if sat >= (university.sat_max or university.sat_min):
                sat_score = 25
                reasons.append(f'SAT {sat} meets or exceeds the catalog range')
            elif sat >= university.sat_min:
                sat_score = 22
                reasons.append(f'SAT {sat} fits the {university.sat_min}–{university.sat_max or university.sat_min} catalog range')
            elif sat >= max(400, university.sat_min - 80):
                sat_score = 12
                gaps.append(f'SAT is {university.sat_min - sat} points below the catalog minimum')
            else:
                sat_score = 4
                gaps.append(f'Raise SAT toward at least {university.sat_min}')
        else:
            sat_score = 20
            reasons.append('No strict SAT minimum is listed in the catalog')
        academic_score += sat_score

        if ielts >= 7:
            academic_score += 8
            reasons.append(f'IELTS {ielts:g} is a strong language score')
        elif ielts >= 6.5:
            academic_score += 6
            reasons.append(f'IELTS {ielts:g} is suitable for many programs')
        else:
            academic_score += 3
            gaps.append('Verify the IELTS requirement on the official program page')

        preference_score = 0
        if university.country.lower() in target_countries:
            preference_score += 12
            reasons.append(f'{university.country} is one of your target countries')
        else:
            preference_score += 3
        majors = [value.strip().lower() for value in university.popular_majors.split(',') if value.strip()]
        if target_major and any(target_major in major or major in target_major for major in majors):
            preference_score += 10
            reasons.append(f'{profile.target_major} matches one of the university’s popular majors')
        else:
            preference_score += 4
            gaps.append('Check the exact program requirements for your selected major')

        financial_score = 0
        if university.net_price_usd:
            if university.net_price_usd <= budget:
                financial_score += 12
                reasons.append('Estimated net price is within your budget')
            elif university.net_price_usd <= budget * 1.5:
                financial_score += 7
                gaps.append('Net price is above budget but may be covered with aid')
            else:
                financial_score += 2
                gaps.append('Estimated net price is significantly above your budget')
        else:
            financial_score += 5
            gaps.append('Net price is not available in the catalog')
        if profile.scholarship_needed:
            if university.offers_international_aid or university.offers_merit_aid or university.offers_need_based_aid:
                financial_score += 8
                reasons.append('A suitable type of financial aid is available')
            else:
                financial_score += 1
                gaps.append('International or merit aid is not listed in the catalog')
        else:
            financial_score += 8

        total_score = min(100, academic_score + preference_score + financial_score + profile_strength_score)
        acceptance_rate = float(university.acceptance_rate) if university.acceptance_rate is not None else None
        if (acceptance_rate is not None and acceptance_rate < 15) or (university.sat_min and sat < university.sat_min):
            admission_band = 'reach'
        elif acceptance_rate is not None and acceptance_rate >= 45 and (not university.sat_min or sat >= university.sat_min):
            admission_band = 'strong_option'
        else:
            admission_band = 'target'
        match_label = 'Strong match' if total_score >= 80 else 'Good match' if total_score >= 65 else 'Developing match'
        recommendations.append({
            'university': UniversitySerializer(university).data,
            'match_score': total_score,
            'match_label': match_label,
            'admission_band': admission_band,
            'score_breakdown': {
                'academic': academic_score,
                'preferences': preference_score,
                'financial': financial_score,
                'profile_strength': profile_strength_score,
            },
            'reasons': reasons[:5],
            'gaps': gaps[:4],
        })

    recommendations.sort(key=lambda item: (-item['match_score'], item['university']['ranking'] or 999999))
    return {
        'ready': True,
        'missing_fields': [],
        'questions': [],
        'profile_snapshot': snapshot,
        'recommendations': recommendations,
        'methodology': 'Academic fit, preferences, affordability, aid and verified profile evidence.',
        'generated_at': timezone.now(),
    }


class CollegeResearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_profile(self, request):
        if request.user.role != User.Role.STUDENT or not hasattr(request.user, 'student_profile'):
            return None
        return request.user.student_profile

    def get(self, request):
        profile = self.get_profile(request)
        if not profile:
            return Response({'detail': 'College research is available to student accounts only.'}, status=403)
        return Response(build_college_research(profile))

    def post(self, request):
        profile = self.get_profile(request)
        if not profile:
            return Response({'detail': 'College research is available to student accounts only.'}, status=403)
        serializer = CollegeResearchProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update_profile(profile)
        return Response(build_college_research(profile))


class ScholarshipViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ScholarshipSerializer
    queryset = Scholarship.objects.select_related('university').filter(is_active=True)
    permission_classes = [permissions.IsAuthenticated]


class OpportunityProgramViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OpportunityProgramSerializer
    queryset = OpportunityProgram.objects.filter(is_active=True)
    permission_classes = [permissions.IsAuthenticated]


class ApplicationViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    queryset = Application.objects.select_related('student__user', 'student__assigned_counselor', 'university').all()

    def get_queryset(self):
        queryset = self.filter_for_user(self.queryset)
        status = self.request.query_params.get('status')
        student = self.request.query_params.get('student')
        if status:
            queryset = queryset.filter(status=status)
        if student:
            queryset = queryset.filter(student_id=student)
        return queryset

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


class StaffControlledWorkPermission(permissions.BasePermission):
    """Managers assign scoped work; students may create personal zero-XP tasks."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        user = request.user
        if user.is_task_manager:
            return user.role != User.Role.TEACHER or bool(user.school_id)
        if user.is_organization:
            return view.basename in {'tasks', 'roadmap-missions'} and request.method in permissions.SAFE_METHODS
        if user.role == User.Role.STUDENT:
            if request.method in permissions.SAFE_METHODS:
                return True
            if view.action in {'create', 'destroy'}:
                return view.basename == 'tasks'
            return view.action in {'update', 'partial_update'}
        return False

    def has_object_permission(self, request, view, obj):
        user = request.user
        student = obj.student
        if user.is_counselor_like:
            return True
        if user.role == User.Role.TEACHER:
            return bool(user.school_id and student.school_id == user.school_id)
        if user.is_organization:
            return bool(
                request.method in permissions.SAFE_METHODS
                and user.school_id
                and student.school_id == user.school_id
            )
        if student.user_id != user.id:
            return False
        if request.method in permissions.SAFE_METHODS or view.action in {'update', 'partial_update'}:
            return True
        return view.action == 'destroy' and obj.is_self_assigned


class StaffControlledWorkMixin:
    permission_classes = [StaffControlledWorkPermission]

    def filter_work_for_user(self, queryset):
        user = self.request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return queryset
        if user.role == User.Role.COUNSELOR:
            return queryset.filter(student__assigned_counselor=user)
        if user.is_product_admin:
            return queryset
        if user.role in {User.Role.TEACHER, User.Role.ORGANIZATION}:
            if not user.school_id:
                return queryset.none()
            return queryset.filter(student__school_id=user.school_id)
        if user.role == User.Role.STUDENT:
            return queryset.filter(student__user=user)
        return queryset.none()


class TaskViewSet(StaffControlledWorkMixin, viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    queryset = Task.objects.select_related('student__user', 'assigned_by', 'student__assigned_counselor').all()

    def get_queryset(self):
        queryset = self.filter_work_for_user(self.queryset)
        status = self.request.query_params.get('status')
        student = self.request.query_params.get('student')
        priority = self.request.query_params.get('priority')
        if status:
            queryset = queryset.filter(status=status)
        if student:
            queryset = queryset.filter(student_id=student)
        if priority:
            queryset = queryset.filter(priority=priority)
        return queryset

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
            task = Task.objects.select_for_update().select_related('student').get(pk=scoped_task.pk)
            if task.status not in {Task.Status.SUBMITTED, Task.Status.APPROVED}:
                return Response({'detail': 'The student must submit the task before approval.'}, status=400)
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
            ActivityLog.objects.get_or_create(
                actor=request.user,
                student=task.student,
                action=(
                    f'Task approved: {task.title} (+{xp_amount} XP)'
                    if xp_amount
                    else f'Self-task approved: {task.title} (no XP)'
                ),
            )
        task.student.refresh_from_db()
        data = TaskSerializer(task, context={'request': request}).data
        data['xp_awarded'] = xp_amount if xp_created else 0
        data['student_leveling'] = StudentProfileSerializer(task.student, context={'request': request}).data
        return Response(data)


class DocumentViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    queryset = Document.objects.select_related('student__user', 'student__assigned_counselor').all()

    def get_queryset(self):
        queryset = self.filter_for_user(self.queryset)
        status = self.request.query_params.get('status')
        student = self.request.query_params.get('student')
        if status:
            queryset = queryset.filter(status=status)
        if student:
            queryset = queryset.filter(student_id=student)
        return queryset

    @action(detail=True, methods=['get'], url_path='file')
    def file(self, request, pk=None):
        document = self.get_object()
        if not document.file:
            raise Http404('This document has no uploaded file.')
        try:
            stream = document.file.open('rb')
        except (FileNotFoundError, OSError):
            raise Http404('The uploaded file is unavailable. Contact support.')

        file_name = document.original_file_name or Path(document.file.name).name
        extension = Path(file_name).suffix.lower()
        inline_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.txt', '.csv'}
        force_download = request.query_params.get('download') == '1' or extension not in inline_extensions
        content_type = document.file_content_type or mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
        response = FileResponse(
            stream,
            as_attachment=force_download,
            filename=file_name,
            content_type=content_type,
        )
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    def perform_destroy(self, instance):
        file_name = instance.file.name if instance.file else ''
        storage = instance.file.storage if file_name else None
        super().perform_destroy(instance)
        if file_name:
            transaction.on_commit(lambda: storage.delete(file_name))


class PrivateEvidenceViewSetMixin:
    @action(detail=True, methods=['get'], url_path='proof-file')
    def proof_file(self, request, pk=None):
        record = self.get_object()
        if not record.proof_file:
            raise Http404('This record has no proof file.')
        try:
            stream = record.proof_file.open('rb')
        except (FileNotFoundError, OSError):
            raise Http404('The proof file is unavailable. Contact support.')

        file_name = record.proof_file_name or Path(record.proof_file.name).name
        extension = Path(file_name).suffix.lower()
        inline_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.txt', '.csv'}
        force_download = request.query_params.get('download') == '1' or extension not in inline_extensions
        content_type = (
            record.proof_file_content_type
            or mimetypes.guess_type(file_name)[0]
            or 'application/octet-stream'
        )
        response = FileResponse(
            stream,
            as_attachment=force_download,
            filename=file_name,
            content_type=content_type,
        )
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    def perform_destroy(self, instance):
        file_name = instance.proof_file.name if instance.proof_file else ''
        storage = instance.proof_file.storage if file_name else None
        super().perform_destroy(instance)
        if file_name:
            transaction.on_commit(lambda: storage.delete(file_name))


class AchievementViewSet(PrivateEvidenceViewSetMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = AchievementSerializer
    queryset = Achievement.objects.select_related('student__user', 'student__assigned_counselor').all()

    def get_queryset(self):
        return self.filter_for_user(self.queryset)

class ResearchViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ResearchSerializer
    queryset = Research.objects.select_related('student__user', 'student__school').all()

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class ProjectViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    queryset = Project.objects.select_related('student__user', 'student__school').all()

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class InternshipViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = InternshipSerializer
    queryset = Internship.objects.select_related('student__user', 'student__school').all()

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class ActivityViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ActivitySerializer
    queryset = Activity.objects.select_related('student__user', 'student__school').all()

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class HonorViewSet(PrivateEvidenceViewSetMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = HonorSerializer
    queryset = Honor.objects.select_related('student__user', 'student__school').all()

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class RecommendationLetterViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = RecommendationLetterSerializer
    queryset = RecommendationLetter.objects.select_related('student__user', 'student__school').all()

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class EssayViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = EssaySerializer
    queryset = Essay.objects.select_related('student__user', 'student__assigned_counselor', 'application__university').all()

    def get_queryset(self):
        queryset = self.filter_for_user(self.queryset)
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def perform_create(self, serializer):
        essay = serializer.save()
        EssayRevision.objects.create(
            essay=essay,
            version=essay.version,
            prompt=essay.prompt,
            content=essay.content,
            status=essay.status,
            counselor_comment=essay.counselor_comment,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        tracked_fields = {'prompt', 'content', 'status', 'counselor_comment'}
        should_version = bool(tracked_fields.intersection(serializer.validated_data))
        if should_version:
            essay = serializer.save(version=serializer.instance.version + 1)
            EssayRevision.objects.create(
                essay=essay,
                version=essay.version,
                prompt=essay.prompt,
                content=essay.content,
                status=essay.status,
                counselor_comment=essay.counselor_comment,
                created_by=self.request.user,
            )
        else:
            serializer.save()


class MeetingNoteViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = MeetingNoteSerializer
    queryset = MeetingNote.objects.select_related('student__user', 'student__assigned_counselor', 'counselor').all()

    def get_queryset(self):
        return self.filter_for_user(self.queryset)

    def perform_create(self, serializer):
        serializer.save(counselor=self.request.user)


class NotificationViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.select_related('student__user', 'student__assigned_counselor').all()

    def get_queryset(self):
        queryset = self.filter_for_user(self.queryset)
        unread = self.request.query_params.get('unread')
        if unread in ['1', 'true', 'True']:
            queryset = queryset.filter(is_read=False)
        return queryset

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=['is_read', 'updated_at'])
        return Response(NotificationSerializer(notification, context={'request': request}).data)


class SupportTicketViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SupportTicketSerializer
    permission_classes = [SupportTicketPermission]
    queryset = SupportTicket.objects.select_related('requester', 'responded_by').all()

    def get_queryset(self):
        user = self.request.user
        if SupportTicketPermission.is_product_admin(user):
            return self.queryset
        return self.queryset.filter(requester=user)

    def perform_create(self, serializer):
        serializer.save(
            requester=self.request.user,
            status=SupportTicket.Status.OPEN,
            admin_response='',
        )

    def perform_update(self, serializer):
        previous_response = serializer.instance.admin_response
        ticket = serializer.save()
        if ticket.admin_response and ticket.admin_response != previous_response:
            ticket.responded_by = self.request.user
            ticket.responded_at = timezone.now()
            ticket.requester_viewed_at = None
            ticket.save(update_fields=[
                'responded_by', 'responded_at', 'requester_viewed_at', 'updated_at',
            ])

    @action(detail=True, methods=['post'], url_path='mark-viewed')
    def mark_viewed(self, request, pk=None):
        ticket = self.get_object()
        if ticket.requester_id != request.user.id:
            return Response(
                {'detail': 'Only the ticket requester can mark a response as viewed.'},
                status=403,
            )
        if ticket.responded_at:
            ticket.requester_viewed_at = timezone.now()
            ticket.save(update_fields=['requester_viewed_at', 'updated_at'])
        return Response(self.get_serializer(ticket).data)


class ActivityLogViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ActivityLogSerializer
    queryset = ActivityLog.objects.select_related('actor', 'student__user', 'student__assigned_counselor').all()

    def get_queryset(self):
        return self.filter_for_user(self.queryset)


class StudentPortalPermission(permissions.BasePermission):
    """Keep the Crimson-inspired portal modules isolated to signed-in students."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.STUDENT
            and hasattr(request.user, 'student_profile')
        )

    def has_object_permission(self, request, view, obj):
        profile = request.user.student_profile
        owner = getattr(obj, 'student', None)
        if isinstance(obj, CommunityPost):
            return (
                request.method in permissions.SAFE_METHODS
                or view.action == 'like'
                or obj.author_id == profile.id
            )
        if owner is not None:
            return getattr(owner, 'id', None) == profile.id
        return request.method in permissions.SAFE_METHODS


class StudentCollaborationPermission(permissions.BasePermission):
    """Allow students and their assigned counselors to share legacy direct messages."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_organization:
            return False
        if request.user.is_counselor_like:
            return not (view.basename == 'bookings' and view.action == 'create')
        return bool(
            request.user.role == User.Role.STUDENT
            and hasattr(request.user, 'student_profile')
        )

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_product_admin:
            return True
        if user.role == User.Role.COUNSELOR:
            if isinstance(obj, Booking):
                return obj.counselor_id == user.id
            if isinstance(obj, StudentMessage):
                return user.id in {obj.sender_id, obj.recipient_id}
            return False
        return getattr(obj, 'student_id', None) == user.student_profile.id


class BookingPermission(permissions.BasePermission):
    """Keep meeting requests scoped to the student and the selected staff participant."""

    STUDENT_ACTIONS = {'list', 'retrieve', 'create', 'participants'}
    STAFF_ACTIONS = {'list', 'retrieve', 'approve', 'reject', 'complete'}

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.STUDENT and hasattr(user, 'student_profile'):
            return view.action in self.STUDENT_ACTIONS
        if user.role in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}:
            return view.action in self.STAFF_ACTIONS
        return False

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.STUDENT and hasattr(user, 'student_profile'):
            return obj.student_id == user.student_profile.id and view.action in {'retrieve'}
        return obj.participant_id == user.id and view.action in {'retrieve', 'approve', 'reject', 'complete'}


class StudentPortalOwnedViewSet(viewsets.ModelViewSet):
    permission_classes = [StudentPortalPermission]

    def get_queryset(self):
        return self.queryset.filter(student=self.request.user.student_profile)


class RoadmapMissionViewSet(StaffControlledWorkMixin, viewsets.ModelViewSet):
    serializer_class = RoadmapMissionSerializer
    queryset = RoadmapMission.objects.select_related('student__user', 'assigned_by').all()

    def get_queryset(self):
        queryset = self.filter_work_for_user(self.queryset)
        student = self.request.query_params.get('student')
        status_value = self.request.query_params.get('status')
        if student:
            queryset = queryset.filter(student_id=student)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    def perform_create(self, serializer):
        serializer.save(assigned_by=self.request.user)

    @action(detail=False, methods=['post'], url_path='extend-level-one')
    def extend_level_one(self, request):
        if not request.user.is_task_manager:
            return Response({'detail': 'Only a teacher or counselor can extend Level 1.'}, status=403)
        student_id = request.data.get('student')
        if not student_id:
            return Response({'student': ['Select a student.']}, status=400)

        students = StudentProfile.objects.select_related('user', 'assigned_counselor')
        if request.user.role == User.Role.COUNSELOR:
            students = students.filter(assigned_counselor=request.user)
        elif request.user.role == User.Role.TEACHER:
            students = students.filter(school_id=request.user.school_id)
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
            mission = RoadmapMission.objects.select_for_update().select_related('student').get(pk=scoped_mission.pk)
            if mission.status not in {RoadmapMission.Status.SUBMITTED, RoadmapMission.Status.COMPLETED}:
                return Response({'detail': 'The student must submit the mission before approval.'}, status=400)
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
            ActivityLog.objects.get_or_create(
                actor=request.user,
                student=mission.student,
                action=f'Roadmap mission approved: {mission.title} (+{ROADMAP_APPROVAL_XP} XP)',
            )
        mission.student.refresh_from_db()
        data = RoadmapMissionSerializer(mission, context={'request': request}).data
        data['xp_awarded'] = ROADMAP_APPROVAL_XP if xp_created else 0
        data['student_leveling'] = StudentProfileSerializer(mission.student, context={'request': request}).data
        return Response(data)


class ProductAdminPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_product_admin)


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
            counselor = self.request.query_params.get('counselor')
            school = self.request.query_params.get('school')
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
        if request.user.is_product_admin:
            response = super().create(request, *args, **kwargs)
            roadmap = CounselorRoadmap.objects.get(pk=response.data['id'])
            audit_product_action(actor=request.user, action='counselor_roadmap.assigned', target=roadmap)
            return response
        if request.user.role != User.Role.COUNSELOR:
            return Response({'detail': 'Only a counselor or product admin can start a counselor roadmap.'}, status=403)

        template_id = request.data.get('template')
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

    @action(detail=True, methods=['post'], url_path='submit-mission')
    def submit_mission(self, request, pk=None):
        roadmap = self.get_object()
        if request.user.role != User.Role.COUNSELOR or roadmap.counselor_id != request.user.id:
            return Response({'detail': 'Only the assigned counselor can submit this mission.'}, status=403)
        mission_id = request.data.get('mission')
        note = str(request.data.get('counselor_note', '')).strip()
        if not note:
            return Response({'counselor_note': ['Add a completion note before submitting.']}, status=400)
        with transaction.atomic():
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
            mission = CounselorRoadmapMission.objects.select_for_update().filter(
                pk=request.data.get('mission'), roadmap=roadmap
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


class CommunityPostViewSet(viewsets.ModelViewSet):
    serializer_class = CommunityPostSerializer
    permission_classes = [StudentPortalPermission]
    queryset = CommunityPost.objects.select_related('author__user').prefetch_related('liked_by').all()

    def perform_create(self, serializer):
        serializer.save(author=self.request.user.student_profile)

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        post = self.get_object()
        profile = request.user.student_profile
        if post.liked_by.filter(id=profile.id).exists():
            post.liked_by.remove(profile)
        else:
            post.liked_by.add(profile)
        return Response(CommunityPostSerializer(post, context={'request': request}).data)


def booking_participants_for(profile):
    if not profile:
        return User.objects.none()
    allowed = Q(id=profile.assigned_counselor_id)
    if profile.school_id:
        allowed |= Q(
            school_id=profile.school_id,
            role__in=[User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION],
        )
    return User.objects.filter(
        allowed,
        is_active=True,
    ).exclude(role=User.Role.STUDENT).distinct().order_by('role', 'first_name', 'last_name', 'username')


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [BookingPermission]
    queryset = Booking.objects.select_related('student__user', 'participant', 'participant__school').all()

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return self.queryset
        if user.role in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}:
            return self.queryset.filter(participant=user)
        if user.role == User.Role.STUDENT and hasattr(user, 'student_profile'):
            return self.queryset.filter(student=user.student_profile)
        return self.queryset.none()

    def perform_create(self, serializer):
        profile = self.request.user.student_profile
        serializer.save(student=profile, status=Booking.Status.PENDING)

    @action(detail=False, methods=['get'])
    def participants(self, request):
        profile = request.user.student_profile
        return Response(UserSerializer(
            booking_participants_for(profile),
            many=True,
            context={'request': request},
        ).data)

    def _transition(self, booking, target_status, allowed_from):
        if booking.status == target_status:
            return Response(self.get_serializer(booking).data)
        if booking.status not in allowed_from:
            return Response(
                {'detail': f'A {booking.get_status_display().lower()} meeting cannot be changed to {target_status}.'},
                status=400,
            )
        booking.status = target_status
        booking.save(update_fields=['status', 'updated_at'])
        participant_name = (
            booking.participant.get_full_name() or booking.participant.username
            if booking.participant else 'your meeting participant'
        )
        meeting_time = timezone.localtime(booking.starts_at).strftime('%d %b %Y, %H:%M')
        Notification.objects.create(
            student=booking.student,
            title=f'Meeting {booking.get_status_display().lower()}',
            message=f'Your meeting with {participant_name} on {meeting_time} is now {booking.get_status_display().lower()}.',
        )
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._transition(self.get_object(), Booking.Status.APPROVED, {Booking.Status.PENDING})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._transition(self.get_object(), Booking.Status.REJECTED, {Booking.Status.PENDING})

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        return self._transition(self.get_object(), Booking.Status.COMPLETED, {Booking.Status.APPROVED})


class StudentMessageViewSet(viewsets.ModelViewSet):
    serializer_class = StudentMessageSerializer
    permission_classes = [StudentCollaborationPermission]
    queryset = StudentMessage.objects.select_related('student__user', 'sender', 'recipient').all()

    def get_queryset(self):
        user = self.request.user
        if user.is_product_admin:
            return self.queryset
        if user.role == User.Role.COUNSELOR:
            return self.queryset.filter(Q(sender=user) | Q(recipient=user))
        return self.queryset.filter(student=user.student_profile)

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == User.Role.COUNSELOR or user.is_counselor_like:
            student_id = self.request.data.get('student')
            profile = StudentProfile.objects.filter(id=student_id, assigned_counselor=user).first()
            if not profile:
                raise drf_serializers.ValidationError({'student': 'Select one of your assigned students.'})
            serializer.save(student=profile, sender=user, recipient=profile.user)
            return
        profile = user.student_profile
        if not profile.assigned_counselor:
            raise drf_serializers.ValidationError({'recipient': 'A counselor has not been assigned yet.'})
        serializer.save(student=profile, sender=user, recipient=profile.assigned_counselor)

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        message = self.get_object()
        if message.recipient_id == request.user.id:
            message.is_read = True
            message.save(update_fields=['is_read', 'updated_at'])
        return Response(StudentMessageSerializer(message, context={'request': request}).data)


def messaging_contacts_for(user):
    queryset = User.objects.filter(is_active=True).exclude(id=user.id)
    if user.is_superuser or user.role == User.Role.ADMIN:
        return queryset.order_by('first_name', 'last_name', 'username')
    if user.role == User.Role.COUNSELOR:
        assigned_students = Q(student_profile__assigned_counselor=user)
        assigned_school_ids = StudentProfile.objects.filter(
            assigned_counselor=user,
            school__isnull=False,
        ).values_list('school_id', flat=True)
        school_staff = Q(
            school_id__in=assigned_school_ids,
            role__in=[User.Role.ORGANIZATION, User.Role.TEACHER, User.Role.COUNSELOR],
        )
        return queryset.filter(assigned_students | school_staff).distinct().order_by('first_name', 'last_name', 'username')
    profile = user.student_profile if user.role == User.Role.STUDENT and hasattr(user, 'student_profile') else None
    effective_school_id = profile.school_id if profile and profile.school_id else user.school_id
    if effective_school_id:
        same_school = Q(school_id=effective_school_id)
    else:
        same_school = Q(pk__in=[])
    if user.role in {User.Role.ORGANIZATION, User.Role.TEACHER} and user.school_id:
        counselor_ids = StudentProfile.objects.filter(
            school_id=user.school_id,
            assigned_counselor__isnull=False,
        ).values_list('assigned_counselor_id', flat=True)
        return queryset.filter(same_school | Q(id__in=counselor_ids)).distinct().order_by('first_name', 'last_name', 'username')
    if profile:
        counselor_id = profile.assigned_counselor_id
        own_school_staff = same_school & Q(
            role__in=[User.Role.ORGANIZATION, User.Role.TEACHER, User.Role.COUNSELOR],
        )
        return queryset.filter(own_school_staff | Q(id=counselor_id)).distinct().order_by('first_name', 'last_name', 'username')
    return queryset.filter(same_school).order_by('first_name', 'last_name', 'username')


def discoverable_channels_for(user):
    queryset = MessageChannel.objects.select_related('school', 'created_by').prefetch_related(
        'memberships__user',
    )
    if user.is_product_admin:
        return queryset
    public_scope = Q(is_public=True, school__isnull=True)
    if user.school_id:
        public_scope |= Q(is_public=True, school_id=user.school_id)
    if user.role == User.Role.COUNSELOR:
        public_scope |= Q(is_public=True, school__students__assigned_counselor=user)
    return queryset.filter(Q(memberships__user=user) | public_scope).distinct()


def moderatable_channels_for(user):
    queryset = MessageChannel.objects.select_related('school', 'created_by')
    if user.is_superuser or user.role == User.Role.ADMIN:
        return queryset
    if user.role not in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}:
        return queryset.none()
    moderator_memberships = Q(
        memberships__user=user,
        memberships__role__in=[ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR],
    )
    return queryset.filter(moderator_memberships).distinct()


def channel_membership_role(channel, user):
    membership = channel.memberships.filter(user=user).first()
    return membership.role if membership else None


class MessageChannelPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_product_admin:
            return True
        role = channel_membership_role(obj, user)
        if request.method in permissions.SAFE_METHODS:
            return bool(role or obj.is_public)
        if view.action in {'join'}:
            return obj.is_public
        if view.action in {'mark_read', 'leave'}:
            return bool(role)
        return role in {ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR}


class MessageChannelViewSet(viewsets.ModelViewSet):
    serializer_class = MessageChannelSerializer
    permission_classes = [MessageChannelPermission]
    queryset = MessageChannel.objects.all()

    def get_queryset(self):
        queryset = discoverable_channels_for(self.request.user)
        kind = self.request.query_params.get('kind')
        search = self.request.query_params.get('search')
        if kind:
            queryset = queryset.filter(kind=kind)
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        kind = serializer.validated_data['kind']
        if kind == MessageChannel.Kind.DIRECT:
            raise drf_serializers.ValidationError({'kind': 'Use the direct action to open a direct conversation.'})
        if kind in {MessageChannel.Kind.GROUP, MessageChannel.Kind.COMMUNITY} and not (
            user.is_task_manager or user.is_organization
        ):
            raise drf_serializers.ValidationError({'kind': 'Only school staff can create Group or Community channels.'})
        if kind in {MessageChannel.Kind.GROUP, MessageChannel.Kind.COMMUNITY, MessageChannel.Kind.DISCUSSION} and not serializer.validated_data.get('name'):
            raise drf_serializers.ValidationError({'name': 'A channel name or discussion title is required.'})

        school = serializer.validated_data.get('school')
        if not user.is_counselor_like:
            school = user.school
        channel = serializer.save(
            created_by=user,
            school=school,
            is_public=kind in {MessageChannel.Kind.COMMUNITY, MessageChannel.Kind.DISCUSSION},
        )
        ChannelMembership.objects.create(channel=channel, user=user, role=ChannelMembership.Role.OWNER)

        requested_members = self.request.data.get('members', [])
        allowed_ids = set(messaging_contacts_for(user).filter(id__in=requested_members).values_list('id', flat=True))
        ChannelMembership.objects.bulk_create([
            ChannelMembership(channel=channel, user_id=user_id)
            for user_id in allowed_ids
        ], ignore_conflicts=True)

    @action(detail=False, methods=['get'])
    def contacts(self, request):
        return Response(UserSerializer(messaging_contacts_for(request.user), many=True, context={'request': request}).data)

    @action(detail=False, methods=['get'])
    def overview(self, request):
        channels = discoverable_channels_for(request.user)
        counts = {kind: 0 for kind, _ in MessageChannel.Kind.choices}
        counts.update(dict(channels.values('kind').annotate(total=Count('id')).values_list('kind', 'total')))
        memberships = ChannelMembership.objects.filter(
            user=request.user,
            channel__in=channels,
        ).annotate(
            unread=Count(
                'channel__messages',
                filter=(
                    Q(channel__messages__deleted_at__isnull=True)
                    & ~Q(channel__messages__sender=request.user)
                    & (
                        Q(last_read_at__isnull=True)
                        | Q(channel__messages__created_at__gt=F('last_read_at'))
                    )
                ),
            ),
        )
        contacts = messaging_contacts_for(request.user)
        can_moderate = bool(request.user.is_task_manager or request.user.is_organization)
        pending_reports = 0
        if can_moderate:
            pending_reports = MessageReport.objects.filter(
                message__channel__in=moderatable_channels_for(request.user),
                status__in=[MessageReport.Status.PENDING, MessageReport.Status.REVIEWING],
            ).count()
        return Response({
            'channel_counts': counts,
            'unread_total': sum(membership.unread for membership in memberships),
            'contacts_total': contacts.count(),
            'students_total': contacts.filter(role=User.Role.STUDENT).count(),
            'staff_total': contacts.exclude(role=User.Role.STUDENT).count(),
            'pending_reports': pending_reports,
            'can_moderate': can_moderate,
        })

    @action(detail=False, methods=['post'])
    def direct(self, request):
        target_id = request.data.get('user')
        target = messaging_contacts_for(request.user).filter(id=target_id).first()
        if not target:
            return Response({'detail': 'This user is not available as a direct-message contact.'}, status=403)
        first_id, second_id = sorted([request.user.id, target.id])
        direct_key = f'{first_id}:{second_id}'
        with transaction.atomic():
            channel, created = MessageChannel.objects.get_or_create(
                direct_key=direct_key,
                defaults={
                    'kind': MessageChannel.Kind.DIRECT,
                    'created_by': request.user,
                    'school': request.user.school or target.school,
                    'is_public': False,
                },
            )
            if created:
                channel.school = (
                    request.user.student_profile.school
                    if request.user.role == User.Role.STUDENT and hasattr(request.user, 'student_profile')
                    else request.user.school or target.school
                )
                channel.save(update_fields=['school', 'updated_at'])
            ChannelMembership.objects.bulk_create([
                ChannelMembership(channel=channel, user=request.user, role=ChannelMembership.Role.OWNER),
                ChannelMembership(channel=channel, user=target, role=ChannelMembership.Role.MEMBER),
            ], ignore_conflicts=True)
        return Response(MessageChannelSerializer(channel, context={'request': request}).data, status=201 if created else 200)

    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        channel = self.get_object()
        if not channel.is_public:
            return Response({'detail': 'This channel is invite-only.'}, status=403)
        membership, created = ChannelMembership.objects.get_or_create(channel=channel, user=request.user)
        return Response(ChannelMembershipSerializer(membership, context={'request': request}).data, status=201 if created else 200)

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        channel = self.get_object()
        if channel.kind == MessageChannel.Kind.DIRECT:
            return Response({'detail': 'Direct conversations cannot be left.'}, status=400)
        membership = channel.memberships.filter(user=request.user).first()
        if membership and membership.role == ChannelMembership.Role.OWNER and channel.memberships.filter(role=ChannelMembership.Role.OWNER).count() == 1:
            return Response({'detail': 'Assign another owner before leaving.'}, status=400)
        if membership:
            membership.delete()
        return Response(status=204)

    @action(detail=True, methods=['get', 'post', 'delete'])
    def members(self, request, pk=None):
        channel = self.get_object()
        membership_role = channel_membership_role(channel, request.user)
        can_manage = request.user.is_counselor_like or membership_role in {
            ChannelMembership.Role.OWNER,
            ChannelMembership.Role.MODERATOR,
        }
        if request.method == 'GET':
            if not (membership_role or request.user.is_counselor_like):
                return Response({'detail': 'Join the channel before viewing its members.'}, status=403)
            return Response(ChannelMembershipSerializer(
                channel.memberships.select_related('user').all(),
                many=True,
                context={'request': request},
            ).data)
        if channel.kind == MessageChannel.Kind.DIRECT:
            return Response({'detail': 'Direct conversation participants cannot be changed.'}, status=400)
        if not can_manage:
            return Response({'detail': 'Only channel moderators can manage members.'}, status=403)
        if request.method == 'DELETE':
            target_membership = channel.memberships.filter(user_id=request.data.get('user')).first()
            if not target_membership:
                return Response(status=204)
            if target_membership.role == ChannelMembership.Role.OWNER:
                return Response({'detail': 'Channel owners cannot be removed.'}, status=400)
            target_membership.delete()
            return Response(status=204)
        target = messaging_contacts_for(request.user).filter(id=request.data.get('user')).first()
        if not target:
            return Response({'detail': 'This user is not available for this channel.'}, status=403)
        requested_role = request.data.get('role', ChannelMembership.Role.MEMBER)
        if requested_role not in {ChannelMembership.Role.MEMBER, ChannelMembership.Role.MODERATOR}:
            return Response({'detail': 'Members can only be added as member or moderator.'}, status=400)
        membership, created = ChannelMembership.objects.get_or_create(
            channel=channel,
            user=target,
            defaults={'role': requested_role},
        )
        if not created and membership.role != ChannelMembership.Role.OWNER and membership.role != requested_role:
            membership.role = requested_role
            membership.save(update_fields=['role'])
        return Response(ChannelMembershipSerializer(membership, context={'request': request}).data, status=201 if created else 200)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        channel = self.get_object()
        membership = channel.memberships.filter(user=request.user).first()
        if not membership:
            return Response({'detail': 'Join the channel before marking it read.'}, status=403)
        membership.last_read_at = timezone.now()
        membership.save(update_fields=['last_read_at'])
        return Response({'status': 'read', 'channel': channel.id})


class ChannelMessagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


class ChannelMessagePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_product_admin:
            return True
        role = channel_membership_role(obj.channel, user)
        if request.method in permissions.SAFE_METHODS:
            return bool(role or obj.channel.is_public)
        if view.action == 'accept':
            return bool(user.is_task_manager or role in {ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR})
        if view.action in {'update', 'partial_update', 'destroy'}:
            return bool(obj.sender_id == user.id or role in {ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR})
        return bool(role)


class ChannelMessageViewSet(viewsets.ModelViewSet):
    serializer_class = ChannelMessageSerializer
    permission_classes = [ChannelMessagePermission]
    pagination_class = ChannelMessagePagination
    queryset = ChannelMessage.objects.select_related('channel', 'sender', 'parent').prefetch_related('replies').all()

    def get_queryset(self):
        channel_id = self.request.query_params.get('channel')
        if not channel_id:
            if getattr(self, 'detail', False):
                return self.queryset.filter(channel__in=discoverable_channels_for(self.request.user))
            return self.queryset.none()
        accessible_channels = discoverable_channels_for(self.request.user).filter(id=channel_id)
        if not accessible_channels.exists():
            return self.queryset.none()
        queryset = self.queryset.filter(channel_id=channel_id).order_by('-created_at', '-id')
        parent = self.request.query_params.get('parent')
        if parent:
            queryset = queryset.filter(parent_id=parent)
        return queryset

    def perform_create(self, serializer):
        message = serializer.save(sender=self.request.user)
        MessageChannel.objects.filter(id=message.channel_id).update(
            last_message_at=message.created_at,
            updated_at=timezone.now(),
        )

    def perform_update(self, serializer):
        serializer.save(is_edited=True)

    def perform_destroy(self, instance):
        instance.body = ''
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['body', 'deleted_at', 'updated_at'])

    @action(detail=True, methods=['post'])
    def report(self, request, pk=None):
        message = self.get_object()
        if message.deleted_at:
            return Response({'detail': 'Deleted messages cannot be reported.'}, status=400)
        if message.sender_id == request.user.id:
            return Response({'detail': 'You cannot report your own message.'}, status=400)
        if not message.channel.memberships.filter(user=request.user).exists():
            return Response({'detail': 'Join the channel before reporting a message.'}, status=403)
        reason = request.data.get('reason')
        valid_reasons = {choice for choice, _ in MessageReport.Reason.choices}
        if reason not in valid_reasons:
            return Response({'reason': ['Select a valid report reason.']}, status=400)
        details = str(request.data.get('details', '')).strip()
        if len(details) > 2000:
            return Response({'details': ['Report details cannot exceed 2,000 characters.']}, status=400)
        report, created = MessageReport.objects.get_or_create(
            message=message,
            reporter=request.user,
            defaults={'reason': reason, 'details': details},
        )
        if not created:
            return Response({'detail': 'You have already reported this message.'}, status=400)
        return Response({
            'id': report.id,
            'message': message.id,
            'reason': report.reason,
            'status': report.status,
            'created_at': report.created_at,
        }, status=201)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        message = self.get_object()
        if message.channel.kind != MessageChannel.Kind.DISCUSSION:
            return Response({'detail': 'Accepted answers are only available in Discussions.'}, status=400)
        if not message.parent_id:
            return Response({'detail': 'Only a reply can be accepted as an answer.'}, status=400)
        role = channel_membership_role(message.channel, request.user)
        if not (request.user.is_task_manager or message.channel.created_by_id == request.user.id or role in {ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR}):
            return Response({'detail': 'Only the discussion owner or moderator can accept an answer.'}, status=403)
        with transaction.atomic():
            message.channel.messages.filter(is_accepted_answer=True).update(is_accepted_answer=False)
            message.is_accepted_answer = True
            message.save(update_fields=['is_accepted_answer', 'updated_at'])
        return Response(ChannelMessageSerializer(message, context={'request': request}).data)


class MessageReportPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_product_admin:
            return True
        if request.user.role not in {User.Role.COUNSELOR, User.Role.TEACHER, User.Role.ORGANIZATION}:
            return False
        return MessageChannel.objects.filter(
            memberships__user=request.user,
            memberships__role__in=[ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR],
        ).exists()


class MessageReportViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MessageReportSerializer
    permission_classes = [MessageReportPermission]
    queryset = MessageReport.objects.select_related(
        'message__channel', 'message__sender', 'reporter', 'reviewed_by',
    ).all()

    def get_queryset(self):
        queryset = self.queryset.filter(
            message__channel__in=moderatable_channels_for(self.request.user),
        )
        status_value = self.request.query_params.get('status')
        if status_value:
            valid_statuses = {choice for choice, _ in MessageReport.Status.choices}
            if status_value not in valid_statuses:
                return queryset.none()
            queryset = queryset.filter(status=status_value)
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(message__body__icontains=search)
                | Q(message__channel__name__icontains=search)
                | Q(details__icontains=search)
            )
        return queryset

    def _ensure_independent_review(self, request, report):
        if report.message.sender_id == request.user.id:
            return Response({'detail': 'Another moderator must review a report about your message.'}, status=403)
        return None

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        report = self.get_object()
        blocked = self._ensure_independent_review(request, report)
        if blocked:
            return blocked
        if report.status != MessageReport.Status.PENDING:
            return Response({'detail': 'Only pending reports can be moved to review.'}, status=400)
        report.status = MessageReport.Status.REVIEWING
        report.reviewed_by = request.user
        report.reviewed_at = timezone.now()
        report.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
        return Response(self.get_serializer(report).data)

    @action(detail=True, methods=['post'])
    def dismiss(self, request, pk=None):
        report = self.get_object()
        blocked = self._ensure_independent_review(request, report)
        if blocked:
            return blocked
        if report.status in {MessageReport.Status.RESOLVED, MessageReport.Status.DISMISSED}:
            return Response({'detail': 'This report has already been closed.'}, status=400)
        report.status = MessageReport.Status.DISMISSED
        report.action = MessageReport.Action.NONE
        report.moderator_note = str(request.data.get('moderator_note', '')).strip()[:2000]
        report.reviewed_by = request.user
        report.reviewed_at = timezone.now()
        report.save(update_fields=[
            'status', 'action', 'moderator_note', 'reviewed_by', 'reviewed_at', 'updated_at',
        ])
        return Response(self.get_serializer(report).data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        scoped_report = self.get_object()
        blocked = self._ensure_independent_review(request, scoped_report)
        if blocked:
            return blocked
        selected_action = request.data.get('action', MessageReport.Action.NONE)
        valid_actions = {choice for choice, _ in MessageReport.Action.choices}
        if selected_action not in valid_actions:
            return Response({'action': ['Select a valid moderation action.']}, status=400)
        if scoped_report.status in {MessageReport.Status.RESOLVED, MessageReport.Status.DISMISSED}:
            return Response({'detail': 'This report has already been closed.'}, status=400)
        moderator_note = str(request.data.get('moderator_note', '')).strip()[:2000]
        now = timezone.now()
        with transaction.atomic():
            report = MessageReport.objects.select_for_update().select_related(
                'message__channel', 'message__sender', 'reporter', 'reviewed_by',
            ).get(pk=scoped_report.pk)
            message = report.message
            if selected_action == MessageReport.Action.CONTENT_REMOVED and not message.deleted_at:
                message.body = ''
                message.deleted_at = now
                message.save(update_fields=['body', 'deleted_at', 'updated_at'])
            elif selected_action in {MessageReport.Action.MUTED_24H, MessageReport.Action.MUTED_7D}:
                membership = ChannelMembership.objects.select_for_update().filter(
                    channel=message.channel,
                    user_id=message.sender_id,
                ).first()
                if not membership:
                    return Response({'detail': 'The message author is no longer a channel member.'}, status=400)
                duration = timedelta(hours=24) if selected_action == MessageReport.Action.MUTED_24H else timedelta(days=7)
                mute_until = now + duration
                if not membership.muted_until or membership.muted_until < mute_until:
                    membership.muted_until = mute_until
                    membership.save(update_fields=['muted_until'])
            MessageReport.objects.filter(
                message=message,
                status__in=[MessageReport.Status.PENDING, MessageReport.Status.REVIEWING],
            ).update(
                status=MessageReport.Status.RESOLVED,
                action=selected_action,
                moderator_note=moderator_note,
                reviewed_by=request.user,
                reviewed_at=now,
                updated_at=now,
            )
        report.refresh_from_db()
        return Response(self.get_serializer(report).data)


class ProgramServicePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return user.role in {
                User.Role.ADMIN, User.Role.COUNSELOR, User.Role.ORGANIZATION, User.Role.STUDENT,
            } or user.is_superuser
        return user.is_superuser or user.role in {User.Role.ADMIN, User.Role.COUNSELOR}

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.COUNSELOR:
            return bool(
                user.school_id
                and obj.student.school_id == user.school_id
                and obj.student.assigned_counselor_id == user.id
            )
        if user.role == User.Role.ORGANIZATION:
            return request.method in permissions.SAFE_METHODS and obj.student.school_id == user.school_id
        return request.method in permissions.SAFE_METHODS and obj.student.user_id == user.id


class ProgramServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ProgramServiceSerializer
    permission_classes = [ProgramServicePermission]
    queryset = ProgramService.objects.select_related('student__user', 'student__school', 'mentor').all()

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return self.queryset
        if user.role == User.Role.COUNSELOR:
            if not user.school_id:
                return self.queryset.none()
            return self.queryset.filter(
                student__assigned_counselor=user,
                student__school_id=user.school_id,
            )
        if user.role == User.Role.ORGANIZATION:
            if not user.school_id:
                return self.queryset.none()
            return self.queryset.filter(student__school_id=user.school_id)
        if user.role == User.Role.STUDENT:
            return self.queryset.filter(student__user=user)
        return self.queryset.none()


class ScreenTimeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ScreenTimeDailySerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = ScreenTimeDaily.objects.select_related('user').all()
    http_method_names = ['get', 'post', 'head', 'options']

    def student_profiles_for_scope(self):
        user = self.request.user
        profiles = StudentProfile.objects.select_related('user', 'school')
        if user.is_superuser or user.role == User.Role.ADMIN:
            return profiles
        if user.role == User.Role.COUNSELOR:
            if not user.school_id:
                return profiles.none()
            return profiles.filter(assigned_counselor=user, school_id=user.school_id)
        if user.role in {User.Role.TEACHER, User.Role.ORGANIZATION}:
            if not user.school_id:
                return profiles.none()
            return profiles.filter(school_id=user.school_id)
        return profiles.none()

    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset
        if user.is_superuser or user.role == User.Role.ADMIN:
            return queryset
        if user.role == User.Role.COUNSELOR:
            student_user_ids = self.student_profiles_for_scope().values_list('user_id', flat=True)
            return queryset.filter(Q(user=user) | Q(user_id__in=student_user_ids))
        if user.role in {User.Role.TEACHER, User.Role.ORGANIZATION}:
            student_user_ids = self.student_profiles_for_scope().values_list('user_id', flat=True)
            return queryset.filter(Q(user=user) | Q(user_id__in=student_user_ids))
        return queryset.filter(user=user)

    @staticmethod
    def parse_entries(raw_entries):
        if not isinstance(raw_entries, list) or not raw_entries or len(raw_entries) > 50:
            raise drf_serializers.ValidationError({'entries': 'Send between 1 and 50 screen-time entries.'})
        today = timezone.localdate()
        oldest_allowed = today - timedelta(days=7)
        aggregated = {}
        for entry in raw_entries:
            if not isinstance(entry, dict):
                raise drf_serializers.ValidationError({'entries': 'Every entry must be an object.'})
            page = str(entry.get('page') or '').strip().lower()
            if not page or len(page) > 80 or not all(character.isalnum() or character in {'_', '-'} for character in page):
                raise drf_serializers.ValidationError({'page': 'Use a valid application page key.'})
            try:
                seconds = int(entry.get('seconds'))
            except (TypeError, ValueError):
                raise drf_serializers.ValidationError({'seconds': 'Active seconds must be an integer.'})
            if seconds < 1 or seconds > 300:
                raise drf_serializers.ValidationError({'seconds': 'Each entry must contain 1–300 active seconds.'})
            try:
                tracked_date = date.fromisoformat(str(entry.get('date') or today.isoformat()))
            except ValueError:
                raise drf_serializers.ValidationError({'date': 'Use YYYY-MM-DD.'})
            if tracked_date > today or tracked_date < oldest_allowed:
                raise drf_serializers.ValidationError({'date': 'Offline screen time can only be submitted within 7 days.'})
            key = (tracked_date, page)
            aggregated[key] = aggregated.get(key, 0) + seconds
        if any(seconds > 600 for seconds in aggregated.values()):
            raise drf_serializers.ValidationError({'seconds': 'A single batch cannot exceed 10 minutes per page.'})
        return aggregated

    @action(detail=False, methods=['post'])
    def track(self, request):
        entries = self.parse_entries(request.data.get('entries'))
        tracked_seconds = 0
        with transaction.atomic():
            for (tracked_date, page), seconds in entries.items():
                record, created = ScreenTimeDaily.objects.get_or_create(
                    user=request.user,
                    date=tracked_date,
                    page=page,
                    defaults={'active_seconds': seconds, 'sessions': 1},
                )
                if not created:
                    ScreenTimeDaily.objects.filter(pk=record.pk).update(
                        active_seconds=F('active_seconds') + seconds,
                        sessions=F('sessions') + 1,
                        last_seen_at=timezone.now(),
                    )
                tracked_seconds += seconds
        return Response({'tracked_seconds': tracked_seconds, 'entries': len(entries)})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        try:
            days = min(31, max(1, int(request.query_params.get('days', 7))))
        except (TypeError, ValueError):
            days = 7
        today = timezone.localdate()
        start_date = today - timedelta(days=days - 1)
        own = ScreenTimeDaily.objects.filter(user=request.user, date__gte=start_date)
        daily_rows = list(
            own.values('date').annotate(seconds=Sum('active_seconds')).order_by('date')
        )
        page_rows = list(
            own.values('page').annotate(seconds=Sum('active_seconds')).order_by('-seconds', 'page')
        )
        profiles = list(self.student_profiles_for_scope())
        user_ids = [profile.user_id for profile in profiles]
        period_totals = {
            row['user_id']: row['seconds'] or 0
            for row in ScreenTimeDaily.objects.filter(
                user_id__in=user_ids, date__gte=start_date
            ).values('user_id').annotate(seconds=Sum('active_seconds'))
        }
        today_totals = {
            row['user_id']: row['seconds'] or 0
            for row in ScreenTimeDaily.objects.filter(
                user_id__in=user_ids, date=today
            ).values('user_id').annotate(seconds=Sum('active_seconds'))
        }
        team = [
            {
                'student': profile.id,
                'user': profile.user_id,
                'name': profile.user.get_full_name() or profile.user.username,
                'school': profile.school.name if profile.school else profile.school_name,
                'today_seconds': today_totals.get(profile.user_id, 0),
                'period_seconds': period_totals.get(profile.user_id, 0),
            }
            for profile in profiles
        ]
        team.sort(key=lambda item: (-item['today_seconds'], item['name']))
        return Response({
            'timezone': settings.TIME_ZONE,
            'retention_days': getattr(settings, 'SCREEN_TIME_RETENTION_DAYS', 365),
            'period_days': days,
            'today': today,
            'own': {
                'today_seconds': own.filter(date=today).aggregate(total=Sum('active_seconds'))['total'] or 0,
                'period_seconds': own.aggregate(total=Sum('active_seconds'))['total'] or 0,
                'daily': daily_rows,
                'pages': page_rows,
            },
            'team': team,
            'privacy': 'Only aggregate active seconds by user, day, and application page are stored.',
        })


class ParentLinkPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.COUNSELOR:
            return view.action in {'list', 'retrieve', 'invite', 'revoke'}
        if user.role == User.Role.PARENT:
            return view.action in {'list', 'retrieve', 'accept', 'revoke'}
        return False

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.COUNSELOR:
            return bool(
                user.school_id
                and obj.student.school_id == user.school_id
                and obj.student.assigned_counselor_id == user.id
            )
        return user.role == User.Role.PARENT and obj.parent_id == user.id


class ParentStudentLinkViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ParentStudentLinkSerializer
    permission_classes = [ParentLinkPermission]
    queryset = ParentStudentLink.objects.select_related(
        'parent', 'student__user', 'student__school', 'student__assigned_counselor', 'invited_by'
    ).all()
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return self.queryset
        if user.role == User.Role.COUNSELOR:
            if not user.school_id:
                return self.queryset.none()
            return self.queryset.filter(
                student__assigned_counselor=user,
                student__school_id=user.school_id,
            )
        if user.role == User.Role.PARENT:
            return self.queryset.filter(parent=user)
        return self.queryset.none()

    @staticmethod
    def unique_parent_username(email):
        base = slugify(email.split('@')[0])[:130] or 'parent'
        username = base
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f'{base[:145 - len(str(suffix))]}-{suffix}'
        return username

    @action(detail=False, methods=['post'])
    def invite(self, request):
        if not (
            request.user.is_superuser
            or request.user.role in {User.Role.ADMIN, User.Role.COUNSELOR}
        ):
            return Response({'detail': 'Only an admin or assigned counselor can invite a parent.'}, status=403)
        serializer = ParentInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        student = values['student']
        if request.user.role == User.Role.COUNSELOR and not (
            request.user.school_id
            and student.school_id == request.user.school_id
            and student.assigned_counselor_id == request.user.id
        ):
            return Response({'student': ['Select one of your assigned students.']}, status=403)

        email = values['email'].lower()
        with transaction.atomic():
            parent = User.objects.filter(email__iexact=email).first()
            created_account = False
            if parent and parent.role != User.Role.PARENT:
                return Response({'email': ['This email belongs to a non-parent account.']}, status=400)
            if not parent:
                password = values.get('password')
                if not password:
                    return Response({'password': ['Set a temporary password for the new parent account.']}, status=400)
                parent = User.objects.create_user(
                    username=self.unique_parent_username(email),
                    email=email,
                    password=password,
                    first_name=values.get('first_name', ''),
                    last_name=values.get('last_name', ''),
                    role=User.Role.PARENT,
                    school=student.school,
                )
                created_account = True
            link, created_link = ParentStudentLink.objects.get_or_create(
                parent=parent,
                student=student,
                defaults={
                    'relationship': values['relationship'],
                    'can_view_applications': values['can_view_applications'],
                    'can_view_documents': values['can_view_documents'],
                    'can_view_meetings': values['can_view_meetings'],
                    'invited_by': request.user,
                },
            )
            if not created_link and link.status == ParentStudentLink.Status.ACTIVE:
                return Response({'detail': 'This parent is already connected to the student.'}, status=409)
            if not created_link:
                link.relationship = values['relationship']
                link.status = ParentStudentLink.Status.PENDING
                link.can_view_applications = values['can_view_applications']
                link.can_view_documents = values['can_view_documents']
                link.can_view_meetings = values['can_view_meetings']
                link.invited_by = request.user
                link.consented_at = None
                link.revoked_at = None
                link.save()
        return Response({
            'created_account': created_account,
            'username': parent.username,
            'link': ParentStudentLinkSerializer(link, context={'request': request}).data,
        }, status=201 if created_link else 200)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        link = self.get_object()
        if request.user.role != User.Role.PARENT or link.parent_id != request.user.id:
            return Response({'detail': 'Only the invited parent can accept this link.'}, status=403)
        if link.status != ParentStudentLink.Status.PENDING:
            return Response({'detail': 'Only a pending invitation can be accepted.'}, status=409)
        link.status = ParentStudentLink.Status.ACTIVE
        link.consented_at = timezone.now()
        link.revoked_at = None
        link.save(update_fields=['status', 'consented_at', 'revoked_at', 'updated_at'])
        return Response(self.get_serializer(link).data)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        link = self.get_object()
        link.status = ParentStudentLink.Status.REVOKED
        link.revoked_at = timezone.now()
        link.save(update_fields=['status', 'revoked_at', 'updated_at'])
        return Response(self.get_serializer(link).data)


class ParentPortalView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.user.role != User.Role.PARENT:
            return Response({'detail': 'This workspace is only available to parent accounts.'}, status=403)
        links = ParentStudentLink.objects.filter(parent=request.user).select_related(
            'student__user', 'student__school', 'student__assigned_counselor', 'invited_by'
        )
        pending = links.filter(status=ParentStudentLink.Status.PENDING)
        children = []
        for link in links.filter(status=ParentStudentLink.Status.ACTIVE):
            student = link.student
            tasks = student.tasks.all()
            applications = student.applications.select_related('university').all() if link.can_view_applications else []
            documents = student.documents.all() if link.can_view_documents else []
            meetings = student.bookings.select_related('participant').all() if link.can_view_meetings else []
            children.append({
                'link_id': link.id,
                'relationship': link.relationship,
                'permissions': {
                    'applications': link.can_view_applications,
                    'documents': link.can_view_documents,
                    'meetings': link.can_view_meetings,
                },
                'profile': {
                    'id': student.id,
                    'name': student.user.get_full_name() or student.user.username,
                    'school': student.school.name if student.school else student.school_name,
                    'grade': student.grade,
                    'counselor_name': (
                        student.assigned_counselor.get_full_name() or student.assigned_counselor.username
                        if student.assigned_counselor else None
                    ),
                    'level': student.level,
                    'xp_total': student.xp_total,
                    'next_level_xp': student.next_level_xp,
                    'gpa': student.gpa,
                    'ielts_score': student.ielts_score,
                    'sat_score': student.sat_score,
                    'target_major': student.target_major,
                    'target_countries': student.target_countries,
                    'task_progress_percent': student.task_progress_percent,
                    'roadmap_progress_percent': student.roadmap_progress_percent,
                    'journey_progress_percent': student.journey_progress_percent,
                    'is_at_risk': student.is_at_risk,
                },
                'tasks': [{
                    'id': item.id,
                    'title': item.title,
                    'due_date': item.due_date,
                    'priority': item.priority,
                    'status': item.status,
                    'is_overdue': item.is_overdue,
                    'is_self_assigned': item.is_self_assigned,
                } for item in tasks],
                'applications': [{
                    'id': item.id,
                    'university': item.university.name,
                    'country': item.university.country,
                    'program': item.program,
                    'tier': item.tier,
                    'status': item.status,
                    'deadline': item.deadline,
                    'scholarship_deadline': item.scholarship_deadline,
                } for item in applications],
                'documents': [{
                    'id': item.id,
                    'title': item.title,
                    'document_type': item.document_type,
                    'status': item.status,
                    'updated_at': item.updated_at,
                } for item in documents],
                'meetings': [{
                    'id': item.id,
                    'topic': item.topic,
                    'starts_at': item.starts_at,
                    'duration_minutes': item.duration_minutes,
                    'status': item.status,
                    'participant_name': (
                        item.participant.get_full_name() or item.participant.username
                        if item.participant else None
                    ),
                    'participant_role': item.participant.role if item.participant else None,
                } for item in meetings],
            })
        return Response({
            'children': children,
            'pending_invitations': ParentStudentLinkSerializer(pending, many=True).data,
            'privacy': {
                'hidden': ['private essays', 'messages', 'counselor notes', 'task responses', 'document files'],
                'read_only': True,
            },
        })


class ResourceLibraryItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ResourceLibraryItemSerializer
    permission_classes = [StudentPortalPermission]
    queryset = ResourceLibraryItem.objects.filter(is_active=True)


class StoreItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StoreItemSerializer
    permission_classes = [StudentPortalPermission]
    queryset = StoreItem.objects.filter(is_active=True)


class StudentTeamView(APIView):
    permission_classes = [StudentPortalPermission]

    def get(self, request):
        profile = request.user.student_profile
        team = []
        if profile.assigned_counselor:
            counselor = profile.assigned_counselor
            team.append({
                'id': counselor.id,
                'name': counselor.get_full_name() or counselor.username,
                'role': counselor.position or 'Education counselor',
                'email': counselor.email,
                'phone': counselor.phone,
                'kind': 'counselor',
            })
        if profile.school:
            organization_users = profile.school.users.filter(role=User.Role.ORGANIZATION).order_by('first_name', 'id')
            for member in organization_users:
                team.append({
                    'id': member.id,
                    'name': member.get_full_name() or member.username,
                    'role': member.position or f'{profile.school.name} coordinator',
                    'email': member.email,
                    'phone': member.phone,
                    'kind': 'school',
                })
        return Response(team)


class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        responses=inline_serializer(
            name='DashboardStats',
            fields={
                'students_total': drf_serializers.IntegerField(),
                'average_progress': drf_serializers.IntegerField(required=False),
                'average_task_progress': drf_serializers.IntegerField(required=False),
                'average_roadmap_progress': drf_serializers.IntegerField(required=False),
                'average_journey_progress': drf_serializers.IntegerField(required=False),
                'students_at_risk': drf_serializers.IntegerField(required=False),
                'tasks_total': drf_serializers.IntegerField(required=False),
                'tasks_late': drf_serializers.IntegerField(required=False),
                'tasks_due_week': drf_serializers.IntegerField(required=False),
                'applications_total': drf_serializers.IntegerField(required=False),
                'applications_submitted': drf_serializers.IntegerField(required=False),
                'documents_pending_review': drf_serializers.IntegerField(required=False),
                'essays_need_revision': drf_serializers.IntegerField(required=False),
                'application_by_status': drf_serializers.ListField(required=False),
                'task_by_status': drf_serializers.ListField(required=False),
            },
        )
    )
    def get(self, request):
        user = request.user
        students = StudentProfile.objects.select_related('user', 'assigned_counselor')
        if user.is_organization:
            students = students.filter(school_id=user.school_id) if user.school_id else students.none()
        elif user.role == User.Role.TEACHER:
            students = students.filter(school_id=user.school_id) if user.school_id else students.none()
        elif user.role == User.Role.COUNSELOR:
            students = students.filter(assigned_counselor=user)
        elif not user.is_counselor_like:
            students = students.filter(user=user)

        progress_values = [student.progress_percent for student in students]
        task_progress_values = [student.task_progress_percent for student in students]
        roadmap_progress_values = [student.roadmap_progress_percent for student in students]
        journey_progress_values = [student.journey_progress_percent for student in students]
        progress_summary = {
            'average_progress': round(sum(progress_values) / len(progress_values)) if progress_values else 0,
            'average_task_progress': round(sum(task_progress_values) / len(task_progress_values)) if task_progress_values else 0,
            'average_roadmap_progress': round(sum(roadmap_progress_values) / len(roadmap_progress_values)) if roadmap_progress_values else 0,
            'average_journey_progress': round(sum(journey_progress_values) / len(journey_progress_values)) if journey_progress_values else 0,
            'students_at_risk': sum(1 for student in students if student.is_at_risk),
        }

        if user.is_organization:
            return Response({
                'students_total': students.count(),
                **progress_summary,
            })

        tasks = Task.objects.filter(student__in=students)
        applications = Application.objects.filter(student__in=students)
        documents = Document.objects.filter(student__in=students)
        essays = Essay.objects.filter(student__in=students)
        today = timezone.localdate()

        if user.role == User.Role.TEACHER:
            return Response({
                'students_total': students.count(),
                **progress_summary,
                'tasks_total': tasks.count(),
                'tasks_late': tasks.exclude(status=Task.Status.APPROVED).filter(due_date__lt=today).count(),
                'tasks_due_week': tasks.exclude(status=Task.Status.APPROVED).filter(
                    due_date__range=[today, today + timedelta(days=7)],
                ).count(),
                'task_by_status': list(tasks.values('status').annotate(count=Count('id')).order_by('status')),
            })

        data = {
            'students_total': students.count(),
            **progress_summary,
            'tasks_total': tasks.count(),
            'tasks_late': tasks.exclude(status=Task.Status.APPROVED).filter(due_date__lt=today).count(),
            'tasks_due_week': tasks.exclude(status=Task.Status.APPROVED).filter(due_date__range=[today, today + timedelta(days=7)]).count(),
            'applications_total': applications.count(),
            'applications_submitted': applications.filter(status__in=[Application.Status.SUBMITTED, Application.Status.ACCEPTED]).count(),
            'documents_pending_review': documents.filter(status__in=[Document.Status.UPLOADED, Document.Status.REVIEWING]).count(),
            'essays_need_revision': essays.filter(status=Essay.Status.NEEDS_REVISION).count(),
            'application_by_status': list(applications.values('status').annotate(count=Count('id')).order_by('status')),
            'task_by_status': list(tasks.values('status').annotate(count=Count('id')).order_by('status')),
        }
        return Response(data)


class ChallengeAttemptPermission(permissions.BasePermission):
    """Deliberately narrower than CounselorOrOwnerPermission.

    A personality profile is not the same kind of record as a task list. The
    shared permission lets a school-account holder read anything with a student
    FK, which here would hand an administrator every student's trait scores --
    the class-ranked-by-conscientiousness list this product must never produce.

    So: a student reads and writes their own attempts; their ASSIGNED counselor
    reads them; nobody else, including other counselors at the same school and
    including teachers. Nobody but the student may create one, and no one at all
    may edit or delete one -- the record belongs to the student and is not
    something staff can quietly correct.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if view.action in {'update', 'partial_update', 'destroy'}:
            return False
        if view.action == 'create':
            return user.role == User.Role.STUDENT
        return user.role == User.Role.STUDENT or user.is_counselor_like

    def has_object_permission(self, request, view, obj):
        if request.method not in permissions.SAFE_METHODS:
            return False
        user = request.user
        if obj.student.user_id == user.id:
            return True
        if user.role == User.Role.ADMIN or user.is_superuser:
            return True
        return user.is_counselor_like and obj.student.assigned_counselor_id == user.id


class ChallengeAttemptViewSet(viewsets.ModelViewSet):
    serializer_class = ChallengeAttemptSerializer
    permission_classes = [ChallengeAttemptPermission]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        queryset = ChallengeAttempt.objects.select_related('student__user')
        if user.role == User.Role.STUDENT:
            return queryset.filter(student__user=user)
        if user.role == User.Role.ADMIN or user.is_superuser:
            pass
        elif user.is_counselor_like:
            queryset = queryset.filter(student__assigned_counselor=user)
        else:
            return queryset.none()
        student = self.request.query_params.get('student')
        return queryset.filter(student_id=student) if student else queryset

    def perform_create(self, serializer):
        serializer.save(student=self.request.user.student_profile)
