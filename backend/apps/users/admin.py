from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from . import entitlements
from .audit import (
    ACCOUNT_OWN_ROW_FIELDS,
    ProductAuditAdminMixin,
    account_update_metadata,
    audit_diff,
    audit_product_action,
    audit_snapshot,
    audit_subscription_change,
    subscription_audit_state,
)
from .models import CredentialAuditEvent, Plan, ProductAuditEvent, TemporaryCredential, User, WorkspaceSubscription
from .credentials import issue_temporary_credential


# Bookkeeping, not an account change: the password has its own form and audit
# trail, and the admin form drops date_joined's microseconds on every save.
ADMIN_UNAUDITED_FIELDS = ('password', 'last_login', 'password_changed_at', 'dashboard_layout', 'date_joined')


class SeatCheckedFormMixin:
    """Apply plan seat limits to Django-admin saves too.

    The admin wraps validation and save in one transaction, so the workspace
    lock taken here is held until the account row is written.
    """

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        previous = None
        if self.instance.pk:
            previous = User.objects.filter(pk=self.instance.pk).values_list('role', 'school_id', 'is_active').first()
            previous = entitlements.SeatState(*previous) if previous else None
        candidate = User(
            pk=self.instance.pk,
            role=cleaned.get('role', self.instance.role),
            school=cleaned.get('school', self.instance.school if self.instance.school_id else None),
            is_active=cleaned.get('is_active', self.instance.is_active),
        )
        try:
            entitlements.check_user_seat(candidate, previous=previous)
        except entitlements.EntitlementError as exc:
            self.add_error('school', exc.detail_message)
        return cleaned


class SeatCheckedUserChangeForm(SeatCheckedFormMixin, UserChangeForm):
    pass


class SeatCheckedUserCreationForm(SeatCheckedFormMixin, AdminUserCreationForm):
    pass


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    form = SeatCheckedUserChangeForm
    add_form = SeatCheckedUserCreationForm
    readonly_fields = UserAdmin.readonly_fields + ('password_changed_at',)
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'admin_tier', 'must_change_password', 'is_staff')
    list_filter = ('role', 'admin_tier', 'must_change_password', 'is_staff', 'is_superuser', 'is_active')
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Naseeb Edu Profile', {
            'fields': ('first_name', 'last_name', 'email', 'role', 'school', 'phone', 'position'),
        }),
    )
    fieldsets = UserAdmin.fieldsets + (
        ('Naseeb Edu Profile', {'fields': ('role', 'admin_tier', 'school', 'phone', 'position', 'avatar', 'must_change_password', 'password_changed_at')}),
    )

    def save_model(self, request, obj, form, change):
        # Admin access granted here starts at the lowest staff tier unless one is chosen.
        if obj.role == User.Role.ADMIN and not obj.is_superuser and not form.cleaned_data.get('admin_tier'):
            obj.admin_tier = User.AdminTier.SUPPORT
        # The form's changed fields, plus the tier, which the role or the line above may set.
        audited = set(form.changed_data) | {'admin_tier'}
        before = audit_snapshot(User.objects.get(pk=obj.pk), audited) if change else None
        super().save_model(request, obj, form, change)
        self._audit_account(request, obj, before)
        if change and 'school' in form.changed_data and obj.role != User.Role.STUDENT:
            from apps.admissions.models import School
            from apps.admissions.tenancy import user_left_school

            user_left_school(obj, School.objects.filter(pk=form.initial.get('school')).first())
        if obj.role != User.Role.STUDENT or obj.is_superuser:
            return
        from apps.admissions.services import ensure_student_profile

        ensure_student_profile(obj, actor=request.user)
        if not change and form.cleaned_data.get('password1'):
            issue_temporary_credential(
                user=obj,
                issued_by=request.user,
                raw_password=form.cleaned_data['password1'],
                request=request,
            )


    def _audit_account(self, request, account, before):
        """The same rows as an account change through the admin portal (UserViewSet)."""
        def audit(action, **metadata):
            audit_product_action(actor=request.user, action=action, target=account, metadata={'source': 'django_admin', **metadata})

        if before is None:
            audit('account.created', role=account.role, admin_tier=account.admin_tier)
            return
        changes = audit_diff(before, audit_snapshot(account, set(before)))
        for name in ADMIN_UNAUDITED_FIELDS:
            changes.pop(name, None)
        if 'school' in changes:
            audit('account.moved', from_school=changes['school']['from'], to_school=changes['school']['to'])
        if 'is_active' in changes:
            audit('account.reactivated' if account.is_active else 'account.deactivated')
        if 'admin_tier' in changes:
            audit('staff.tier_changed', changes={'admin_tier': changes['admin_tier']})
        other = {name: change for name, change in changes.items() if name not in ACCOUNT_OWN_ROW_FIELDS}
        if other:
            audit('account.updated', **account_update_metadata(other))


@admin.register(TemporaryCredential)
class TemporaryCredentialAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'issued_by', 'issued_at', 'expires_at', 'used_at')
    list_filter = ('status', 'issued_at', 'expires_at')
    search_fields = ('user__username', 'user__email', 'issued_by__username')
    readonly_fields = ('user', 'issued_by', 'status', 'issued_at', 'expires_at', 'used_at', 'revoked_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CredentialAuditEvent)
class CredentialAuditEventAdmin(admin.ModelAdmin):
    list_display = ('target_user', 'event', 'actor', 'credential', 'created_at')
    list_filter = ('event', 'created_at')
    search_fields = ('target_user__username', 'target_user__email', 'actor__username')
    readonly_fields = ('target_user', 'actor', 'event', 'credential', 'metadata', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProductAuditEvent)
class ProductAuditEventAdmin(admin.ModelAdmin):
    list_display = ('action', 'target_type', 'target_label', 'actor', 'created_at')
    list_filter = ('action', 'target_type', 'created_at')
    search_fields = ('target_label', 'target_id', 'actor__username')
    readonly_fields = ('actor', 'action', 'target_type', 'target_id', 'target_label', 'metadata', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Plan)
class PlanAdmin(ProductAuditAdminMixin, admin.ModelAdmin):
    audit_prefix = 'plan'
    list_display = ('name', 'code', 'max_counselors', 'max_students', 'max_teachers', 'is_active')
    search_fields = ('name', 'code')


@admin.register(WorkspaceSubscription)
class WorkspaceSubscriptionAdmin(ProductAuditAdminMixin, admin.ModelAdmin):
    # Same rows as a plan change made in the admin portal: on the School, plans by code.
    audit_prefix = 'subscription'
    audit_update_verb = 'changed'
    list_display = ('school', 'plan', 'status', 'period_start', 'period_end', 'updated_at')
    list_filter = ('status', 'plan')
    search_fields = ('school__name', 'school__code')
    raw_id_fields = ('school',)
    readonly_fields = ('updated_by', 'created_at', 'updated_at')

    def audit_target(self, obj):
        return obj.school

    def save_model(self, request, obj, form, change):
        if change:
            before = subscription_audit_state(WorkspaceSubscription.objects.select_related('plan').get(pk=obj.pk))
        else:
            before = dict.fromkeys(subscription_audit_state(obj))
        # The mixin's generic row is replaced by the API's subscription.changed row.
        super(ProductAuditAdminMixin, self).save_model(request, obj, form, change)
        audit_subscription_change(actor=request.user, before=before, subscription=obj, source='django_admin')

    def audit_metadata(self, obj):
        return {'plan': obj.plan.code if obj.plan_id else None}
