from django.contrib import admin

from .models import StaffTelegramAccess


@admin.register(StaffTelegramAccess)
class StaffTelegramAccessAdmin(admin.ModelAdmin):
    list_display = ('telegram_username', 'user', 'created_by', 'updated_at')
    search_fields = ('telegram_username', 'user__username', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user', 'created_by')

    def save_model(self, request, obj, form, change):
        obj.telegram_username = str(obj.telegram_username or '').strip().lstrip('@').lower()
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
