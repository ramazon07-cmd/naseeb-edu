from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.response import Response
from apps.users.throttles import ScopedRateThrottle
from apps.admissions.listing import ListQueryMixin
from . import entitlements
from .admin_permissions import IsSupportStaff, SupportReadOpsWrite, SupportReadSuperadminWrite, has_tier, staff_tier_denied
from .audit import (
    ACCOUNT_OWN_ROW_FIELDS,
    account_update_metadata,
    audit_staff_read,
    audit_subscription_change,
    field_changes,
    recorded_actions,
    subscription_audit_state,
)
from .models import PLAN_LIMITS, CredentialAuditEvent, Plan, ProductAuditEvent, User, WorkspaceSubscription
from .auth_views import token_pair_for_user
from .credentials import change_own_password, complete_password_change, issue_temporary_credential
from .serializers import (
    AUDIT_SCHOOL_KEYS,
    AccountEmailChangeSerializer,
    AccountPasswordChangeSerializer,
    CounselorTransferSerializer,
    CounselorProvisionSerializer,
    DashboardLayoutSerializer,
    IndividualCounselorCreateSerializer,
    PasswordChangeSerializer,
    PlanSerializer,
    ProductAuditEventSerializer,
    StaffCreateSerializer,
    SupportViewRequestSerializer,
    TemporaryCredentialIssueSerializer,
    UserSerializer,
    WorkspaceSubscriptionSerializer,
)
from .services import audit_product_action, transfer_counselor
from .images import serve_private_image
from .uploads import limit_upload_size


OPS = User.AdminTier.OPS
SUPPORT = User.AdminTier.SUPPORT
SUPERADMIN = User.AdminTier.SUPERADMIN
TENANCY_AUDIT_ACTIONS = frozenset({
    'student.moved', 'student.deactivated', 'student.reactivated', 'account.moved', 'account.deactivated',
    'account.reactivated', 'staff.tier_changed',
})


def student_account_in_scope(account, user):
    """Whether ``user`` manages student ``account`` under the canonical scoping rules.

    The profile's school decides, so an account row that lags behind a move
    never keeps the old school in control.
    """
    from apps.admissions.scoping import student_lookups

    if user.role not in {User.Role.COUNSELOR, User.Role.ORGANIZATION}:
        return False
    lookups = student_lookups(user)
    if not lookups:
        return False
    return User.objects.filter(
        pk=account.pk,
        **{f'student_profile__{key}': value for key, value in lookups.items()},
    ).exists()


class IsRoleScopedUserAccess(permissions.BasePermission):
    """Object access for ``/api/users/accounts/``.

    Product admins manage every account. Counselors may only touch their own
    account and the students assigned to them (matching ``/api/students/``);
    organization accounts may read and edit students of their own school.
    Deleting an account is reserved for product admins. Support staff only
    read, reset credentials and open support views; changes need ops.
    Another staff account (admin role or superuser) is changed, deactivated
    or opened in a support view by super admins only.
    """

    support_actions = {'me', 'change_password', 'temporary_credential', 'support_view'}

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_product_admin:
            if request.method in permissions.SAFE_METHODS or view.action in self.support_actions:
                return True
            return has_tier(request.user, OPS)
        if view.action == 'destroy':
            return False
        if view.action == 'create':
            school = request.user.school if request.user.role == User.Role.COUNSELOR else None
            return bool(school and school.is_active)
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_product_admin:
            if (
                request.method not in permissions.SAFE_METHODS
                and obj.pk != user.pk
                and obj.is_product_admin
                and not has_tier(user, SUPERADMIN)
            ):
                raise staff_tier_denied(request)
            return True
        if view.action == 'destroy':
            return False
        if obj == user:
            return True
        return obj.role == User.Role.STUDENT and student_account_in_scope(obj, user)


