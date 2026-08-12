from django.db import transaction
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from .models import User
from .auth_views import token_pair_for_user
from .credentials import complete_password_change, issue_temporary_credential
from .serializers import (
    CounselorTransferSerializer,
    IndividualCounselorCreateSerializer,
    PasswordChangeSerializer,
    RegisterSerializer,
    TemporaryCredentialIssueSerializer,
    UserSerializer,
)


class IsRoleScopedUserAccess(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_counselor_like:
            return True
        if view.action == 'create':
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if request.user.is_counselor_like:
            return True
        if request.user.is_organization:
            return (
                request.user.school_id is not None
                and obj.role == User.Role.STUDENT
                and obj.school_id == request.user.school_id
            )
        return obj == request.user


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.IsAuthenticated]


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsRoleScopedUserAccess]
    throttle_scope = None

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.role == User.Role.ADMIN:
            return User.objects.all().order_by('first_name', 'last_name')
        if user.role == User.Role.COUNSELOR:
            if not user.school_id:
                return User.objects.none()
            return User.objects.filter(
                role__in=[User.Role.STUDENT, User.Role.COUNSELOR],
                school_id=user.school_id,
            ).order_by('first_name', 'last_name')
        if user.role == User.Role.ORGANIZATION:
            if not user.school_id:
                return User.objects.none()
            return User.objects.filter(role=User.Role.STUDENT, school=user.school).order_by('first_name', 'last_name')
        return User.objects.filter(id=user.id)

    @action(detail=False, methods=['get'])
    def me(self, request):
        return Response(UserSerializer(request.user, context={'request': request}).data)

    @action(
        detail=False,
        methods=['post'],
        url_path='change-password',
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='password_change',
    )
    def change_password(self, request):
        if not request.user.must_change_password:
            return Response({'detail': 'No mandatory password change is pending.'}, status=400)
        serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        try:
            user = complete_password_change(
                user=request.user,
                new_password=serializer.validated_data['new_password'],
                request=request,
            )
        except ValueError as exc:
            if str(exc) == 'password_reuse':
                return Response({'new_password': ['Choose a password different from the temporary password.']}, status=400)
            raise
        return Response({
            **token_pair_for_user(user),
            'user': UserSerializer(user, context={'request': request}).data,
        })

    @action(
        detail=True,
        methods=['post'],
        url_path='temporary-credential',
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='credential_issue',
    )
    def temporary_credential(self, request, pk=None):
        target = self.get_object()
        if target.role not in {User.Role.STUDENT, User.Role.ORGANIZATION}:
            return Response({'detail': 'Temporary credentials are only available for student and school accounts.'}, status=400)
        allowed = self.is_product_admin(request.user)
        if request.user.role == User.Role.COUNSELOR and target.role == User.Role.STUDENT:
            allowed = bool(
                request.user.school_id
                and target.school_id == request.user.school_id
                and hasattr(target, 'student_profile')
                and target.student_profile.assigned_counselor_id == request.user.id
            )
        if request.user.is_organization and target.role == User.Role.STUDENT:
            allowed = bool(request.user.school_id and target.school_id == request.user.school_id)
        if not allowed:
            return Response({'detail': 'You cannot issue credentials for this account.'}, status=403)

        serializer = TemporaryCredentialIssueSerializer(
            data=request.data,
            context={'request': request, 'target_user': target},
        )
        serializer.is_valid(raise_exception=True)
        target, credential, password, generated = issue_temporary_credential(
            user=target,
            issued_by=request.user,
            raw_password=serializer.validated_data.get('password') or None,
            request=request,
        )
        return Response({
            'user': UserSerializer(target, context={'request': request}).data,
            'credential': {
                'status': credential.status,
                'issued_at': credential.issued_at,
                'expires_at': credential.expires_at,
            },
            'temporary_password': password if generated else None,
            'delivery_notice': 'Show the generated password once over an approved secure channel. It is not stored in plaintext.',
        })

    @staticmethod
    def is_product_admin(user):
        return bool(user.is_superuser or user.role == User.Role.ADMIN)

    @action(detail=False, methods=['post'], url_path='create-individual-counselor')
    def create_individual_counselor(self, request):
        if not self.is_product_admin(request.user):
            return Response({'detail': 'Only a product admin can create individual counselors.'}, status=403)
        serializer = IndividualCounselorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        counselor = serializer.save()
        return Response(
            UserSerializer(counselor, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='transfer-school')
    def transfer_school(self, request, pk=None):
        if not self.is_product_admin(request.user):
            return Response({'detail': 'Only a product admin can transfer counselors.'}, status=403)
        counselor = self.get_object()
        if counselor.role != User.Role.COUNSELOR:
            return Response({'detail': 'Only counselor accounts can be transferred.'}, status=400)
        serializer = CounselorTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.admissions.models import School

        target = School.objects.filter(
            id=serializer.validated_data['school'],
            is_active=True,
            workspace_type=School.WorkspaceType.SCHOOL,
        ).first()
        if not target:
            return Response({'school': ['Select an active organization school.']}, status=400)
        mismatched_students = counselor.assigned_students.exclude(school=target)
        if mismatched_students.exists():
            return Response({
                'detail': 'Reassign or move the counselor’s students before transferring the counselor.'
            }, status=409)
        previous_workspace = counselor.school
        with transaction.atomic():
            counselor.school = target
            counselor.save(update_fields=['school'])
            if (
                previous_workspace
                and previous_workspace.workspace_type == School.WorkspaceType.INDIVIDUAL
                and previous_workspace.owner_counselor_id == counselor.id
            ):
                previous_workspace.is_active = False
                previous_workspace.save(update_fields=['is_active', 'updated_at'])
        return Response(UserSerializer(counselor, context={'request': request}).data)
