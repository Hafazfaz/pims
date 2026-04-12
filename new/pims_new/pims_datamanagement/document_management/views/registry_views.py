from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin
from django.views.generic import ListView, View
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.contrib import messages
from django.db.models import Q
from audit_log.models import AuditLogEntry
from audit_log.utils import log_action
from organization.models import Staff, Department, Unit
from core.constants import FILE_TYPE_CHOICES
from ..models import File, FileAccessRequest
from .base import HTMXLoginRequiredMixin, RegistryRequiredMixin

class RegistryHubView(RegistryRequiredMixin, ListView):
    model = File
    template_name = "document_management/registry_hub.html"
    context_object_name = "files"
    paginate_by = 15

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")

        queryset = File.objects.all()

        search_query = self.request.GET.get("q")
        file_type = self.request.GET.get("file_type")
        status = self.request.GET.get("status")

        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query)
                | Q(file_number__icontains=search_query)
            )
        if file_type:
            queryset = queryset.filter(file_type=file_type)
        if status:
            queryset = queryset.filter(status=status)

        department_filter = self.request.GET.get("department")
        unit_filter = self.request.GET.get("unit")
        
        if department_filter:
            queryset = queryset.filter(department_id=department_filter)
        if unit_filter:
            queryset = queryset.filter(owner__unit_id=unit_filter)

        if status != "archived":
            queryset = queryset.exclude(status="archived")

        return queryset.order_by("-created_at")

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            target = self.request.headers.get("HX-Target")
            if target == "outgoing-file-list":
                return ["document_management/partials/_registry_outgoing_list.html"]
            return ["document_management/partials/_registry_file_list.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")

        base_scope = Q()

        context["pending_activation_files"] = File.objects.filter(base_scope, status="pending_activation").order_by("-created_at")
        context["archived_files"] = File.objects.filter(base_scope, status="archived").order_by("-created_at")

        context["all_file_types"] = FILE_TYPE_CHOICES
        context["selected_search_query"] = self.request.GET.get("q", "")
        context["selected_file_type"] = self.request.GET.get("file_type", "")
        context["selected_status"] = self.request.GET.get("status", "")

        context["all_departments"] = Department.objects.all().order_by("name")
        context["all_units"] = Unit.objects.all().order_by("name")
        context["selected_department"] = self.request.GET.get("department") and int(self.request.GET.get("department"))
        context["selected_unit"] = self.request.GET.get("unit") and int(self.request.GET.get("unit"))

        if staff_user.is_registry:
            context["pending_access_requests"] = FileAccessRequest.objects.filter(status='pending').order_by('-created_at')
            
            registry_staff_ids = Staff.objects.filter(
                Q(designation__name__icontains='registry') | 
                Q(user__groups__name__iexact='Registry')
            ).values_list('id', flat=True)
            
            outgoing_qs = File.objects.filter(
                status='active'
            ).exclude(
                Q(current_location__isnull=True) | Q(current_location__id__in=registry_staff_ids)
            ).select_related('current_location', 'owner', 'department')
            
            q_outgoing = self.request.GET.get("q_outgoing")
            if q_outgoing:
                outgoing_qs = outgoing_qs.filter(
                    Q(title__icontains=q_outgoing) | 
                    Q(file_number__icontains=q_outgoing) |
                    Q(current_location__user__username__icontains=q_outgoing) |
                    Q(current_location__user__first_name__icontains=q_outgoing) |
                    Q(current_location__user__last_name__icontains=q_outgoing)
                )
            context["selected_outgoing_query"] = q_outgoing or ""

            outgoing_files_subset = outgoing_qs.order_by('-created_at')[:50]
            
            outgoing_list = []
            overdue_count = 0
            for file in outgoing_files_subset:
                custody_duration = file.get_custody_duration()
                is_overdue = file.is_overdue()
                outgoing_list.append({
                    'file': file,
                    'custody_duration': custody_duration,
                    'is_overdue': is_overdue
                })
                if is_overdue:
                    overdue_count += 1
            
            context["outgoing_files"] = outgoing_list
            context["outgoing_files_count"] = len(outgoing_list)
            context["outgoing_overdue_count"] = overdue_count
            
            context["total_files_count"] = File.objects.filter(status='active').count()
            
            today = timezone.now().date()
            context["docs_added_today"] = AuditLogEntry.objects.filter(action='DOCUMENT_ADDED', timestamp__date=today).count()
            context["files_created_today"] = AuditLogEntry.objects.filter(action='FILE_CREATED', timestamp__date=today).count()
            context["actions_today"] = AuditLogEntry.objects.filter(timestamp__date=today).count()
            
            context["recent_activities"] = AuditLogEntry.objects.select_related('user').all()[:15]
            
            context["total_staff_count"] = Staff.objects.count()
            context["total_departments_count"] = Department.objects.count()

            staff_with_files = File.objects.filter(
                file_type='personal'
            ).values_list('owner_id', flat=True).distinct()

            context["staff_without_files_count"] = Staff.objects.exclude(
                id__in=staff_with_files
            ).count()

        return context

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None