class UserViewSet(ListQueryMixin, viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsRoleScopedUserAccess]
    throttle_scope = None
    search_fields = ('username', 'email', 'first_name', 'last_name')
    choice_filters = {'role': ('role', User.Role.choices)}
    int_filters = {'school': 'school_id'}
    bool_filters = {'is_active': 'is_active'}
    ordering_options = {
        'name': ('first_name', 'last_name', 'id'),
        '-joined': ('-date_joined', '-id'),
    }
    default_cursor_ordering = 'name'

    def initial(self, request, *args, **kwargs):
        # The only file this viewset accepts is the avatar.
        limit_upload_size(request, settings.AVATAR_MAX_UPLOAD_SIZE)
        super().initial(request, *args, **kwargs)

    def get_queryset(self):
        # UserSerializer reads the student profile and the latest temporary
        # credential of every row.
        return self.scoped_queryset().select_related('school', 'student_profile').prefetch_related(
            'temporary_credentials',
        )

    def scoped_queryset(self):
        user = self.request.user
        if user.is_product_admin:
            return User.objects.order_by('first_name', 'last_name', 'id')
        if user.role in {User.Role.COUNSELOR, User.Role.ORGANIZATION}:
            from apps.admissions.scoping import student_lookups

            lookups = student_lookups(user)
            if not lookups:
                return User.objects.none()
            # Students are matched by their profile, the single source of
            # their school; staff rows by the account's school.
            visible = Q(role=User.Role.STUDENT, **{
                f'student_profile__{key}': value for key, value in lookups.items()
            })
            if user.role == User.Role.COUNSELOR:
                visible |= Q(role=User.Role.COUNSELOR, school_id=user.school_id)
            return User.objects.filter(visible).order_by('first_name', 'last_name', 'id')
        return User.objects.filter(id=user.id).order_by('id')

    def perform_create(self, serializer):
        account = serializer.save()
        if self.request.user.is_product_admin:
            audit_product_action(actor=self.request.user, action='account.created', target=account)

    def retrieve(self, request, *args, **kwargs):
        account = self.get_object()
        if account.role == User.Role.STUDENT and account != request.user:
            audit_staff_read(request, account, 'student_account.viewed')
        return Response(self.get_serializer(account).data)

    def perform_update(self, serializer):
        from apps.admissions.services import ensure_student_profile
        from apps.admissions.tenancy import move_student, set_student_active, user_left_school

        previous_school = serializer.instance.school
        previous_active = serializer.instance.is_active
        previous_tier = serializer.instance.admin_tier
        role = serializer.validated_data.get('role', serializer.instance.role)
        moving_student = role == User.Role.STUDENT and 'school' in serializer.validated_data
        new_school = serializer.validated_data.pop('school', None) if moving_student else None
        # A student's move and activation go through the tenancy services,
        # which also write their audit events; other accounts are audited here.
        activation = serializer.validated_data.pop('is_active', None) if role == User.Role.STUDENT else None
        other_changes = {
            name: change for name, change in field_changes(serializer.instance, serializer.validated_data).items()
            if name not in ACCOUNT_OWN_ROW_FIELDS
        }
        try:
            with transaction.atomic(), recorded_actions() as audited:
                account = serializer.save()
                if (
                    account.role != User.Role.STUDENT
                    and previous_school is not None
                    and previous_school.pk != account.school_id
                ):
                    user_left_school(account, previous_school)
                ensure_student_profile(account, actor=self.request.user)
                if moving_student:
                    move_student(account, new_school, self.request.user)
                if activation is not None and hasattr(account, 'student_profile'):
                    set_student_active(account, activation, self.request.user)
                if account.role != User.Role.STUDENT:
                    if account.school_id != (previous_school.pk if previous_school else None):
                        audit_product_action(
                            actor=self.request.user,
                            action='account.moved',
                            target=account,
                            metadata={
                                'from_school': previous_school.pk if previous_school else None,
                                'to_school': account.school_id,
                            },
                        )
                    if previous_active and not account.is_active:
                        audit_product_action(actor=self.request.user, action='account.deactivated', target=account)
                    elif not previous_active and account.is_active:
                        audit_product_action(actor=self.request.user, action='account.reactivated', target=account)
                    if account.admin_tier != previous_tier:
                        audit_product_action(
                            actor=self.request.user, action='staff.tier_changed', target=account,
                            metadata={'changes': {'admin_tier': {'from': previous_tier, 'to': account.admin_tier}}},
                        )
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        # A move, (de)activation or tier change has its own row; every other changed
        # field (email, username, names...) is listed on one update row next to it.
        if self.request.user.is_product_admin and (other_changes or not TENANCY_AUDIT_ACTIONS.intersection(audited)):
            audit_product_action(
                actor=self.request.user,
                action='counselor.updated' if account.role == User.Role.COUNSELOR else 'account.updated',
                target=account,
                metadata=account_update_metadata(other_changes),
            )

    def perform_destroy(self, instance):
        """Soft-delete: deactivate instead of cascading away the student's records."""
        if instance == self.request.user:
            raise ValidationError({'detail': 'You cannot delete your own account.', 'code': 'own_account'})
        self._deactivate(instance)

    def _deactivate(self, account):
        from apps.admissions.tenancy import set_student_active

        # Students are audited by the service as student.deactivated.
        if account.role == User.Role.STUDENT and hasattr(account, 'student_profile'):
            set_student_active(account, False, self.request.user)
            return
        account.is_active = False
        account.save(update_fields=['is_active'])
        audit_product_action(actor=self.request.user, action='account.deactivated', target=account)

    @action(detail=True, methods=['get'], url_path='avatar')
    def avatar(self, request, pk=None):
        account = self.get_object()
        return serve_private_image(request, account.avatar, missing_message='This account has no avatar.')

    @action(detail=False, methods=['get'])
    def me(self, request):
        data = UserSerializer(request.user, context={'request': request}).data
        subscription = None
        if request.user.school_id:
            subscription = WorkspaceSubscription.objects.select_related('plan').filter(
                school_id=request.user.school_id,
            ).first()
        data['workspace'] = entitlements.workspace_summary(subscription)
        # Same rules as the chat view, so the frontend only offers what will work.
        data['assistant_enabled'] = entitlements.assistant_available(request.user, subscription)
        return Response(data)

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
        detail=False,
        methods=['post'],
        url_path='me/password',
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='password_change',
    )
    def account_password(self, request):
        """Change your own password; this session gets a new token pair, others end."""
        serializer = AccountPasswordChangeSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = change_own_password(
            user=request.user,
            new_password=serializer.validated_data['new_password'],
            request=request,
        )
        return Response({
            **token_pair_for_user(user),
            'user': UserSerializer(user, context={'request': request}).data,
        })

    @action(
        detail=False,
        methods=['post'],
        url_path='me/email',
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='account_change',
    )
    def account_email(self, request):
        serializer = AccountEmailChangeSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = request.user
        if email != user.email:
            try:
                with transaction.atomic():
                    User.objects.filter(pk=user.pk).update(email=email)
            except IntegrityError:
                # Taken by a concurrent request between the check and the write.
                raise ValidationError({'email': [ErrorDetail(
                    'This email address is already used by another account.', code='email_taken',
                )]}) from None
            user.email = email
        return Response(UserSerializer(user, context={'request': request}).data)

    @action(detail=False, methods=['get', 'put'], url_path='me/dashboard-layout')
    def dashboard_layout(self, request):
        """The signed-in user's dashboard arrangement, shared by all their devices."""
        user = request.user
        if request.method == 'PUT':
            serializer = DashboardLayoutSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user.dashboard_layout = serializer.validated_data['layout']
            user.save(update_fields=['dashboard_layout'])
        return Response({'layout': user.dashboard_layout})

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
            return Response({
                'detail': 'Temporary credentials are only available for student and school accounts.',
                'code': 'credential_role_unsupported',
            }, status=400)
        allowed = has_tier(request.user, SUPPORT) or (
            target.role == User.Role.STUDENT and student_account_in_scope(target, request.user)
        )
        if not allowed:
            return Response({'detail': 'You cannot issue credentials for this account.', 'code': 'credential_forbidden'}, status=403)

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
        audit_product_action(
            actor=request.user,
            action='credential.issued',
            target=target,
            metadata={'role': target.role},
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
        return has_tier(user, OPS)

    @action(detail=False, methods=['post'], url_path='create-counselor')
    def create_counselor(self, request):
        if not self.is_product_admin(request.user):
            return Response({'detail': 'Only a product admin can create counselors.', 'code': 'product_admin_required'}, status=403)
        serializer = CounselorProvisionSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        counselor = serializer.save()
        return Response(UserSerializer(counselor, context={'request': request}).data, status=201)

    @action(detail=False, methods=['post'], url_path='create-individual-counselor')
    def create_individual_counselor(self, request):
        if not self.is_product_admin(request.user):
            return Response({
                'detail': 'Only a product admin can create individual counselors.', 'code': 'product_admin_required',
            }, status=403)
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

    @action(
        detail=False,
        methods=['post'],
        url_path='create-staff',
        throttle_classes=[ScopedRateThrottle],
        throttle_scope='credential_issue',
    )
    def create_staff(self, request):
        if not has_tier(request.user, SUPERADMIN):
            raise staff_tier_denied(request)
        serializer = StaffCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        staff = serializer.save()
        return Response({
            'user': UserSerializer(staff, context={'request': request}).data,
            'temporary_password': serializer.temporary_password,
            'credential': {'status': serializer.credential.status, 'expires_at': serializer.credential.expires_at},
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='transfer-school')
    def transfer_school(self, request, pk=None):
        if not self.is_product_admin(request.user):
            return Response({'detail': 'Only a product admin can transfer counselors.', 'code': 'product_admin_required'}, status=403)
        counselor = self.get_object()
        if counselor.role != User.Role.COUNSELOR:
            return Response({'detail': 'Only counselor accounts can be transferred.', 'code': 'not_a_counselor'}, status=400)
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
                'detail': 'Reassign or move the counselor’s students before transferring the counselor.',
                'code': 'counselor_has_students',
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
        if not self.is_product_admin(request.user):
            return Response({'detail': 'Only a product admin can deactivate accounts.', 'code': 'product_admin_required'}, status=403)
        account = self.get_object()
        if account == request.user:
            return Response({'detail': 'You cannot deactivate your own account.', 'code': 'own_account'}, status=400)
        self._deactivate(account)
        return Response(UserSerializer(account, context={'request': request}).data)

    SUPPORT_VIEW_EVENTS = 10

    @action(detail=True, methods=['post'], url_path='support-view')
    def support_view(self, request, pk=None):
        """Read-only account snapshot for support, opened with a recorded reason.

        Deliberately not an impersonation: no token for the account is issued,
        and the snapshot holds account state only, never the person's private
        content (messages, essays, notes).
        """
        if not has_tier(request.user, SUPPORT):
            return Response({'detail': 'Only product staff can open a support view.', 'code': 'product_admin_required'}, status=403)
        serializer = SupportViewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = self.get_object()
        audit_product_action(
            actor=request.user,
            action='support.profile_viewed',
            target=account,
            metadata={'reason': serializer.validated_data['reason'], 'staff_tier': request.user.staff_tier},
        )
        subscription = None
        if account.school_id:
            subscription = WorkspaceSubscription.objects.select_related('plan').filter(
                school_id=account.school_id,
            ).first()
        profile = getattr(account, 'student_profile', None) if account.role == User.Role.STUDENT else None
        events = CredentialAuditEvent.objects.filter(target_user=account).select_related('actor')[:self.SUPPORT_VIEW_EVENTS]
        return Response({
            'account': {
                **UserSerializer(account, context={'request': request}).data,
                'last_login': account.last_login,
                'date_joined': account.date_joined,
            },
            'workspace': entitlements.workspace_summary(subscription),
            'student': {
                'grade': profile.grade,
                'level': profile.level,
                'profile_completed': bool(profile.profile_completed_at),
                'assigned_counselor': profile.assigned_counselor_id,
            } if profile else None,
            'credential_events': [
                {
                    'event': event.event,
                    'created_at': event.created_at,
                    'actor_name': (event.actor.get_full_name() or event.actor.username) if event.actor else None,
                }
                for event in events
            ],
        })



class ProductAuditEventViewSet(ListQueryMixin, viewsets.ReadOnlyModelViewSet):
    """Paged audit log filterable by actor, action, school and date range."""

    serializer_class = ProductAuditEventSerializer
    permission_classes = [IsSupportStaff]
    search_fields = ('target_label', 'action', 'actor__username')
    int_filters = {'actor': 'actor_id', 'school': 'school_id'}
    date_filters = {'date': 'created_at'}
    ordering_options = {'-created': ('-created_at', '-id')}
    default_cursor_ordering = '-created'

    def get_serializer(self, *args, **kwargs):
        # One query per page resolves the school ids that metadata mentions.
        if kwargs.get('many') and args:
            from apps.admissions.models import School

            events = list(args[0])
            ids = {
                value for event in events if isinstance(event.metadata, dict)
                for key in AUDIT_SCHOOL_KEYS if isinstance(value := event.metadata.get(key), int)
            }
            context = self.get_serializer_context()
            context['school_names'] = dict(School.objects.filter(id__in=ids).values_list('id', 'name')) if ids else {}
            kwargs['context'] = context
            args = (events, *args[1:])
        return super().get_serializer(*args, **kwargs)

    def get_queryset(self):
        queryset = ProductAuditEvent.objects.select_related('actor', 'school').all()
        params = self.request.query_params
        # Free-form audit vocabularies, bounded by the column length.
        action_value = params.get('action', '').strip()[:80]
        target_type = params.get('target_type', '').strip()[:80]
        if action_value:
            # "student_360" matches every student_360.* event.
            queryset = queryset.filter(
                Q(action=action_value) | Q(action__startswith=f'{action_value.rstrip(".")}.')
            )
        if target_type:
            queryset = queryset.filter(target_type=target_type)
        return queryset


class PlanViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """Plans and their limits and features. Support staff read; super admins
    create, edit and retire (no delete: subscriptions keep pointing at a plan)."""

    serializer_class = PlanSerializer
    permission_classes = [SupportReadSuperadminWrite]
    pagination_class = None
    queryset = Plan.objects.annotate(workspaces_count=Count('subscriptions')).order_by('name', 'id')

    def perform_create(self, serializer):
        plan = serializer.save()
        audit_product_action(
            actor=self.request.user, action='plan.created', target=plan,
            metadata={'workspace_type': plan.workspace_type, 'features': plan.features},
        )

    def perform_update(self, serializer):
        was_active = serializer.instance.is_active
        changes = field_changes(serializer.instance, serializer.validated_data)
        plan = serializer.save()
        action_name = 'plan.retired' if was_active and not plan.is_active else 'plan.updated'
        audit_product_action(actor=self.request.user, action=action_name, target=plan, metadata={'changes': changes})

    @action(detail=True, methods=['get'])
    def impact(self, request, pk=None):
        """Workspaces on this plan, and those whose current seats exceed the given limits.

        Lowering a limit never removes accounts; it only blocks new ones, so
        this is what an admin should know before saving lower numbers.
        """
        from apps.admissions.models import School
        from apps.admissions.params import int_param

        plan = self.get_object()
        limits = {key: int_param(request.query_params, key) for key in PLAN_LIMITS}
        limits = {key: value for key, value in limits.items() if value is not None}
        if any(value < 0 for value in limits.values()):
            raise ValidationError({'detail': 'Limits cannot be negative.'})
        schools = entitlements.annotate_seat_usage(School.objects.filter(subscription__plan=plan)).order_by('name')
        over = Q()
        for key, value in limits.items():
            over |= Q(**{f'{key}_used__gt': value})
        over_limit = schools.filter(over) if limits else School.objects.none()
        return Response({
            'workspaces': schools.count(),
            'over_limit': [
                {
                    'id': school.id, 'name': school.name,
                    'seats': {
                        key: {'used': getattr(school, f'{key}_used'), 'limit': value}
                        for key, value in limits.items() if getattr(school, f'{key}_used') > value
                    },
                }
                for school in over_limit[:50]
            ],
        })


class WorkspaceSubscriptionViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """A workspace's plan and access state, addressed by school id."""

    serializer_class = WorkspaceSubscriptionSerializer
    permission_classes = [SupportReadOpsWrite]
    queryset = WorkspaceSubscription.objects.select_related('plan', 'school')
    lookup_field = 'school'
    lookup_value_regex = '[0-9]+'

    def get_object(self):
        from apps.admissions.models import School

        school = get_object_or_404(School, pk=self.kwargs['school'])
        return entitlements.ensure_subscription(school)

    def perform_update(self, serializer):
        with transaction.atomic():
            subscription = WorkspaceSubscription.objects.select_for_update().select_related('plan').get(
                pk=serializer.instance.pk,
            )
            before = subscription_audit_state(subscription)
            serializer.instance = subscription
            updated = serializer.save(updated_by=self.request.user)
            audit_subscription_change(actor=self.request.user, before=before, subscription=updated)
