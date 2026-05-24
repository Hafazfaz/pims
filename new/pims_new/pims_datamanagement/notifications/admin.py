from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ("user", "message", "is_read", "timestamp")
    list_filter = ("is_read",)
    search_fields = ("user__username", "message")
    readonly_fields = ("timestamp",)
