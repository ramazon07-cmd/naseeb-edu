from django.contrib import admin
from django.apps import apps
from django.contrib.auth.admin import UserAdmin
from .models import CredentialAuditEvent, ProductAuditEvent, TemporaryCredential, User
from .credentials import issue_temporary_credential


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    readonly_fields = UserAdmin.readonly_fields + ('password_changed_at',)
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'must_change_password', 'is_staff')
    list_filter = ('role', 'must_change_password', 'is_staff', 'is_superuser', 'is_active')
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Naseeb Edu Profile', {
            'fields': ('first_name', 'last_name', 'email', 'role', 'school', 'phone', 'position'),
        }),
    )
    fieldsets = UserAdmin.fieldsets + (
        ('Naseeb Edu Profile', {'fields': ('role', 'school', 'phone', 'position', 'avatar', 'must_change_password', 'password_changed_at')}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.role != User.Role.STUDENT or obj.is_superuser:
            return
        StudentProfile = apps.get_model('admissions', 'StudentProfile')
        defaults = {
            'school_id': obj.school_id,
            'school_name': obj.school.name if obj.school_id else 'Naseeb Edu',
        }
        profile, created = StudentProfile.objects.get_or_create(user=obj, defaults=defaults)
        if not created and obj.school_id and profile.school_id != obj.school_id:
            profile.school_id = obj.school_id
            profile.school_name = obj.school.name
            profile.save(update_fields=['school', 'school_name', 'updated_at'])
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
