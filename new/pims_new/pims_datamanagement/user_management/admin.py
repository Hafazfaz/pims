from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser
from organization.models import Staff # Import Staff from organization app

class CustomUserAdmin(UserAdmin):
    # Add 'must_change_password' to fieldsets and list_display
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('must_change_password',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('must_change_password',)}),
    )
    list_display = UserAdmin.list_display + ('must_change_password',)

admin.site.register(CustomUser, CustomUserAdmin)

class StaffAdmin(admin.ModelAdmin):
    list_display = ('user', 'designation', 'department', 'unit', 'phone_number')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'designation__name', 'department__name')
    list_filter = ('designation', 'department', 'unit')

admin.site.register(Staff, StaffAdmin)