from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from . import entitlements
from .models import CredentialAuditEvent, Plan, ProductAuditEvent, TemporaryCredential, User, WorkspaceSubscription
from .credentials import issue_temporary_credential


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
        super().save_model(request, obj, form, change)
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
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'max_counselors', 'max_students', 'max_teachers', 'is_active')
    search_fields = ('name', 'code')


@admin.register(WorkspaceSubscription)
class WorkspaceSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('school', 'plan', 'status', 'period_start', 'period_end', 'updated_at')
    list_filter = ('status', 'plan')
    search_fields = ('school__name', 'school__code')
    raw_id_fields = ('school',)
    readonly_fields = ('updated_by', 'created_at', 'updated_at')
