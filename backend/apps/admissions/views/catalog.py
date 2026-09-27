"""Admissions API views — catalog."""
from django.db.models import Count, Prefetch
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.users.models import User
from ..models import (
    OpportunityProgram,
    School,
    Scholarship,
    StoreItem,
    University,
)
from ..serializers import (
    OpportunityProgramSerializer,
    OrganizationAccountSerializer,
    SchoolSerializer,
    ScholarshipSerializer,
    StoreItemSerializer,
    UniversitySerializer,
)
from apps.users import entitlements
from apps.users.admin_permissions import has_tier
from apps.users.services import audit_product_action
from ..catalog_cache import CachedCatalogListMixin
from ..listing import ListQueryMixin
from .common import CounselorOrOwnerPermission, ProductAdminPermission
from .portal import StudentPortalPermission


class SchoolViewSet(ListQueryMixin, viewsets.ModelViewSet):
    serializer_class = SchoolSerializer
    permission_classes = [CounselorOrOwnerPermission]
    queryset = entitlements.annotate_seat_usage(
        School.objects.annotate(students_count=Count('students')),
    ).select_related(
        'owner_counselor', 'subscription__plan',
    ).prefetch_related(
        Prefetch(
            'users',
            queryset=User.objects.filter(role=User.Role.ORGANIZATION).prefetch_related('temporary_credentials').order_by('pk'),
            to_attr='prefetched_organization_accounts',
        ),
    ).order_by('name')
    search_fields = ('name', 'code', 'contact_email')
    choice_filters = {
        'workspace_type': ('workspace_type', School.WorkspaceType.choices),
        'region': ('region', School.Region.choices),
    }
    bool_filters = {'is_active': 'is_active'}
    ordering_options = {'name': ('name', 'id'), '-created': ('-created_at', '-id')}
    default_cursor_ordering = 'name'

    def get_queryset(self):
        if self.request.user.is_product_admin:
            return self.queryset
        if self.request.user.role == User.Role.COUNSELOR and self.request.user.school_id:
            return self.queryset.filter(id=self.request.user.school_id)
        if self.request.user.is_organization and self.request.user.school_id:
            return self.queryset.filter(id=self.request.user.school_id)
        return self.queryset.none()

    @staticmethod
    def can_manage(user):
        return has_tier(user, User.AdminTier.OPS)

    def create(self, request, *args, **kwargs):
        if not self.can_manage(request.user):
            return Response({'detail': 'Only a product admin can create schools.'}, status=403)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        school = serializer.save()
        audit_product_action(actor=self.request.user, action='school.created', target=school)

    def update(self, request, *args, **kwargs):
        if not self.can_manage(request.user):
            return Response({'detail': 'Only a product admin can edit schools.'}, status=403)
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        school = serializer.save()
        audit_product_action(actor=self.request.user, action='school.updated', target=school)

    def destroy(self, request, *args, **kwargs):
        if not self.can_manage(request.user):
            return Response({'detail': 'Only a product admin can deactivate schools.'}, status=403)
        school = self.get_object()
        school.is_active = False
        school.save(update_fields=['is_active', 'updated_at'])
        audit_product_action(actor=request.user, action='school.deactivated', target=school)
        return Response(status=204)

    @action(detail=True, methods=['post'], url_path='create-account')
    def create_account(self, request, pk=None):
        school = self.get_object()
        if not self.can_manage(request.user):
            return Response({'detail': 'Only a product admin can create organization accounts.'}, status=403)
        try:
            entitlements.require_school_feature(school, 'organization_accounts')
        except entitlements.EntitlementError as exc:
            return Response(exc.response_data(), status=400)
        if school.workspace_type == School.WorkspaceType.INDIVIDUAL:
            return Response({'detail': 'An individual counselor workspace has no school accounts.'}, status=400)
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


class UniversityViewSet(CachedCatalogListMixin, viewsets.ModelViewSet):
    serializer_class = UniversitySerializer
    queryset = University.objects.prefetch_related('programs').all()
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        # Universities are a shared catalog: any authenticated user may read,
        # but only a product admin may create/update/delete — counselors are
        # not scoped to a school here, so CounselorOrOwnerPermission's
        # unconditional `is_counselor_like` pass would let any counselor at
        # any school mutate or delete rows other schools' data depends on.
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [ProductAdminPermission()]


class ScholarshipViewSet(CachedCatalogListMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ScholarshipSerializer
    queryset = Scholarship.objects.select_related('university').filter(is_active=True)
    permission_classes = [permissions.IsAuthenticated]


class OpportunityProgramViewSet(CachedCatalogListMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = OpportunityProgramSerializer
    # Most catalog entries repeat every year with a text deadline, so a closed cycle is
    # labelled in the UI instead of hidden here.
    queryset = OpportunityProgram.objects.filter(is_active=True)
    permission_classes = [permissions.IsAuthenticated]


class StoreItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StoreItemSerializer
    permission_classes = [StudentPortalPermission]
    queryset = StoreItem.objects.filter(is_active=True)
