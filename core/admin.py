from django.contrib import admin
from .models import AuditLog, SystemConfig, Notification

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'user', 'ip_address', 'status', 'created_at')
    list_filter = ('action', 'status', 'created_at')
    search_fields = ('user__phone_number', 'user__first_name', 'user__last_name', 'ip_address', 'data')
    readonly_fields = ('id', 'user', 'action', 'ip_address', 'user_agent', 'data', 'status', 'error_message', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'value_type', 'is_public', 'updated_at')
    list_filter = ('value_type', 'is_public')
    search_fields = ('key', 'value', 'description')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__phone_number', 'title', 'message')
    readonly_fields = ('id', 'created_at', 'updated_at')
