from datetime import timedelta
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.text import slugify
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers
from drf_spectacular.utils import extend_schema, inline_serializer

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
from .serializers import (
    AchievementSerializer,
    ActivitySerializer,
    ActivityLogSerializer,
    ApplicationSerializer,
    BookingSerializer,
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
    ProgramServiceSerializer,
    ProjectSerializer,
    RecommendationLetterSerializer,
    ResearchSerializer,
    ResourceLibraryItemSerializer,
    RoadmapMissionSerializer,
    SchoolSerializer,
    ScholarshipSerializer,
    StoreItemSerializer,
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


class CounselorOrOwnerPermission(permissions.BasePermission):
    organization_read_resources = {
        'tasks', 'applications', 'documents', 'essays', 'achievements',
        'meetings', 'researches', 'projects', 'internships', 'activities',
        'honors', 'recommendations', 'notifications', 'activity-logs',
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


class ScopedQuerysetMixin:
    permission_classes = [CounselorOrOwnerPermission]

    def filter_for_user(self, queryset):
        user = self.request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return queryset
        if user.role == User.Role.COUNSELOR:
            if queryset.model == StudentProfile:
                return queryset.filter(assigned_counselor=user)
            if hasattr(queryset.model, 'student'):
                return queryset.filter(student__assigned_counselor=user)
            return queryset
        if user.is_staff:
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
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=User.Role.STUDENT,
                phone=request.data.get('phone', ''),
                school=school,
            )
            student = StudentProfile.objects.create(
                user=user,
                assigned_counselor=request.user if request.user.is_counselor_like else None,
                school=school,
                school_name=school.name if school else request.data.get('school_name', 'Naseeb Edu'),
                grade=str(request.data.get('grade') or StudentProfile.Grade.GRADE_11).replace('-sinf', ''),
                gpa=request.data.get('gpa') or None,
                ielts_score=request.data.get('ielts') or request.data.get('ielts_score') or None,
                sat_score=request.data.get('sat') or request.data.get('sat_score') or None,
                target_major=request.data.get('major') or request.data.get('target_major') or '',
                target_countries=request.data.get('countries') or request.data.get('target_countries') or '',
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
        if self.request.user.is_counselor_like:
            return self.queryset
        if self.request.user.is_organization and self.request.user.school_id:
            return self.queryset.filter(id=self.request.user.school_id)
        return self.queryset.none()

    @action(detail=True, methods=['post'], url_path='create-account')
    def create_account(self, request, pk=None):
        if not request.user.is_counselor_like:
            return Response({'detail': 'Only counselors can create organization accounts.'}, status=403)
        school = self.get_object()
        serializer = OrganizationAccountSerializer(data=request.data, context={'school': school})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
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
    """Teachers/counselors control structure; students only report their progress."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        user = request.user
        if user.is_task_manager:
            return user.role != User.Role.TEACHER or bool(user.school_id)
        if user.is_organization:
            return view.basename == 'tasks' and request.method in permissions.SAFE_METHODS
        if user.role == User.Role.STUDENT:
            if request.method in permissions.SAFE_METHODS:
                return True
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
        return bool(
            student.user_id == user.id
            and (request.method in permissions.SAFE_METHODS or view.action in {'update', 'partial_update'})
        )


class StaffControlledWorkMixin:
    permission_classes = [StaffControlledWorkPermission]

    def filter_work_for_user(self, queryset):
        user = self.request.user
        if user.is_superuser or user.role == User.Role.ADMIN:
            return queryset
        if user.role == User.Role.COUNSELOR:
            return queryset.filter(student__assigned_counselor=user)
        if user.is_staff:
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
        serializer.save(assigned_by=self.request.user)

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
            xp_amount = TASK_XP_BY_PRIORITY[task.priority]
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
                action=f'Task approved: {task.title} (+{xp_amount} XP)',
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


class AchievementViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
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


class HonorViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
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
    """Allow students and their assigned counselors to share bookings and direct messages."""

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
        if user.is_staff or user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.COUNSELOR:
            if isinstance(obj, Booking):
                return obj.counselor_id == user.id
            if isinstance(obj, StudentMessage):
                return user.id in {obj.sender_id, obj.recipient_id}
            return False
        return getattr(obj, 'student_id', None) == user.student_profile.id


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


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [StudentCollaborationPermission]
    queryset = Booking.objects.select_related('student__user', 'counselor').all()

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.role == User.Role.ADMIN:
            return self.queryset
        if user.role == User.Role.COUNSELOR:
            return self.queryset.filter(counselor=user)
        return self.queryset.filter(student=user.student_profile)

    def perform_create(self, serializer):
        profile = self.request.user.student_profile
        serializer.save(student=profile, counselor=profile.assigned_counselor)


class StudentMessageViewSet(viewsets.ModelViewSet):
    serializer_class = StudentMessageSerializer
    permission_classes = [StudentCollaborationPermission]
    queryset = StudentMessage.objects.select_related('student__user', 'sender', 'recipient').all()

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.role == User.Role.ADMIN:
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
    if user.school_id:
        same_school = Q(school_id=user.school_id)
    else:
        same_school = Q(pk__in=[])
    if user.role in {User.Role.ORGANIZATION, User.Role.TEACHER} and user.school_id:
        counselor_ids = StudentProfile.objects.filter(
            school_id=user.school_id,
            assigned_counselor__isnull=False,
        ).values_list('assigned_counselor_id', flat=True)
        return queryset.filter(same_school | Q(id__in=counselor_ids)).distinct().order_by('first_name', 'last_name', 'username')
    if user.role == User.Role.STUDENT and hasattr(user, 'student_profile'):
        counselor_id = user.student_profile.assigned_counselor_id
        return queryset.filter(same_school | Q(id=counselor_id)).distinct().order_by('first_name', 'last_name', 'username')
    return queryset.filter(same_school).order_by('first_name', 'last_name', 'username')


def discoverable_channels_for(user):
    queryset = MessageChannel.objects.select_related('school', 'created_by').prefetch_related(
        'memberships__user',
    )
    if user.is_staff or user.role == User.Role.ADMIN:
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
    moderator_memberships = Q(
        memberships__user=user,
        memberships__role__in=[ChannelMembership.Role.OWNER, ChannelMembership.Role.MODERATOR],
    )
    if user.role == User.Role.COUNSELOR:
        school_ids = StudentProfile.objects.filter(
            assigned_counselor=user,
            school__isnull=False,
        ).values_list('school_id', flat=True)
        return queryset.filter(moderator_memberships | Q(school_id__in=school_ids)).distinct()
    if user.role in {User.Role.TEACHER, User.Role.ORGANIZATION}:
        school_scope = Q(school_id=user.school_id) if user.school_id else Q(pk__in=[])
        return queryset.filter(moderator_memberships | school_scope).distinct()
    return queryset.none()


def channel_membership_role(channel, user):
    membership = channel.memberships.filter(user=user).first()
    return membership.role if membership else None


class MessageChannelPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_staff or user.role == User.Role.ADMIN:
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
                ChannelMembership.objects.bulk_create([
                    ChannelMembership(channel=channel, user=request.user, role=ChannelMembership.Role.OWNER),
                    ChannelMembership(channel=channel, user=target, role=ChannelMembership.Role.MEMBER),
                ])
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
        if user.is_staff or user.role == User.Role.ADMIN:
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
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_task_manager or request.user.is_organization)
        )


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


class ProgramServiceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProgramServiceSerializer
    permission_classes = [StudentPortalPermission]
    queryset = ProgramService.objects.select_related('student__user', 'mentor').all()

    def get_queryset(self):
        return self.queryset.filter(student=self.request.user.student_profile)


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
