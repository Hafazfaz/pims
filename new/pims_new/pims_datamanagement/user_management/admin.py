from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Permission
from organization.models import Staff
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import CustomUser


class CustomUserAdminForm(UserCreationForm):
    can_set_urgent_priority = forms.BooleanField(
        required=False,
        label="Can mark documents as Urgent/High Priority",
    )

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ("can_set_urgent_priority",)

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            if self.cleaned_data.get("can_set_urgent_priority"):
                urgent_perm = Permission.objects.get(
                    content_type__app_label="user_management",
                    codename="can_set_urgent_priority",
                )
                user.user_permissions.add(urgent_perm)
            else:
                user.user_permissions.filter(
                    codename="can_set_urgent_priority",
                ).delete()
        return user


@admin.action(description="Unlock selected accounts")
def unlock_accounts(modeladmin, request, queryset):
    updated_count = queryset.filter(lockout_until__isnull=False).update(failed_login_attempts=0, lockout_until=None)
    updated_count += queryset.filter(failed_login_attempts__gt=0, lockout_until__isnull=True).update(
        failed_login_attempts=0
    )
    modeladmin.message_user(request, f"{updated_count} accounts were successfully unlocked.")


class CustomUserAdmin(ModelAdmin, UserAdmin):
    form = UserChangeForm
    add_form = CustomUserAdminForm
    change_password_form = AdminPasswordChangeForm
    fieldsets = (
        *UserAdmin.fieldsets,
        (None, {"fields": ("must_change_password", "failed_login_attempts", "lockout_until")}),
    )
    add_fieldsets = (
        *UserAdmin.add_fieldsets,
        (None, {"fields": ("must_change_password",)}),
        ("Permissions", {"fields": ("can_set_urgent_priority",)}),
    )
    list_display = (*UserAdmin.list_display, "must_change_password", "failed_login_attempts", "lockout_until")
    search_fields = ("username", "first_name", "last_name", "email")
    actions = [unlock_accounts]


admin.site.register(CustomUser, CustomUserAdmin)


class StaffAdmin(ModelAdmin):
    list_display = ("user", "designation", "department", "unit", "phone_number")
    search_fields = ("user__username", "user__first_name", "user__last_name", "designation__name", "department__name")
    list_filter = ("designation", "department", "unit")
    autocomplete_fields = ("user", "designation", "department", "unit")

    class Media:
        js = ("admin/js/filter_units_by_department.js",)


admin.site.register(Staff, StaffAdmin)
