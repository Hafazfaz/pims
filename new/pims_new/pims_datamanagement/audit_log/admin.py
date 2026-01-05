from django.contrib import admin
from .models import AuditLogEntry

@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp', 'user', 'action', 'ip_address', 'content_object', 'details'
    )
    list_filter = ('action', 'user', 'timestamp')
    search_fields = (
        'user__username', 'action', 'ip_address', 'user_agent', 'details'
    )
    date_hierarchy = 'timestamp'
    readonly_fields = (
        'timestamp', 'user', 'action', 'ip_address', 'user_agent',
        'content_type', 'object_id', 'content_object', 'details'
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
