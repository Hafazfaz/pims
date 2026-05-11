from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.urls import reverse_lazy
from .models import Department, Unit, Designation, Division, Section
from .forms import DepartmentForm, UnitForm, DesignationForm, DivisionForm, SectionForm

class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser

class RegistryOrSuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return hasattr(user, 'staff') and user.staff.is_registry

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

@staff_member_required
def units_by_department(request):
    department_id = request.GET.get('department_id')
    units = Unit.objects.filter(department_id=department_id).order_by('name').values('id', 'name') if department_id else []
    return JsonResponse(list(units), safe=False)


# ── Department CRUD ──────────────────────────────────────────────────────────

class DepartmentCreateView(LoginRequiredMixin, SuperuserRequiredMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'organization/department_form.html'
    success_url = reverse_lazy('organization:department_list')

    def form_valid(self, form):
        messages.success(self.request, f'Department "{form.instance.name}" created.')
        return super().form_valid(form)


class DepartmentUpdateView(LoginRequiredMixin, SuperuserRequiredMixin, UpdateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'organization/department_form.html'
    success_url = reverse_lazy('organization:department_list')

    def form_valid(self, form):
        messages.success(self.request, f'Department "{form.instance.name}" updated.')
        return super().form_valid(form)


class DepartmentDeleteView(LoginRequiredMixin, SuperuserRequiredMixin, DeleteView):
    model = Department
    template_name = 'organization/department_confirm_delete.html'
    success_url = reverse_lazy('organization:department_list')

    def form_valid(self, form):
        messages.success(self.request, f'Department "{self.object.name}" deleted.')
        return super().form_valid(form)


# ── Unit CRUD ────────────────────────────────────────────────────────────────

class UnitCreateView(LoginRequiredMixin, SuperuserRequiredMixin, CreateView):
    model = Unit
    form_class = UnitForm
    template_name = 'organization/unit_form.html'
    success_url = reverse_lazy('organization:unit_list')

    def form_valid(self, form):
        messages.success(self.request, f'Unit "{form.instance.name}" created.')
        return super().form_valid(form)


class UnitUpdateView(LoginRequiredMixin, SuperuserRequiredMixin, UpdateView):
    model = Unit
    form_class = UnitForm
    template_name = 'organization/unit_form.html'
    success_url = reverse_lazy('organization:unit_list')

    def form_valid(self, form):
        messages.success(self.request, f'Unit "{form.instance.name}" updated.')
        return super().form_valid(form)


class UnitDeleteView(LoginRequiredMixin, SuperuserRequiredMixin, DeleteView):
    model = Unit
    template_name = 'organization/unit_confirm_delete.html'
    success_url = reverse_lazy('organization:unit_list')

    def form_valid(self, form):
        messages.success(self.request, f'Unit "{self.object.name}" deleted.')
        return super().form_valid(form)


# ── Designation CRUD ─────────────────────────────────────────────────────────

class DesignationListView(LoginRequiredMixin, SuperuserRequiredMixin, ListView):
    model = Designation
    context_object_name = 'designations'
    template_name = 'organization/designation_list.html'
    ordering = ['level']


class DesignationCreateView(LoginRequiredMixin, SuperuserRequiredMixin, CreateView):
    model = Designation
    form_class = DesignationForm
    template_name = 'organization/designation_form.html'
    success_url = reverse_lazy('organization:designation_list')

    def form_valid(self, form):
        messages.success(self.request, f'Designation "{form.instance.name}" created.')
        return super().form_valid(form)


class DesignationUpdateView(LoginRequiredMixin, SuperuserRequiredMixin, UpdateView):
    model = Designation
    form_class = DesignationForm
    template_name = 'organization/designation_form.html'
    success_url = reverse_lazy('organization:designation_list')

    def form_valid(self, form):
        messages.success(self.request, f'Designation "{form.instance.name}" updated.')
        return super().form_valid(form)


class DesignationDeleteView(LoginRequiredMixin, SuperuserRequiredMixin, DeleteView):
    model = Designation
    template_name = 'organization/designation_confirm_delete.html'
    success_url = reverse_lazy('organization:designation_list')

    def form_valid(self, form):
        messages.success(self.request, f'Designation "{self.object.name}" deleted.')
        return super().form_valid(form)


# ── Division CRUD ─────────────────────────────────────────────────────────────

class DivisionListView(LoginRequiredMixin, RegistryOrSuperuserRequiredMixin, ListView):
    model = Division
    context_object_name = 'divisions'
    template_name = 'organization/division_list.html'
    ordering = ['department__name', 'name']


class DivisionCreateView(LoginRequiredMixin, RegistryOrSuperuserRequiredMixin, CreateView):
    model = Division
    form_class = DivisionForm
    template_name = 'organization/division_form.html'
    success_url = reverse_lazy('organization:division_list')

    def form_valid(self, form):
        messages.success(self.request, f'Division "{form.instance.name}" created.')
        return super().form_valid(form)


class DivisionUpdateView(LoginRequiredMixin, RegistryOrSuperuserRequiredMixin, UpdateView):
    model = Division
    form_class = DivisionForm
    template_name = 'organization/division_form.html'
    success_url = reverse_lazy('organization:division_list')

    def form_valid(self, form):
        messages.success(self.request, f'Division "{form.instance.name}" updated.')
        return super().form_valid(form)


class DivisionDeleteView(LoginRequiredMixin, RegistryOrSuperuserRequiredMixin, DeleteView):
    model = Division
    template_name = 'organization/division_confirm_delete.html'
    success_url = reverse_lazy('organization:division_list')

    def form_valid(self, form):
        messages.success(self.request, f'Division "{self.object.name}" deleted.')
        return super().form_valid(form)

# ── Section CRUD ──────────────────────────────────────────────────────────────

class SectionListView(LoginRequiredMixin, RegistryOrSuperuserRequiredMixin, ListView):
    model = Section
    context_object_name = 'sections'
    template_name = 'organization/section_list.html'
    ordering = ['division__department__name', 'division__name', 'name']


class SectionCreateView(LoginRequiredMixin, RegistryOrSuperuserRequiredMixin, CreateView):
    model = Section
    form_class = SectionForm
    template_name = 'organization/section_form.html'
    success_url = reverse_lazy('organization:section_list')

    def form_valid(self, form):
        messages.success(self.request, f'Section "{form.instance.name}" created.')
        return super().form_valid(form)


class SectionUpdateView(LoginRequiredMixin, RegistryOrSuperuserRequiredMixin, UpdateView):
    model = Section
    form_class = SectionForm
    template_name = 'organization/section_form.html'
    success_url = reverse_lazy('organization:section_list')

    def form_valid(self, form):
        messages.success(self.request, f'Section "{form.instance.name}" updated.')
        return super().form_valid(form)


class SectionDeleteView(LoginRequiredMixin, RegistryOrSuperuserRequiredMixin, DeleteView):
    model = Section
    template_name = 'organization/section_confirm_delete.html'
    success_url = reverse_lazy('organization:section_list')

    def form_valid(self, form):
        messages.success(self.request, f'Section "{self.object.name}" deleted.')
        return super().form_valid(form)
