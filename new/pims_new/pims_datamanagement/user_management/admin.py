from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from .models import CustomUser
from organization.models import Staff # Import Staff from organization app


@admin.action(description='Unlock selected accounts')
def unlock_accounts(modeladmin, request, queryset):
    # Filter for accounts that are currently locked or have failed attempts
    # and then unlock them.
    updated_count = queryset.filter(
        lockout_until__isnull=False
    ).update(failed_login_attempts=0, lockout_until=None)

    # Also update accounts that might have failed attempts but aren't yet locked out
    # to clear their failed attempts count.
    updated_count += queryset.filter(
        failed_login_attempts__gt=0, lockout_until__isnull=True
    ).update(failed_login_attempts=0)

    modeladmin.message_user(request, f"{updated_count} accounts were successfully unlocked.")


class CustomUserAdmin(UserAdmin):
    # Add 'must_change_password', 'failed_login_attempts', 'lockout_until' to fieldsets and list_display
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('must_change_password', 'failed_login_attempts', 'lockout_until',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('must_change_password',)}), # failed_login_attempts and lockout_until are not needed on add form
    )
    list_display = UserAdmin.list_display + ('must_change_password', 'failed_login_attempts', 'lockout_until',)
    actions = [unlock_accounts] # Register the admin action

admin.site.register(CustomUser, CustomUserAdmin)

class StaffAdmin(admin.ModelAdmin):
    list_display = ('user', 'designation', 'department', 'unit', 'phone_number')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'designation__name', 'department__name')
    list_filter = ('designation', 'department', 'unit')

admin.site.register(Staff, StaffAdmin)