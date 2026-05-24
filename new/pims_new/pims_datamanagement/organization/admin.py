from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Department, Designation, Division, Section, Unit


@admin.register(Department)
class DepartmentAdmin(ModelAdmin):
    list_display = ("name", "code", "head")
    search_fields = ("name", "code")
    autocomplete_fields = ("head",)


@admin.register(Division)
class DivisionAdmin(ModelAdmin):
    list_display = ("name", "department", "head")
    list_filter = ("department",)
    search_fields = ("name",)
    autocomplete_fields = ("department", "head")


@admin.register(Section)
class SectionAdmin(ModelAdmin):
    list_display = ("name", "department", "head")
    list_filter = ("department",)
    search_fields = ("name",)
    autocomplete_fields = ("department", "head")


@admin.register(Unit)
class UnitAdmin(ModelAdmin):
    list_display = ("name", "department", "head")
    list_filter = ("department",)
    search_fields = ("name",)
    autocomplete_fields = ("department", "head")


@admin.register(Designation)
class DesignationAdmin(ModelAdmin):
    list_display = ("name", "level")
    search_fields = ("name",)
    list_filter = ("level",)
