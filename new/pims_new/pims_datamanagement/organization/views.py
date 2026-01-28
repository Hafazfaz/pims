from django.shortcuts import render
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .models import Department, Unit

class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser

class DepartmentListView(LoginRequiredMixin, SuperuserRequiredMixin, ListView):
    model = Department
    context_object_name = 'departments'
    paginate_by = 10
    ordering = ['name']

    def get_template_names(self):
        return ['organization/department_list.html']

class DepartmentDetailView(LoginRequiredMixin, SuperuserRequiredMixin, DetailView):
    model = Department
    context_object_name = 'department'

    def get_template_names(self):
        return ['organization/department_detail.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add paginated units for this department
        from django.core.paginator import Paginator
        unit_list = self.object.units.all().order_by('name')
        paginator = Paginator(unit_list, 10)
        page = self.request.GET.get('page')
        context['units'] = paginator.get_page(page)
        return context

class UnitListView(LoginRequiredMixin, SuperuserRequiredMixin, ListView):
    model = Unit
    context_object_name = 'units'
    paginate_by = 20
    ordering = ['department__name', 'name']

    def get_template_names(self):
        return ['organization/unit_list.html']
