"""Admissions API views — catalog."""
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Prefetch, ProtectedError, Q, Subquery
from django.db.models.functions import Coalesce
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from apps.users.audit import field_changes
from apps.users.models import User
from core.exceptions import CodedError
from ..models import (
    Application,
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


NO_SCHOOL_ACCOUNTS = {
    'detail': 'An individual counselor workspace has no school accounts.',
    'code': 'individual_workspace_no_school_accounts',
}


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

    @staticmethod
    def forbidden(message):
        return Response({'detail': message, 'code': 'product_admin_required'}, status=403)

    def create(self, request, *args, **kwargs):
        if not self.can_manage(request.user):
            return self.forbidden('Only a product admin can create schools.')
        if 'account' not in request.data:
            return super().create(request, *args, **kwargs)
        # A school and its login are created together or not at all. It is audited
        # as two rows, school.created and organization_account.created, the same
        # rows as when the login is added later.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get('workspace_type') == School.WorkspaceType.INDIVIDUAL:
            return Response(NO_SCHOOL_ACCOUNTS, status=400)
        account = OrganizationAccountSerializer(data=request.data['account'], context={'request': request})
        if not account.is_valid():
            raise ValidationError({'account': account.errors})
        try:
            with transaction.atomic():
                school = serializer.save()
                audit_product_action(actor=request.user, action='school.created', target=school)
                entitlements.require_school_feature(school, 'organization_accounts')
                login = self._create_login(school, account)
        except entitlements.EntitlementError as exc:
            return Response(exc.response_data(), status=400)
        return Response({**self.get_serializer(school).data, 'account': login}, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        school = serializer.save()
        audit_product_action(actor=self.request.user, action='school.created', target=school)

    def update(self, request, *args, **kwargs):
        if not self.can_manage(request.user):
            return self.forbidden('Only a product admin can edit schools.')
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        previous_active = serializer.instance.is_active
        changes = field_changes(serializer.instance, serializer.validated_data)
        school = serializer.save()
        action_name = 'school.updated'
        if school.is_active != previous_active:
            action_name = 'school.reactivated' if school.is_active else 'school.deactivated'
            changes.pop('is_active', None)
        audit_product_action(actor=self.request.user, action=action_name, target=school, metadata={'changes': changes})

    def destroy(self, request, *args, **kwargs):
        if not self.can_manage(request.user):
            return self.forbidden('Only a product admin can deactivate schools.')
        school = self.get_object()
        school.is_active = False
        school.save(update_fields=['is_active', 'updated_at'])
        audit_product_action(actor=request.user, action='school.deactivated', target=school)
        return Response(status=204)

    def _create_login(self, school, serializer):
        """The school's organization login; runs inside the caller's transaction."""
        serializer.context['school'] = school
        user = serializer.save()
        audit_product_action(actor=self.request.user, action='organization_account.created', target=user, metadata={'school': school.pk})
        return {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'school': school.id,
            'school_name': school.name,
            # Shown once; only when the server generated it.
            'temporary_password': serializer.temporary_password,
            'credential': {'status': serializer.credential.status, 'expires_at': serializer.credential.expires_at},
        }

    @action(detail=True, methods=['post'], url_path='create-account')
    def create_account(self, request, pk=None):
        school = self.get_object()
        if not self.can_manage(request.user):
            return self.forbidden('Only a product admin can create organization accounts.')
        try:
            entitlements.require_school_feature(school, 'organization_accounts')
        except entitlements.EntitlementError as exc:
            return Response(exc.response_data(), status=400)
        if school.workspace_type == School.WorkspaceType.INDIVIDUAL:
            return Response(NO_SCHOOL_ACCOUNTS, status=400)
        serializer = OrganizationAccountSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            login = self._create_login(school, serializer)
        return Response(login, status=201)


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

    def perform_create(self, serializer):
        university = serializer.save()
        audit_product_action(actor=self.request.user, action='university.created', target=university)

    def perform_update(self, serializer):
        changes = field_changes(serializer.instance, serializer.validated_data)
        university = serializer.save()
        audit_product_action(
            actor=self.request.user, action='university.updated', target=university, metadata={'changes': changes},
        )

    def perform_destroy(self, instance):
        # Recorded before the row goes, so the event keeps the university's id.
        with transaction.atomic():
            audit_product_action(actor=self.request.user, action='university.deleted', target=instance)
            instance.delete()


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

# A changed text longer than this is recorded cut short; a changed JSON field
# (qs_data, source_metadata) records only which of its keys changed.
AUDIT_TEXT_LIMIT = 200


def _audit_value(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text if len(text) <= AUDIT_TEXT_LIMIT else f'{text[:AUDIT_TEXT_LIMIT]}…'


def _field_values(instance):
    return {field.attname: getattr(instance, field.attname) for field in instance._meta.concrete_fields}


def audit_changes(before, after):
    """{field: [before, after]} for every changed field, kept small for the audit log."""
    changes = {}
    for name, old in before.items():
        new = after.get(name)
        if name == 'updated_at' or old == new:
            continue
        if isinstance(old, (dict, list)) or isinstance(new, (dict, list)):
            old_map = old if isinstance(old, dict) else {}
            new_map = new if isinstance(new, dict) else {}
            changes[name] = {'changed_keys': sorted(str(key) for key in set(old_map) | set(new_map) if old_map.get(key) != new_map.get(key))}
        else:
            changes[name] = [_audit_value(old), _audit_value(new)]
    return changes


class CatalogAdminMixin(ListQueryMixin):
    permission_classes = [SupportReadOpsWrite]
    audit_name = ''

    # A write and its audit row commit together, or neither does.
    def perform_create(self, serializer):
        with transaction.atomic():
            audit_product_action(actor=self.request.user, action=f'{self.audit_name}.created', target=serializer.save())

    def perform_update(self, serializer):
        with transaction.atomic():
            before = _field_values(serializer.instance)
            instance = serializer.save()
            audit_product_action(
                actor=self.request.user, action=f'{self.audit_name}.updated', target=instance,
                metadata={'changes': audit_changes(before, _field_values(instance))},
            )

    def perform_destroy(self, instance):
        with transaction.atomic():
            audit_product_action(actor=self.request.user, action=f'{self.audit_name}.deleted', target=instance)
            instance.delete()


# Hidden (is_active=False), never deleted: students save opportunity programs,
# and a hidden row can be shown again.
NO_DELETE = ['get', 'post', 'put', 'patch', 'head', 'options']


UNIVERSITY_IN_USE_MESSAGE = 'This university has linked student applications, programs or scholarships. Edit it instead.'


def linked_count(model):
    """Rows of ``model`` pointing at the university, one small subquery each (no join fan-out)."""
    rows = model.objects.filter(university=OuterRef('pk')).order_by().values('university').annotate(total=Count('pk')).values('total')
    return Coalesce(Subquery(rows, output_field=IntegerField()), 0)


class CatalogUniversityViewSet(CatalogAdminMixin, viewsets.ModelViewSet):
    serializer_class = CatalogUniversitySerializer
    queryset = University.objects.annotate(
        programs_count=linked_count(UniversityProgram),
        applications_count=linked_count(Application),
        scholarships_count=linked_count(Scholarship),
    ).order_by('name', 'id')
    search_fields = ('name', 'city', 'country')
    ordering_options = {'name': ('name', 'id')}
    default_cursor_ordering = 'name'
    audit_name = 'university'

    def perform_destroy(self, instance):
        # Linked scholarships would silently become open to any university, and
        # programs would go with it. The row lock makes a concurrent insert that
        # references this university (which takes a key-share lock on it) wait
        # until the check and the delete are done; Application.university is
        # PROTECT, so the database refuses whatever slips past.
        in_use = CodedError(UNIVERSITY_IN_USE_MESSAGE, 'university_in_use', status.HTTP_409_CONFLICT)
        with transaction.atomic():
            university = University.objects.select_for_update().get(pk=instance.pk)
            if (
                Application.objects.filter(university=university).exists()
                or Scholarship.objects.filter(university=university).exists()
                or UniversityProgram.objects.filter(university=university).exists()
            ):
                raise in_use
            audit_product_action(actor=self.request.user, action=f'{self.audit_name}.deleted', target=university)
            try:
                university.delete()
            except ProtectedError:
                raise in_use from None


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
