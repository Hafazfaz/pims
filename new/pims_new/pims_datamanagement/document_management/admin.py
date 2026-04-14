from django.contrib import admin
from .models import File, Document, FileMovement, FileAccessRequest


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ('file_number', 'title', 'file_type', 'status', 'owner', 'department', 'created_at')
    list_filter = ('status', 'file_type', 'department')
    search_fields = ('file_number', 'title', 'owner__user__username')
    readonly_fields = ('file_number', 'created_at')
    autocomplete_fields = ('owner', 'current_location', 'department', 'created_by')


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'file', 'uploaded_by', 'status', 'uploaded_at')
    list_filter = ('status',)
    search_fields = ('title', 'file__file_number', 'uploaded_by__username')
    readonly_fields = ('uploaded_at',)
    autocomplete_fields = ('file', 'uploaded_by', 'shared_with')


@admin.register(FileMovement)
class FileMovementAdmin(admin.ModelAdmin):
    list_display = ('file', 'sent_by', 'sent_to', 'action', 'moved_at')
    list_filter = ('action',)
    search_fields = ('file__file_number', 'sent_by__user__username', 'sent_to__user__username')
    readonly_fields = ('moved_at',)
    autocomplete_fields = ('file', 'sent_by', 'sent_to', 'from_location')


@admin.register(FileAccessRequest)
class FileAccessRequestAdmin(admin.ModelAdmin):
    list_display = ('file', 'requested_by', 'access_type', 'status', 'created_at', 'expires_at')
    list_filter = ('status', 'access_type')
    search_fields = ('file__file_number', 'requested_by__username')
    readonly_fields = ('created_at', 'approved_at', 'expires_at')
    autocomplete_fields = ('file', 'requested_by')
