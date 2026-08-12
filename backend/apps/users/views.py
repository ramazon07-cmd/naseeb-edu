from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from .models import ProductAuditEvent, User
from .auth_views import token_pair_for_user
from .credentials import complete_password_change, issue_temporary_credential
from .serializers import (
    CounselorTransferSerializer,
    CounselorProvisionSerializer,
    IndividualCounselorCreateSerializer,
    PasswordChangeSerializer,
    ProductAuditEventSerializer,
    RegisterSerializer,
    TemporaryCredentialIssueSerializer,
    UserSerializer,
)
from .services import audit_product_action, transfer_counselor


class IsRoleScopedUserAccess(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_product_admin or request.user.role == User.Role.COUNSELOR:
            return True
        if view.action == 'create':
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if request.user.is_product_admin:
            return True
        if request.user.role == User.Role.COUNSELOR:
            return obj == request.user or (
                obj.role == User.Role.STUDENT
                and request.user.school_id is not None
                and obj.school_id == request.user.school_id
            )
        if request.user.is_organization:
            return (
                request.user.school_id is not None
                and obj.role == User.Role.STUDENT
                and obj.school_id == request.user.school_id
            )
        return obj == request.user


class IsProductAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_product_admin)


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
        if user.is_product_admin:
            queryset = User.objects.select_related('school').all()
            role = self.request.query_params.get('role')
            school = self.request.query_params.get('school')
            active = self.request.query_params.get('is_active')
            search = self.request.query_params.get('search', '').strip()
            if role:
                queryset = queryset.filter(role=role)
            if school:
                queryset = queryset.filter(school_id=school)
            if active in {'true', 'false'}:
                queryset = queryset.filter(is_active=active == 'true')
            if search:
                queryset = queryset.filter(
                    Q(username__icontains=search) | Q(email__icontains=search)
                    | Q(first_name__icontains=search) | Q(last_name__icontains=search)
                )
            return queryset.order_by('first_name', 'last_name', 'id')
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
        return User.objects.filter(id=user.id).order_by('id')

    def perform_update(self, serializer):
        account = serializer.save()
        if self.request.user.is_product_admin:
            audit_product_action(
                actor=self.request.user,
                action='counselor.updated' if account.role == User.Role.COUNSELOR else 'account.updated',
                target=account,
            )

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
        return user.is_product_admin

    @action(detail=False, methods=['post'], url_path='create-counselor')
    def create_counselor(self, request):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can create counselors.'}, status=403)
        serializer = CounselorProvisionSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        counselor = serializer.save()
        return Response(UserSerializer(counselor, context={'request': request}).data, status=201)

    @action(detail=False, methods=['post'], url_path='create-individual-counselor')
    def create_individual_counselor(self, request):
        if not self.is_product_admin(request.user):
            return Response({'detail': 'Only a product admin can create individual counselors.'}, status=403)
        serializer = IndividualCounselorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        counselor = serializer.save()
        audit_product_action(
            actor=request.user,
            action='counselor.created_individual',
            target=counselor,
            metadata={'school': counselor.school_id},
        )
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
        try:
            counselor, _ = transfer_counselor(
                counselor=counselor,
                school=target,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            return Response(exc.message_dict, status=409)
        return Response(UserSerializer(counselor, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        if not request.user.is_product_admin:
            return Response({'detail': 'Only a product admin can deactivate accounts.'}, status=403)
        account = self.get_object()
        if account == request.user:
            return Response({'detail': 'You cannot deactivate your own account.'}, status=400)
        account.is_active = False
        account.save(update_fields=['is_active'])
        audit_product_action(actor=request.user, action='account.deactivated', target=account)
        return Response(UserSerializer(account, context={'request': request}).data)


class ProductAuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductAuditEventSerializer
    permission_classes = [IsProductAdmin]

    def get_queryset(self):
        queryset = ProductAuditEvent.objects.select_related('actor').all()
        action_value = self.request.query_params.get('action')
        target_type = self.request.query_params.get('target_type')
        search = self.request.query_params.get('search', '').strip()
        if action_value:
            queryset = queryset.filter(action=action_value)
        if target_type:
            queryset = queryset.filter(target_type=target_type)
        if search:
            queryset = queryset.filter(
                Q(target_label__icontains=search) | Q(action__icontains=search)
                | Q(actor__username__icontains=search)
            )
        return queryset
    ProductAuditEventSerializer,
