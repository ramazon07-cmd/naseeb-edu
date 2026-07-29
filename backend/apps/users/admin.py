from django.contrib import admin
from django.apps import apps
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Naseeb Edu Profile', {
            'fields': ('first_name', 'last_name', 'email', 'role', 'school', 'phone', 'position'),
        }),
    )
    fieldsets = UserAdmin.fieldsets + (
        ('Naseeb Edu Profile', {'fields': ('role', 'school', 'phone', 'position', 'avatar')}),
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
