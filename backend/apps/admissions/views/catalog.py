"""Admissions API views — catalog."""
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from apps.users.models import User
from ..models import (
    OpportunityProgram,
    SavedOpportunityProgram,
    School,
    Scholarship,
    StoreItem,
    University,
    UniversityProgram,
)
from ..serializers import (
    CatalogOpportunityProgramSerializer,
    CatalogProgramSerializer,
    CatalogScholarshipSerializer,
    CatalogUniversitySerializer,
    OpportunityProgramSerializer,
    OrganizationAccountSerializer,
    SchoolSerializer,
    ScholarshipSerializer,
    StoreItemSerializer,
    UniversityRowSerializer,
    UniversitySerializer,
)
from apps.users import entitlements
from apps.users.admin_permissions import SupportReadOpsWrite, has_tier
from apps.users.services import audit_product_action
from ..catalog_cache import CachedCatalogListMixin
from ..college_search import SEARCH_FIELDS
from ..pricing import with_cost
from ..listing import ListQueryMixin
from .common import CounselorOrOwnerPermission, ProductAdminPermission
from .portal import StudentPortalPermission


class SavedProgramPermission(StudentPortalPermission):
    def has_object_permission(self, request, view, obj):
        return True


class SchoolViewSet(ListQueryMixin, viewsets.ModelViewSet):
    serializer_class = SchoolSerializer
    permission_classes = [CounselorOrOwnerPermission]
    queryset = entitlements.annotate_seat_usage(
        # Deactivated students keep their data but are not counted (scoping.active_visible_students).
        School.objects.annotate(students_count=Count(
            'students', filter=Q(students__user__is_active=True, students__deactivated_at__isnull=True),
        )),
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


class UniversityViewSet(ListQueryMixin, CachedCatalogListMixin, viewsets.ModelViewSet):
    """The shared catalogue. Lists are searched and paged like every other list
    (at most 100 rows a page) with slim rows; a university's full record is its
    detail. College Search pages through ``/api/college-search/`` instead."""

    serializer_class = UniversitySerializer
    queryset = University.objects.prefetch_related('programs').all()
    permission_classes = [permissions.IsAuthenticated]
    search_fields = SEARCH_FIELDS
    search_folded_field = 'search_text'
    ordering_options = {'name': ('name', 'id')}
    default_cursor_ordering = 'name'

    def get_queryset(self):
        if self.action == 'list':
            return with_cost(University.objects.all())
        return with_cost(super().get_queryset())

    def get_serializer_class(self):
        return UniversityRowSerializer if self.action == 'list' else UniversitySerializer

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

    def get_permissions(self):
        if self.action in {'saved', 'save'}:
            return [SavedProgramPermission()]
        return super().get_permissions()

    @action(detail=False, methods=['get'])
    def saved(self, request):
        ids = SavedOpportunityProgram.objects.filter(
            student=request.user.student_profile,
            program__is_active=True,
        ).values_list('program_id', flat=True)
        return Response({'program_ids': list(ids)})

    @action(detail=True, methods=['post', 'delete'])
    def save(self, request, pk=None):
        program = self.get_object()
        lookup = {'student': request.user.student_profile, 'program': program}
        if request.method == 'POST':
            SavedOpportunityProgram.objects.get_or_create(**lookup)
            return Response({'program_id': program.id, 'saved': True}, status=status.HTTP_200_OK)
        SavedOpportunityProgram.objects.filter(**lookup).delete()
        return Response({'program_id': program.id, 'saved': False}, status=status.HTTP_200_OK)


# -- Admin catalogue editor (/api/catalog/...) ---------------------------------
# The public catalogue endpoints above stay read-only and cached; these list
# every row (hidden ones too) a page at a time for the admin portal. Every
# product admin reads, ops and superadmins write (OPS_WRITE_ROUTES), and every
# write is audited. A save bumps the catalogue cache version (catalog_cache).

class CatalogAdminMixin(ListQueryMixin):
    permission_classes = [SupportReadOpsWrite]
    audit_name = ''

    def perform_create(self, serializer):
        audit_product_action(actor=self.request.user, action=f'{self.audit_name}.created', target=serializer.save())

    def perform_update(self, serializer):
        audit_product_action(actor=self.request.user, action=f'{self.audit_name}.updated', target=serializer.save())

    def perform_destroy(self, instance):
        with transaction.atomic():
            audit_product_action(actor=self.request.user, action=f'{self.audit_name}.deleted', target=instance)
            instance.delete()


# Hidden (is_active=False), never deleted: students save opportunity programs,
# and a hidden row can be shown again.
NO_DELETE = ['get', 'post', 'put', 'patch', 'head', 'options']


class CatalogUniversityViewSet(CatalogAdminMixin, viewsets.ModelViewSet):
    serializer_class = CatalogUniversitySerializer
    queryset = University.objects.annotate(
        programs_count=Count('programs', distinct=True),
        applications_count=Count('applications', distinct=True),
        scholarships_count=Count('scholarships', distinct=True),
    ).order_by('name', 'id')
    search_fields = ('name', 'city', 'country')
    ordering_options = {'name': ('name', 'id')}
    default_cursor_ordering = 'name'
    audit_name = 'university'

    def perform_destroy(self, instance):
        # Applications are deleted with their university, and linked scholarships
        # would silently become open to any university.
        if instance.applications.exists() or instance.scholarships.exists() or instance.programs.exists():
            raise ValidationError({'detail': ['This university has linked student applications, programs or scholarships. Edit it instead.']})
        super().perform_destroy(instance)


class CatalogProgramViewSet(CatalogAdminMixin, viewsets.ModelViewSet):
    serializer_class = CatalogProgramSerializer
    queryset = UniversityProgram.objects.select_related('university').order_by('name', 'id')
    search_fields = ('name', 'canonical_major', 'university__name')
    int_filters = {'university': 'university_id'}
    ordering_options = {'name': ('name', 'id')}
    default_cursor_ordering = 'name'
    audit_name = 'university_program'


class CatalogScholarshipViewSet(CatalogAdminMixin, viewsets.ModelViewSet):
    serializer_class = CatalogScholarshipSerializer
    queryset = Scholarship.objects.select_related('university').order_by('title', 'id')
    search_fields = ('title', 'provider')
    bool_filters = {'is_active': 'is_active'}
    ordering_options = {'title': ('title', 'id')}
    default_cursor_ordering = 'title'
    audit_name = 'scholarship'
    http_method_names = NO_DELETE


class CatalogOpportunityProgramViewSet(CatalogAdminMixin, viewsets.ModelViewSet):
    serializer_class = CatalogOpportunityProgramSerializer
    queryset = OpportunityProgram.objects.order_by('title', 'id')
    search_fields = ('title', 'provider', 'category', 'country')
    bool_filters = {'is_active': 'is_active'}
    ordering_options = {'title': ('title', 'id')}
    default_cursor_ordering = 'title'
    audit_name = 'opportunity_program'
    http_method_names = NO_DELETE


class StoreItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StoreItemSerializer
    permission_classes = [StudentPortalPermission]
    queryset = StoreItem.objects.filter(is_active=True)