class RegistryDashboardView(RegistryRequiredMixin, ListView):
    model = File
    template_name = "document_management/registry_analytics.html"
    context_object_name = "files"

    def get_queryset(self):
        return File.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")

        today = timezone.now().date()
        
        context["total_files_count"] = File.objects.filter(status='active').count()
        context["pending_activation_count"] = File.objects.filter(status='pending_activation').count()
        context["archived_files_count"] = File.objects.filter(status='archived').count()
        
        registry_staff_ids = Staff.objects.filter(
            Q(designation__name__icontains='registry') | 
            Q(user__groups__name__iexact='Registry')
        ).values_list('id', flat=True)
        
        outgoing_files = File.objects.filter(status='active').exclude(
            Q(current_location__isnull=True) | Q(current_location__id__in=registry_staff_ids)
        )
        context["outgoing_files_count"] = outgoing_files.count()
        
        overdue_count = 0
        for f in outgoing_files:
            if f.is_overdue():
                overdue_count += 1
        context["outgoing_overdue_count"] = overdue_count

        context["docs_added_today"] = AuditLogEntry.objects.filter(action='DOCUMENT_ADDED', timestamp__date=today).count()
        context["files_created_today"] = AuditLogEntry.objects.filter(action='FILE_CREATED', timestamp__date=today).count()
        context["actions_today"] = AuditLogEntry.objects.filter(timestamp__date=today).count()
        
        context["total_staff_count"] = Staff.objects.count()
        context["total_departments_count"] = Department.objects.count()
        
        staff_with_files = File.objects.filter(file_type='personal').values_list('owner_id', flat=True).distinct()
        context["staff_without_files_count"] = Staff.objects.exclude(id__in=staff_with_files).count()

        return context

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None        

class StaffWithoutFilesView(RegistryRequiredMixin, ListView):
    model = Staff
    template_name = "document_management/staff_without_files.html"
    context_object_name = "staff_list"
    paginate_by = 20

    def get_queryset(self):
        staff_with_files = File.objects.filter(
            file_type='personal'
        ).values_list('owner_id', flat=True).distinct()
        
        queryset = Staff.objects.exclude(
            id__in=staff_with_files
        ).select_related('user', 'department', 'unit').order_by('user__last_name')
        
        search_query = self.request.GET.get('q')
        if search_query:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search_query) |
                Q(user__last_name__icontains=search_query) |
                Q(user__username__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_count"] = self.get_queryset().count()
        context["search_query"] = self.request.GET.get('q', '')
        return context

class FileApproveActivationView(RegistryRequiredMixin, View):

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        if file_obj.status != 'pending_activation':
            messages.error(request, "File is not pending activation.")
            return redirect('document_management:registry_hub')

        file_obj.status = 'active'
        file_obj.save()

        log_action(request.user, "FILE_ACTIVATED", request=request, obj=file_obj)
        messages.success(request, f"File {file_obj.file_number} has been activated.")
        
        if request.headers.get("HX-Request"):
            return render(request, "document_management/partials/_registry_file_status.html", {"file": file_obj})
            
        return redirect('document_management:registry_hub')
