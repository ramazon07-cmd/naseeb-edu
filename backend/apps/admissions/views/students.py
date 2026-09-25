"""Admissions API views — students."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from pathlib import Path
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers
from apps.users.models import User
from apps.users.serializers import UserSerializer
from apps.users.images import serve_private_image
from apps.users.uploads import limit_upload_size, verify_image
from ..models import (
    ActivityLog,
    LevelApproval,
    School,
    StudentProfile,
)
from ..serializers import (
    LevelApprovalSerializer,
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
    StudentProfileSerializer,
    XPTransactionSerializer,
)
from ..exam_scores import EXAM_KEYS
from ..tenancy import create_student_account
from apps.users import entitlements
from apps.users.audit import audit_staff_read
from apps.users.services import audit_product_action
from ..params import int_param
from ..listing import STUDENT_SEARCH_FIELDS, ListQueryMixin
from ..progress import attach_progress_stats
from .common import ScopedQuerysetMixin
from core.storage import delete_file_on_commit


ASSIGNMENT_CANDIDATE_LIMIT = 200


class StudentProfileViewSet(ListQueryMixin, ScopedQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = StudentProfileSerializer
    queryset = StudentProfile.objects.select_related(
        'user', 'user__school', 'assigned_counselor', 'school',
    ).prefetch_related('user__temporary_credentials').order_by('user__first_name', 'user__last_name', 'id')
    search_fields = STUDENT_SEARCH_FIELDS
    int_filters = {'school': 'school_id', 'counselor': 'assigned_counselor_id'}
    choice_filters = {'grade': ('grade', StudentProfile.Grade.choices)}
    bool_filters = {'unassigned': 'assigned_counselor__isnull'}
    date_filters = {'created': 'created_at', 'updated': 'updated_at'}
    ordering_options = {
        'name': ('user__first_name', 'user__last_name', 'id'),
        '-updated': ('-updated_at', '-id'),
        '-created': ('-created_at', '-id'),
    }
    default_cursor_ordering = 'name'

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        if page is not None:
            attach_progress_stats(page)
        return page

    def get_queryset(self):
        queryset = self.filter_for_user(self.queryset)
        if self.action == 'list':
            # Deactivated students drop out of every list; admins still open them.
            queryset = queryset.filter(user__is_active=True)
        return queryset

    @action(detail=False, methods=['get', 'post', 'patch'], url_path='onboarding')
    def onboarding(self, request):
        """Read the student's own answers, complete onboarding (POST) or edit some answers (PATCH).

        POST takes every answer and marks the profile complete. PATCH takes any
        subset, validates it with the stored values of related answers, and
        leaves every other answer as it is.
        """
        if request.user.role != User.Role.STUDENT:
            return Response({'detail': 'Only students can complete their profile.'}, status=403)
        profile = self.get_queryset().filter(user=request.user).first()
        if not profile:
            return Response({'detail': 'Student profile not found.'}, status=404)
        if request.method == 'GET':
            return Response(self.get_serializer(profile).data)
        from ..onboarding import OnboardingSerializer, current_answers
        partial = request.method == 'PATCH'
        with transaction.atomic():
            if partial:
                # Locked so two edits of different sections cannot drop each other's answers.
                profile = StudentProfile.objects.select_for_update(of=('self',)).select_related('user', 'assigned_counselor', 'school').get(pk=profile.pk)
                if profile.profile_completed_at is None:
                    return Response({'detail': 'Complete your profile first.'}, status=400)
            serializer = OnboardingSerializer(
                data=request.data, partial=partial,
                context={'current': current_answers(profile)} if partial else {},
            )
            serializer.is_valid(raise_exception=True)
            self._save_answers(request.user, profile, serializer, partial)
        return Response({'profile': self.get_serializer(profile).data, 'user': UserSerializer(request.user, context={'request': request}).data})

    @staticmethod
    def _save_answers(user, profile, serializer, partial):
        values = serializer.validated_data
        given = values.keys()
        names = [key for key in ('first_name', 'last_name') if key in given]
        if names:
            for key in names:
                setattr(user, key, values[key])
            user.save(update_fields=names)
        if 'gpa_scale' in given:
            profile.gpa_scale = int(values['gpa_scale'])
        for key in ('grade', 'school_name', 'gpa', 'target_countries', 'guardian_name', 'guardian_relation'):
            if not partial or key in given:
                setattr(profile, key, values.get(key) or '' if key.startswith('guardian') else values.get(key))
        for key in EXAM_KEYS:
            if not partial or key in given:
                setattr(profile, key, values.get(key))
        if partial and 'guardian_contact' in given:
            profile.parent_contact = values['guardian_contact']
        elif values.get('guardian_contact'):
            profile.parent_contact = values['guardian_contact']
        if not partial or 'interests' in given:
            profile.target_major = ', '.join(values.get('interests', []))[:160]
        # Test scores have their own columns; the rest of the answers stay as submitted.
        answers = serializer.answers_representation()
        profile.application_profile = {**(profile.application_profile or {}), **answers} if partial else answers
        if not partial:
            profile.profile_completed_at = timezone.now()
        profile.save()
        user.student_profile = profile

    PHOTO_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
    PHOTO_MAX_BYTES = 5 * 1024 * 1024

    @action(detail=True, methods=['get', 'post', 'delete'], url_path='photo')
    def photo(self, request, pk=None):
        """Read, replace or remove a student's profile photo.

        The file lives in private storage like every other personal upload, so it
        is streamed through this authenticated action instead of a media URL;
        ``?v=<photo_version>`` makes the response cacheable.
        """
        student = self.get_object()
        if request.method == 'GET':
            audit_staff_read(request, student, 'student_photo.viewed')
            return serve_private_image(request, student.photo, missing_message='This student has no profile photo.')

        if request.user.role != User.Role.STUDENT or student.user_id != request.user.id:
            return Response(
                {'detail': 'Only the student can change their own profile photo.'},
                status=403,
            )

        previous = student.photo.name if student.photo else ''
        storage = student.photo.storage if previous else None
        if request.method == 'DELETE':
            student.photo = None
            student.save(update_fields=['photo'])
            if previous:
                delete_file_on_commit(storage, previous)
            return Response(status=204)

        limit_upload_size(request, self.PHOTO_MAX_BYTES)
        upload = request.FILES.get('photo')
        if not upload:
            return Response({'photo': 'Choose an image to upload.'}, status=400)
        extension = Path(upload.name or '').suffix.lower()
        if extension not in self.PHOTO_EXTENSIONS:
            return Response(
                {'photo': f'Unsupported image type. Allowed: {", ".join(sorted(self.PHOTO_EXTENSIONS))}.'},
                status=400,
            )
        if upload.size > self.PHOTO_MAX_BYTES:
            return Response({'photo': 'The photo must be 5 MB or smaller.'}, status=400)
        try:
            verify_image(upload)
        except drf_serializers.ValidationError as exc:
            return Response({'photo': exc.detail}, status=400)
        student.photo = upload
        student.save(update_fields=['photo'])
        if previous and previous != student.photo.name:
            delete_file_on_commit(storage, previous)
        return Response(self.get_serializer(student).data)

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
                    'unshared_essays', 'essay_draft_content_and_feedback', 'recommendation_files_and_private_notes',
                    'task_submission_content', 'roadmap_reflections', 'screen_time_detail', 'support_tickets',
                ],
            },
            'student': SchoolVisibilityStudentSerializer(student, context=context).data,
            'tasks': SchoolVisibilityTaskSerializer(student.tasks.select_related('assigned_by').all(), many=True, context=context).data,
            'roadmap': SchoolVisibilityRoadmapSerializer(student.roadmap_missions.all(), many=True, context=context).data,
            'applications': SchoolVisibilityApplicationSerializer(student.applications.select_related('university').all(), many=True, context=context).data,
            'documents': SchoolVisibilityDocumentSerializer(student.documents.all(), many=True, context=context).data,
            'essays': SchoolVisibilityEssaySerializer(student.essays.filter(trashed_at__isnull=True, shared_with_counselor=True).select_related('application__university'), many=True, context=context).data,
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
            counselor_id = int_param(request.query_params, 'counselor')
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

        # A school can hold thousands of candidates: search on the server and
        # return a bounded, name-ordered slice.
        candidates = self.apply_search(candidates, request.query_params.get('search'))[:ASSIGNMENT_CANDIDATE_LIMIT]
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
            supplied_counselor = int_param(request.data, 'counselor')
            if supplied_counselor and str(supplied_counselor) != str(user.id):
                return Response({'counselor': ['Counselors can only connect students to themselves.']}, status=403)
        else:
            counselor = User.objects.filter(
                pk=int_param(request.data, 'counselor'),
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
                StudentProfile.objects.select_for_update(of=('self',))
                .select_related('user')
                .filter(pk__in=student_ids)
            )
            # Both branches below return the identical generic message on purpose:
            # a distinct "does not exist" vs "different school" message would let a
            # counselor enumerate other schools' StudentProfile ids by observing
            # which error comes back.
            if len(students) != len(student_ids):
                return Response({
                    'students': ['One or more selected students are not available for assignment.']
                }, status=400)
            if any(
                student.school_id != counselor.school_id or student.user.school_id != counselor.school_id
                for student in students
            ):
                return Response({
                    'students': ['One or more selected students are not available for assignment.']
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

    def perform_create(self, serializer):
        with transaction.atomic():
            profile = serializer.save()
            # The account follows the profile, which is the student's tenant.
            User.objects.filter(pk=profile.user_id).update(school=profile.school)
            ActivityLog.objects.create(
                actor=self.request.user,
                student=profile,
                action=f'Student profile created: {profile.user.get_full_name() or profile.user.username}',
            )

    def perform_update(self, serializer):
        from ..tenancy import move_student

        new_school = serializer.validated_data.pop('school', serializer.instance.school)
        try:
            with transaction.atomic():
                if new_school != serializer.instance.school:
                    move_student(serializer.instance, new_school, self.request.user)
                serializer.save()
        except DjangoValidationError as exc:
            raise drf_serializers.ValidationError(exc.message_dict) from exc

    def destroy(self, request, *args, **kwargs):
        """Deactivate, never delete: the student's records are kept."""
        from ..tenancy import set_student_active

        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can deactivate a student.'}, status=403)
        set_student_active(self.get_object(), False, request.user)
        return Response(status=204)

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
        audit_staff_read(request, student, 'student_xp.viewed')
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
        # An address that is already registered must not produce a
        # different response: create_student_account() attaches a
        # placeholder instead, and the response never echoes the email.
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

        if request.user.is_organization or request.user.role == User.Role.COUNSELOR:
            # Staff add students to their own school, and only while it is active.
            school = request.user.school
            if not school or not school.is_active:
                return Response({'school': ['Your account is not connected to an active school.']}, status=400)
            supplied_school = int_param(request.data, 'school')
            if supplied_school and str(supplied_school) != str(school.id):
                return Response({'school': ['You can only add students to your own school.']}, status=400)
        else:
            school_id = int_param(request.data, 'school')
            if not school_id:
                return Response({'school': ['Select a school for this student.']}, status=400)
            school = School.objects.filter(id=school_id, is_active=True).first()
            if not school:
                return Response({'school': ['Selected school does not exist or is inactive.']}, status=400)

        try:
            student = create_student_account(
                school=school,
                full_name=full_name,
                password=password,
                created_by=request.user,
                email=email,
                phone=str(request.data.get('phone') or ''),
                request=request,
            )
        except entitlements.EntitlementError as exc:
            return Response(exc.response_data(), status=400)

        data = StudentProfileSerializer(student, context={'request': request}).data
        if isinstance(data.get('user_detail'), dict):
            data['user_detail'].pop('email', None)
        return Response(data, status=201)
