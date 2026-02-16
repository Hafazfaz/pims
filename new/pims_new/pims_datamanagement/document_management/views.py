from audit_log.utils import log_action  # Import audit logging utility
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.auth.mixins import (LoginRequiredMixin,
                                        PermissionRequiredMixin,
                                        UserPassesTestMixin)
from django.db.models import Q, Prefetch
from django.http import Http404, HttpResponse
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import (CreateView, DetailView, ListView, UpdateView,
                                  View, TemplateView)
from notifications.utils import \
    create_notification  # Import notification utility
from organization.models import Staff

from .forms import (DocumentForm, DocumentUploadForm, FileForm, FileUpdateForm,
                    SendFileForm)
from .models import Document, File, FileAccessRequest
from django.utils import timezone
from datetime import timedelta
from django.utils import timezone
from audit_log.models import AuditLogEntry
from organization.models import Department, Staff, Unit
from core.constants import FILE_TYPE_CHOICES, STATUS_CHOICES


from django.urls import reverse_lazy


class HTMXLoginRequiredMixin(LoginRequiredMixin):
    """
    Forces a full page redirect to the login page for HTMX requests
    when the user is not authenticated.
    """
    def handle_no_permission(self):
        if self.request.headers.get("HX-Request"):
            response = HttpResponse()
            # Redirect to login page and let it redirect back to current page
            response["HX-Redirect"] = str(reverse_lazy("user_management:login"))
            return response
        return super().handle_no_permission()


class RegistryHubView(HTMXLoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = File
    template_name = "document_management/registry_hub.html"
    context_object_name = "files"
    permission_required = "document_management.view_file"
    paginate_by = 15

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        
        if not staff_user.is_registry:
            raise PermissionDenied("Only registry users can access the registry hub.")

        # Registry users see all files
        queryset = File.objects.all()

        # Apply search filters
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

        # New Hierarchy Filters
        department_filter = self.request.GET.get("department")
        unit_filter = self.request.GET.get("unit")
        
        if department_filter:
            queryset = queryset.filter(department_id=department_filter)
        if unit_filter:
            queryset = queryset.filter(owner__unit_id=unit_filter)

        # Exclude archived files from the main list by default, but allow explicit search
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

        # Base Filter Scope for summaries (registry sees all)
        base_scope = Q()

        # Pending activation files and archived files
        context["pending_activation_files"] = File.objects.filter(base_scope, status="pending_activation").order_by("-created_at")
        context["archived_files"] = File.objects.filter(base_scope, status="archived").order_by("-created_at")

        context["all_file_types"] = FILE_TYPE_CHOICES
        context["selected_search_query"] = self.request.GET.get("q", "")
        context["selected_file_type"] = self.request.GET.get("file_type", "")
        context["selected_status"] = self.request.GET.get("status", "")

        # New Filter Options
        context["all_departments"] = Department.objects.all().order_by("name")
        context["all_units"] = Unit.objects.all().order_by("name")
        context["selected_department"] = self.request.GET.get("department") and int(self.request.GET.get("department"))
        context["selected_unit"] = self.request.GET.get("unit") and int(self.request.GET.get("unit"))

        # Pending Access Requests (Registry only)
        if staff_user.is_registry:
            context["pending_access_requests"] = FileAccessRequest.objects.filter(status='pending').order_by('-created_at')
            
            # Outgoing Files Tracking
            registry_staff_ids = Staff.objects.filter(
                Q(designation__name__icontains='registry') | 
                Q(user__groups__name__iexact='Registry')
            ).values_list('id', flat=True)
            
            outgoing_qs = File.objects.filter(
                status='active'
            ).exclude(
                Q(current_location__isnull=True) | Q(current_location__id__in=registry_staff_ids)
            ).select_related('current_location', 'owner', 'department')
            
            # Outgoing Search Logic
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
            
            # Total files and staff without files metrics
            context["total_files_count"] = File.objects.filter(status='active').count()
            
            # Daily Activity Metrics
            today = timezone.now().date()
            context["docs_added_today"] = AuditLogEntry.objects.filter(action='DOCUMENT_ADDED', timestamp__date=today).count()
            context["files_created_today"] = AuditLogEntry.objects.filter(action='FILE_CREATED', timestamp__date=today).count()
            context["actions_today"] = AuditLogEntry.objects.filter(timestamp__date=today).count()
            
            # Recent System Activity
            context["recent_activities"] = AuditLogEntry.objects.select_related('user').all()[:15]
            
            # Global Counts
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
            staff = Staff.objects.get(user=user)
            return staff
        except Staff.DoesNotExist:
            return None

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(
            self.request, "You do not have permission to access the registry dashboard."
        )
        return redirect("document_management:my_files")



class RegistryDashboardView(HTMXLoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = File
    template_name = "document_management/registry_analytics.html"
    context_object_name = "files"
    permission_required = "document_management.view_file"

    def get_queryset(self):
        # We don't really need a queryset for the analytics view, just metrics
        return File.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
            
        if not staff_user.is_registry:
            raise PermissionDenied("Only registry users can access the registry analytics.")

        today = timezone.now().date()
        
        # High Level Metrics
        context["total_files_count"] = File.objects.filter(status='active').count()
        context["pending_activation_count"] = File.objects.filter(status='pending_activation').count()
        context["archived_files_count"] = File.objects.filter(status='archived').count()
        
        # Outgoing/Overdue Metrics
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

        # Daily Action Velocity
        context["docs_added_today"] = AuditLogEntry.objects.filter(action='DOCUMENT_ADDED', timestamp__date=today).count()
        context["files_created_today"] = AuditLogEntry.objects.filter(action='FILE_CREATED', timestamp__date=today).count()
        context["actions_today"] = AuditLogEntry.objects.filter(timestamp__date=today).count()
        
        # Global Counts
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


class StaffWithoutFilesView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Staff
    template_name = "document_management/staff_without_files.html"
    context_object_name = "staff_list"
    permission_required = "document_management.view_file"
    paginate_by = 20

    def get_queryset(self):
        # Staff who don't have any files of type 'personal' linked to them as owner
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


class ExecutiveDashboardView(HTMXLoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    Comprehensive dashboard for executives, HODs, and unit managers.
    Shows department/unit-specific metrics based on role.
    """
    template_name = "document_management/executive_dashboard.html"
    permission_required = "document_management.view_file"

    def test_func(self):
        staff_user = self.get_staff_user()
        return staff_user and (staff_user.is_hod or staff_user.is_unit_manager or self.request.user.is_superuser)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_user = self.get_staff_user()
        
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        
        if not (staff_user.is_hod or staff_user.is_unit_manager or self.request.user.is_superuser):
            raise PermissionDenied("Only executives, HODs, and unit managers can access this dashboard.")

        today = timezone.now().date()
        
        # Determine scope based on role
        if self.request.user.is_superuser:
            # Superusers (Directors) see everything
            scope_filter = Q()
            context['scope_title'] = 'Organization-Wide'
        elif staff_user.is_hod:
            # HODs see their department
            scope_filter = Q(department=staff_user.department)
            context['scope_title'] = f'{staff_user.department.name} Department'
        elif staff_user.is_unit_manager:
            # Unit managers see their unit
            scope_filter = Q(owner__unit=staff_user.unit)
            context['scope_title'] = f'{staff_user.unit.name} Unit'
        else:
            scope_filter = Q(owner=staff_user)
            context['scope_title'] = 'Personal'

        # File Statistics
        context['total_files'] = File.objects.filter(scope_filter).count()
        context['active_files'] = File.objects.filter(scope_filter, status='active').count()
        context['pending_activation'] = File.objects.filter(scope_filter, status='pending_activation').count()
        context['closed_files'] = File.objects.filter(scope_filter, status='closed').count()
        context['archived_files'] = File.objects.filter(scope_filter, status='archived').count()

        # Files by type
        context['personal_files_count'] = File.objects.filter(scope_filter, file_type='personal').count()
        context['policy_files_count'] = File.objects.filter(scope_filter, file_type='policy').count()

        # Overdue Files (files not with registry that have been out > 2 days)
        registry_staff_ids = Staff.objects.filter(
            Q(designation__name__icontains='registry') | 
            Q(user__groups__name__iexact='Registry')
        ).values_list('id', flat=True)
        
        outgoing_files = File.objects.filter(
            scope_filter,
            status='active'
        ).exclude(
            Q(current_location__isnull=True) | Q(current_location__id__in=registry_staff_ids)
        ).select_related('current_location', 'owner', 'department')
        
        overdue_list = []
        for f in outgoing_files:
            if f.is_overdue():
                overdue_list.append({
                    'file': f,
                    'custody_duration': f.get_custody_duration()
                })
        
        context['overdue_files'] = overdue_list[:10]  # Top 10 overdue
        context['overdue_count'] = len(overdue_list)
        context['outgoing_files_count'] = outgoing_files.count()

        # Recent File Activity (last 10 files created/updated)
        context['recent_files'] = File.objects.filter(scope_filter).order_by('-created_at')[:10]

        # Document Velocity
        context['docs_added_today'] = Document.objects.filter(
            file__in=File.objects.filter(scope_filter),
            uploaded_at__date=today
        ).count()
        
        context['files_created_this_week'] = File.objects.filter(
            scope_filter,
            created_at__gte=today - timedelta(days=7)
        ).count()

        # Staff Performance (for HODs and Unit Managers)
        if staff_user.is_hod:
            # Count staff in department
            context['total_staff'] = Staff.objects.filter(department=staff_user.department).count()
            
            # Staff with files
            staff_with_files = File.objects.filter(
                scope_filter,
                file_type='personal'
            ).values_list('owner_id', flat=True).distinct()
            
            context['staff_with_files_count'] = len(staff_with_files)
            context['staff_without_files_count'] = context['total_staff'] - context['staff_with_files_count']
        
        elif staff_user.is_unit_manager:
            # Count staff in unit
            context['total_staff'] = Staff.objects.filter(unit=staff_user.unit).count()
            
            # Staff with files
            staff_with_files = File.objects.filter(
                scope_filter,
                file_type='personal'
            ).values_list('owner_id', flat=True).distinct()
            
            context['staff_with_files_count'] = len(staff_with_files)
            context['staff_without_files_count'] = context['total_staff'] - context['staff_with_files_count']

        # Pending Access Requests for their scope
        context['pending_access_requests'] = FileAccessRequest.objects.filter(
            file__in=File.objects.filter(scope_filter),
            status='pending'
        ).order_by('-created_at')[:5]

        return context

    def get_staff_user(self):
        user = self.request.user
        try:
            staff = Staff.objects.get(user=user)
            return staff
        except Staff.DoesNotExist:
            return None

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(
            self.request, "You do not have permission to access the executive dashboard."
        )
        return redirect("document_management:my_files")


class HODDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = File
    template_name = "document_management/hod_dashboard.html"
    context_object_name = "files"

    def test_func(self):
        staff_user = self.get_staff_user()
        return staff_user and (staff_user.is_hod or staff_user.is_unit_manager or self.request.user.is_superuser)

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")

        # HODs see all non-archived files in their department
        return (
            File.objects.filter(department=staff_user.department)
            .exclude(status="archived")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")

        department_files = File.objects.filter(department=staff_user.department)
        context["all_files_count"] = department_files.count()
        context["active_files_count"] = department_files.filter(status="active").count()
        context["closed_files_count"] = department_files.filter(status="closed").count()
        context["archived_files_count"] = department_files.filter(status="archived").count()

        # Custody notifications for HOD/Unit Manager
        if staff_user.is_unit_manager:
            # Unit managers see files in their unit
            custody_files = File.objects.filter(
                current_location__unit=staff_user.unit,
                status='active'
            ).exclude(current_location=None).select_related('current_location', 'owner').order_by('-created_at')
        else:
            # HODs see files in their department
            custody_files = File.objects.filter(
                current_location__department=staff_user.department,
                status='active'
            ).exclude(current_location=None).select_related('current_location', 'owner').order_by('-created_at')
        
        # Add custody duration to each file
        custody_list = []
        overdue_count = 0
        for file in custody_files:
            custody_duration = file.get_custody_duration()
            is_overdue = file.is_overdue()
            custody_list.append({
                'file': file,
                'custody_duration': custody_duration,
                'is_overdue': is_overdue
            })
            if is_overdue:
                overdue_count += 1
        
        context["custody_files"] = custody_list
        context["custody_files_count"] = len(custody_list)
        context["overdue_files_count"] = overdue_count

        return context

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(
            self.request, "You do not have permission to access the HOD dashboard."
        )
        return redirect("document_management:my_files")


class FileCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = File
    form_class = FileForm
    template_name = "document_management/file_form.html"
    
    def test_func(self):
        user = self.request.user
        try:
            return user.staff.is_registry or user.is_superuser
        except AttributeError:
            return False
    
    def get_success_url(self):
        try:
            staff = self.request.user.staff
            if "registry" in staff.designation.name.lower() if staff.designation else False:
                return reverse_lazy("document_management:registry_hub")
        except Staff.DoesNotExist:
            pass
        return reverse_lazy("document_management:my_files")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        owner_id = self.request.GET.get('owner_id')
        if owner_id:
            try:
                owner = Staff.objects.get(id=owner_id)
                initial['owner'] = owner
                initial['file_type'] = 'personal'
                initial['title'] = f"PERSONNEL FILE OF {owner.user.get_full_name().upper() if owner.user.get_full_name() else owner.user.username.upper()}"
            except Staff.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        user_staff = self.get_staff_user()
        if not user_staff:
            raise Http404("Staff user profile not found.")

        # Initially, the file sits with the creator
        form.instance.current_location = user_staff
        form.instance.created_by = self.request.user

        # For policy files, if department is provided in the form, use it.
        # Otherwise, default to the creator's department if it's a personal file.
        if form.cleaned_data.get('file_type') == 'personal' and not form.instance.department:
            owner = form.cleaned_data.get('owner')
            if owner:
                form.instance.department = owner.department

        self.object = form.save()

        # Handle uploaded attachments
        for f in self.request.FILES.getlist("attachments"):
            Document.objects.create(
                file=self.object, attachment=f, uploaded_by=self.request.user
            )

        # Log file creation
        log_action(
            self.request.user, "FILE_CREATED", request=self.request, obj=self.object
        )

        messages.success(self.request, "File and documents created successfully.")
        return redirect(self.get_success_url())

    def get_staff_user(self):
        user = self.request.user
        try:
            staff = Staff.objects.get(user=user)
            return staff
        except Staff.DoesNotExist:
            return None

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(self.request, "You do not have permission to create a new file.")
        return redirect("document_management:my_files")


class MyFilesView(HTMXLoginRequiredMixin, ListView):
    model = File
    template_name = "document_management/my_files.html"
    context_object_name = "owned_folders"
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        # Allow all staff to access their own files
        return super().dispatch(request, *args, **kwargs)

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["document_management/partials/_my_files_list.html"]
        return [self.template_name]

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        

        # Strictly owned folders (personal folder + folders they created)
        queryset = File.objects.filter(
            Q(owner=staff_user) | Q(created_by=self.request.user)
        ).distinct()

        # Apply search filters
        search_query = self.request.GET.get("q")
        if search_query:
            # Filter files that match the query in title, number, OR have matching documents
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(file_number__icontains=search_query) |
                Q(documents__title__icontains=search_query)
            ).distinct()

            queryset = queryset.prefetch_related(
                Prefetch(
                    'documents',
                    queryset=Document.objects.filter(title__icontains=search_query)
                )
            )
        else:
            queryset = queryset.prefetch_related('documents')

        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        context = super().get_context_data(**kwargs)
        
        # Fetch the staff's personal file number
        personal_folder = File.objects.filter(owner=staff_user, file_type='personal').first()
        context["staff_file_number"] = personal_folder.file_number if personal_folder else "NOT ASSIGNED"
        
        context["selected_search_query"] = self.request.GET.get("q", "")
        return context

    def get_staff_user(self):
        user = self.request.user
        try:
            staff = Staff.objects.get(user=user)
            return staff
        except Staff.DoesNotExist:
            return None


class MessagesView(LoginRequiredMixin, ListView):
    """
    Inbox for incoming folder dispatches.
    """
    model = File
    template_name = "document_management/messages.html"
    context_object_name = "inbox_files"
    paginate_by = 10

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user profile not found.")

        # Incoming files (where the user is the current custodian but not the owner)
        queryset = File.objects.filter(
            current_location=staff_user
        ).exclude(owner=staff_user)

        search_query = self.request.GET.get("q")
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query)
                | Q(file_number__icontains=search_query)
            )
        
        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_search_query"] = self.request.GET.get("q", "")
        return context

    def get_staff_user(self):
        try:
            return self.request.user.staff
        except Staff.DoesNotExist:
            return None


class FileRequestActivationView(LoginRequiredMixin, View):
    def get_staff_user(self):
        user = self.request.user
        try:
            staff = Staff.objects.get(user=user)
            return staff
        except Staff.DoesNotExist:
            return None

    def post(self, request, pk):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        file = get_object_or_404(File, pk=pk, owner=staff_user)
        
        if file.status == "inactive":
            # Registry Bypass: Directly activate
            if staff_user.is_registry:
                file.status = "active"
                file.save()
                log_action(request.user, "FILE_ACTIVATED", request=request, obj=file)
                messages.success(request, f"File '{file.title}' has been activated successfully.")
            
            else:
                # All other staff: Submit to Registry
                file.status = "pending_activation"
                file.save()
                messages.success(request, f"Activation request for '{file.title}' submitted to Registry.")


        else:
            messages.warning(
                request, f"File '{file.title}' is already {file.get_status_display()}."
            )
        return redirect("document_management:my_files")


class FileApproveActivationView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "document_management.activate_file"

    def post(self, request, pk):
        file = get_object_or_404(File, pk=pk)
        if file.status == "pending_activation":
            file.status = "active"
            file.save()
            log_action(
                self.request.user, "FILE_ACTIVATED", request=self.request, obj=file
            )

            # Notify file owner
            if file.owner and file.owner.user:
                create_notification(
                    user=file.owner.user,
                    message=f"Your file '{file.title}' ({file.file_number}) has been activated.",
                    obj=file,
                    link=file.get_absolute_url(),
                )
            messages.success(request, f"File '{file.title}' has been activated.")
        else:
            messages.warning(request, f"File '{file.title}' is not pending activation.")
        return redirect("document_management:registry_hub")

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(
            self.request, "You do not have permission to approve file activations."
        )
        return redirect("document_management:registry_hub")


class FileRecallView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "document_management.view_file"  # Basic perm, refined by registry check

    def post(self, request, pk):
        staff_user = self.get_staff_user()
        if not staff_user or not staff_user.is_registry:
            messages.error(request, "Only Registry staff can recall files.")
            return redirect("document_management:registry_hub")

        file = get_object_or_404(File, pk=pk)
        
        # Capture previous location for notification
        previous_custodian = file.current_location

        # Update location to the Registry Staff member recalling it
        file.current_location = staff_user
        file.save()

        # Log action
        log_action(
            request.user, 
            "FILE_RECALLED", 
            request=request, 
            obj=file,
            details={"previous_location": str(previous_custodian) if previous_custodian else "Unknown"}
        )

        # Notify the previous custodian
        if previous_custodian and previous_custodian.user:
            create_notification(
                user=previous_custodian.user,
                message=f"File '{file.title}' ({file.file_number}) has been RECALLED by Registry.",
                obj=file,
                link=file.get_absolute_url(),
            )

        messages.success(request, f"File '{file.title}' has been successfully recalled to your custody.")
        return redirect("document_management:registry_hub")

    def get_staff_user(self):
        try:
            return Staff.objects.get(user=self.request.user)
        except Staff.DoesNotExist:
            return None


class FileDetailView(HTMXLoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = File
    template_name = "document_management/file_detail.html"
    context_object_name = "file"
    permission_required = "document_management.view_file"

    def has_permission(self):
        user = self.request.user
        # Admins/Superusers always have access
        if user.is_superuser or user.is_staff:
            return True

        # Get the file object that is being accessed
        try:
            target_file = self.get_object()
        except Http404:
            return False  # File not found

        # Try to get the Staff object for the current user
        staff_user = None
        try:
            staff_user = Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return False

        # Check if the user is the owner or has the file in their current location
        if (
            staff_user == target_file.owner
            or staff_user == target_file.current_location
        ):
            return True

        # If they are NOT the owner/location, check for the general permission (Registry/HOD)
        if not super().has_permission():
            return False

        # Check if the user is the owner or has the file in their current location
        if (
            staff_user == target_file.owner
            or staff_user == target_file.current_location
        ):
            return True

        # Logic for Registry to access ALL files globally ("God Mode")
        if staff_user and staff_user.is_registry:
            return True

        # Logic for HODs to access files within their department
        if staff_user and staff_user.is_hod and staff_user.department:
            if (
                target_file.owner
                and target_file.owner.department == staff_user.department
            ):
                return True

        # NEW: Logic for temporary access via FileAccessRequest
        from .models import FileAccessRequest
        active_request = FileAccessRequest.objects.filter(
            file=target_file,
            requested_by=user,
            status='approved'
        ).filter(
            Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
        ).exists()
        if active_request:
            return True

        # NEW: Check if user has specific shared documents in this file
        if target_file.documents.filter(shared_with=user).exists():
            return True

        # If none of the above conditions are met, deny permission
        return False

    def can_view_original(self, file, user):
        """Helper to determine if user can view original (unwatermarked) files."""
        if user.is_superuser:
            return True
        
        try:
            staff = Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return False

        # Direct access (Registry has global access, HOD restricted to their dept)
        if staff.is_registry:
            return True
        if staff.is_hod and file.owner and file.owner.department == staff.department:
            return True

        # Approved temporary access
        from .models import FileAccessRequest
        return FileAccessRequest.objects.filter(
            file=file,
            requested_by=user,
            status='approved'
        ).filter(
            Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
        ).exists()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch only top-level documents (those without a parent)
        context["documents"] = self.object.documents.filter(parent__isnull=True).order_by("-uploaded_at")
        context["send_file_form"] = SendFileForm(user=self.request.user)
        
        # Access Request info
        from .forms import FileAccessRequestForm
        from .models import FileAccessRequest
        context["access_request_form"] = FileAccessRequestForm()
        
        # Check for active access
        is_registry = False
        try:
            is_registry = self.request.user.staff.is_registry
        except AttributeError:
            pass
        context["is_registry"] = is_registry

        # Get active approved access request if exists
        active_access = FileAccessRequest.objects.filter(
            file=self.object, 
            requested_by=self.request.user, 
            status="approved"
        ).first()
        
        # Check if access is currently valid (not expired)
        has_approved_access = False
        access_type = None
        if active_access and active_access.is_active:
            has_approved_access = True
            access_type = active_access.access_type
        
        context["has_approved_access"] = has_approved_access
        context["active_access_request"] = active_access if has_approved_access else None
        context["access_type"] = access_type
        
        # Pass status choices explicitly to template
        context["status_choices"] = STATUS_CHOICES
        
        # Context flags for UI permissions
        can_send_file = False
        if not is_registry and self.object.status == 'active':
            # Only staff who are current custodians can send files
            if hasattr(self.request.user, 'staff') and self.object.current_location == self.request.user.staff:
                can_send_file = True
        
        context["can_send_file"] = can_send_file
        # Current Custodian and Owner checks
        is_custodian = hasattr(self.request.user, 'staff') and self.object.current_location == self.request.user.staff
        is_owner = hasattr(self.request.user, 'staff') and self.object.owner == self.request.user.staff
        
        # Registry users can view but NOT add/edit documents
        context["can_add_minute"] = (not is_registry) and (
            is_custodian or (
            has_approved_access and 
            access_type == 'read_write' and 
            self.object.status == 'active'
        ))

        context["can_delete_documents"] = (not is_registry) and (
                has_approved_access and access_type == 'read_write'
            )

        context["pending_access_request"] = FileAccessRequest.objects.filter(
            file=self.object, requested_by=self.request.user, status="pending"
        ).first()

        # Chronicle: Merge Documents and Audit Logs
        from audit_log.models import AuditLogEntry
        from django.contrib.contenttypes.models import ContentType
        file_ct = ContentType.objects.get_for_model(self.object)
        audit_logs = AuditLogEntry.objects.filter(
            content_type=file_ct, object_id=self.object.pk
        )

        chronicle = []
        
        # Check permissions for Full View vs Limited View
        has_full_view = (
            self.request.user.is_superuser or 
            is_registry or 
            is_custodian or 
            is_owner or 
            (hasattr(self.request.user, 'staff') and self.request.user.staff.is_hod and self.object.owner and self.object.owner.department == self.request.user.staff.department) or
            has_approved_access
        )
        
        if has_full_view:
            audit_logs = AuditLogEntry.objects.filter(
                content_type=file_ct, object_id=self.object.pk
            )
            documents = self.object.documents.all()
        else:
            # Limited View: Only show shared documents and NO audit logs
            audit_logs = AuditLogEntry.objects.none()
            documents = self.object.documents.filter(shared_with=self.request.user)
            context["is_limited_view"] = True

        for doc in documents:
            chronicle.append({
                'type': 'document',
                'timestamp': doc.uploaded_at,
                'item': doc
            })
            
        for log in audit_logs:
            chronicle.append({
                'type': 'audit',
                'timestamp': log.timestamp,
                'item': log
            })

        # Sort combined chronicle by timestamp descending
        context["chronicle"] = sorted(chronicle, key=lambda x: x['timestamp'], reverse=True)

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Handle explicit Status Update action (from the sidebar form)
        if request.POST.get("action") == "update_status":
            # Check permissions: Only Registry or Owners (for personal files) should usually do this
            # For now, rely on view permission + role checks
            is_registry = False
            try:
                is_registry = request.user.staff.is_registry
            except AttributeError:
                pass
            
            if not is_registry:
                 messages.error(request, "Only Registry staff can manually update file status.")
                 return redirect(self.object.get_absolute_url())

            new_status = request.POST.get("status")
            if new_status:
                old_status = self.object.status
                self.object.status = new_status
                self.object.save()
                
                log_action(
                    request.user, 
                    "FILE_UPDATED", 
                    request=request, 
                    obj=self.object,
                    details={"field": "status", "old": old_status, "new": new_status}
                )
                messages.success(request, f"File status updated to {self.object.get_status_display()}.")
            return redirect(self.object.get_absolute_url())

        # Handle Document Status Update action
        if request.POST.get("action") == "update_document_status":
            doc_id = request.POST.get("document_id")
            new_status = request.POST.get("status")

            if doc_id and new_status:
                from django.shortcuts import get_object_or_404
                # Fetch document first to check ownership
                doc = get_object_or_404(self.object.documents, pk=doc_id)
                
                # Strict check: Only the uploader can change status
                if doc.uploaded_by != request.user:
                    messages.error(request, "Only the document creator can update its status.")
                    return redirect(self.object.get_absolute_url())

                # Proceed with update
                old_status = doc.status
                doc.status = new_status
                doc.save()
                
                log_action(
                    request.user,
                    "DOCUMENT_UPDATED", 
                    request=request,
                    obj=doc,
                    details={'field': 'status', 'old': old_status, 'new': new_status}
                )
                messages.success(request, f"Document status updated to {doc.get_status_display()}.")
                
            return redirect(self.object.get_absolute_url())

        # Determine which form was submitted (other than status updates)
        if "reason" in request.POST:
            # FileAccessRequest submission
            from .forms import FileAccessRequestForm
            form = FileAccessRequestForm(request.POST)
            if form.is_valid():
                from .models import FileAccessRequest
                access_req = form.save(commit=False)
                access_req.file = self.object
                access_req.requested_by = request.user
                access_req.save()
                
                log_action(request.user, "ACCESS_REQUEST_SUBMITTED", request=request, obj=self.object)
                messages.success(request, "Access request submitted to Registry.")
                return redirect(self.object.get_absolute_url())
            else:
                context = self.get_context_data()
                context["access_request_form"] = form
                return self.render_to_response(context)
        elif "recipient" in request.POST:
            # SendFileForm submission
            is_registry = False
            try:
                is_registry = request.user.staff.is_registry
            except AttributeError:
                pass

            if is_registry or not request.user.has_perm("document_management.send_file"):
                messages.error(request, "Registry users cannot dispatch files. This is restricted to Department/Unit management.")
                return redirect(self.object.get_absolute_url())

            # Check if the file is active before sending
            if self.object.status != "active":
                messages.error(
                    request,
                    f"File '{self.object.title}' must be active to be dispatched. Current status: {self.object.get_status_display()}.",
                )
                return redirect(self.object.get_absolute_url())

            form = SendFileForm(user=request.user, data=request.POST)
            if form.is_valid():
                recipient_user = form.cleaned_data[
                    "recipient"
                ]  # This is a CustomUser object
                previous_location = (
                    self.object.current_location
                )  # Capture previous location for audit

                # Get Staff object for current_location to save in File model
                try:
                    recipient_staff = Staff.objects.get(user=recipient_user)
                except Staff.DoesNotExist:
                    messages.error(
                        request,
                        "Recipient is not a staff member and cannot receive files.",
                    )
                    return redirect(self.object.get_absolute_url())

                self.object.current_location = recipient_staff
                
                # Link to specific document if provided
                doc_id = form.cleaned_data.get("document_id")
                if doc_id:
                    from .models import Document
                    try:
                        doc = Document.objects.get(pk=doc_id, file=self.object)
                        self.object.active_dispatch_document = doc
                    except Document.DoesNotExist:
                        pass
                
                self.object.save()
                log_action(
                    request.user,
                    "FILE_SENT",
                    request=request,
                    obj=self.object,
                    details={
                        "from_location": str(previous_location),
                        "to_location": str(recipient_staff),
                        "on_document": str(self.object.active_dispatch_document) if self.object.active_dispatch_document else "N/A"
                    },
                )

                # Create in-app notification for the recipient
                create_notification(
                    user=recipient_user,
                    message=f"File '{self.object.title}' ({self.object.file_number}) has been sent to you.",
                    obj=self.object,
                    link=self.object.get_absolute_url(),
                )
                messages.success(
                    request,
                    f"File sent to {recipient_user.get_full_name() or recipient_user.username}.",
                )
                return redirect(
                    self.object.get_absolute_url()
                )  # Always redirect after successful send
            else:
                context = self.get_context_data()
                context["send_file_form"] = form
                print("SendFileForm is invalid. Errors:", form.errors)  # Debug print
                if request.headers.get("HX-Request"):
                    # For HTMX, return the form with errors as an alert
                    error_html = '<div class="alert alert-danger" role="alert"><p class="mb-1"><strong>Error sending file:</strong></p><ul class="mb-0">'
                    for field in form:
                        for error in field.errors:
                            error_html += f"<li>{field.label}: {error}</li>"
                    for error in form.non_field_errors():
                        error_html += f"<li>{error}</li>"
                    error_html += "</ul></div>"
                    return HttpResponse(
                        error_html
                    )  # Return only the error HTML for HTMX
                messages.error(
                    request, "Error sending file. Please check the form for details."
                )
                for field in form:
                    for error in field.errors:
                        messages.error(request, f"{field.label}: {error}")
                for error in form.non_field_errors():
                    messages.error(request, error)
                return self.render_to_response(context)

        elif request.POST.get("action") == "return_to_owner":
            # Return file to owner
            if not hasattr(request.user, 'staff') or self.object.current_location != request.user.staff:
                messages.error(request, "Only the current custodian can return this file.")
                return redirect(self.object.get_absolute_url())
            
            if self.object.owner == request.user.staff:
                messages.warning(request, "You are already the owner of this file.")
                return redirect(self.object.get_absolute_url())

            previous_location = self.object.current_location
            self.object.current_location = self.object.owner
            self.object.save()
            
            log_action(
                request.user,
                "FILE_RETURNED",
                request=request,
                obj=self.object,
                details={
                    "from_location": str(previous_location),
                    "to_location": str(self.object.owner),
                },
            )
            
            # Notify the owner
            if self.object.owner and self.object.owner.user:
                create_notification(
                    user=self.object.owner.user,
                    message=f"File '{self.object.title}' ({self.object.file_number}) has been returned to you.",
                    obj=self.object,
                    link=self.object.get_absolute_url(),
                )
            
            messages.success(request, f"File returned to {self.object.owner.user.get_full_name() or 'owner'}.")
            return redirect("document_management:my_files")

        elif request.POST.get("action") == "update_status" and request.user.staff.is_registry:
            # Registry global status update
            new_status = request.POST.get("status")
            if new_status in dict(File.STATUS_CHOICES):
                old_status = self.object.status
                self.object.status = new_status
                self.object.save()
                log_action(
                    request.user, 
                    "FILE_STATUS_UPDATED", 
                    request=request, 
                    obj=self.object,
                    details={"old_status": old_status, "new_status": new_status}
                )
                messages.success(request, f"File status updated to {self.object.get_status_display()}.")
            else:
                messages.error(request, "Invalid status selected.")
            return redirect(self.object.get_absolute_url())

        # Fallback if no form is recognized
        messages.error(request, "Invalid form submission.")
        return redirect(self.object.get_absolute_url())

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(self.request, "You do not have permission to view this file.")
        return redirect("document_management:my_files")


class FileUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = File
    form_class = FileUpdateForm
    template_name = "document_management/file_form.html"  # Reusing the form template
    context_object_name = "file"

    def get_success_url(self):
        return reverse_lazy(
            "document_management:file_detail", kwargs={"pk": self.object.pk}
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            self.request.user, "FILE_UPDATED", request=self.request, obj=self.object
        )
        messages.success(self.request, "File updated successfully.")
        return response

    def test_func(self):
        user = self.request.user
        # Registry users can NOT edit files - only view, create, delete
        return user.is_superuser

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(self.request, "You do not have permission to edit this file.")
        return redirect("document_management:my_files")


class DocumentUploadView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentUploadForm
    template_name = (
        "document_management/document_upload_form.html"  # A new template for this
    )
    success_url = reverse_lazy("document_management:my_files")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        document = form.save(commit=False)
        document.uploaded_by = self.request.user
        document.save()
        messages.success(self.request, "Document uploaded successfully.")
        return redirect(self.get_success_url())

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(self.request, "You do not have permission to upload documents.")
        return redirect("document_management:my_files")


class FileCloseView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
        try:
            return user.staff.is_registry
        except AttributeError:
            return False

    def post(self, request, pk):
        file = get_object_or_404(File, pk=pk)
        if file.status == "active":
            file.status = "closed"
            file.save()
            log_action(self.request.user, "FILE_CLOSED", request=self.request, obj=file)
            messages.success(request, f"File '{file.title}' has been closed.")
        else:
            messages.warning(
                request, f"File '{file.title}' is not active and cannot be closed."
            )
        return redirect("document_management:file_detail", pk=pk)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(self.request, "You do not have permission to close this file.")
        return redirect("document_management:my_files")


class FileArchiveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "document_management.archive_file"

    def post(self, request, pk):
        file = get_object_or_404(File, pk=pk)
        if file.status == "closed":
            file.status = "archived"
            file.save()
            log_action(
                self.request.user, "FILE_ARCHIVED", request=self.request, obj=file
            )
            messages.success(request, f"File '{file.title}' has been archived.")
        else:
            messages.warning(
                request, f"File '{file.title}' is not closed and cannot be archived."
            )
        return redirect("document_management:file_detail", pk=pk)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(self.request, "You do not have permission to archive files.")
        return redirect("document_management:my_files")
class DirectorAdminDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = File
    template_name = "document_management/admin_dashboard.html"
    context_object_name = "recent_files"

    def test_func(self):
        staff_user = self.get_staff_user()
        return staff_user and (staff_user.is_hod or self.request.user.is_superuser)

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None

    def get_queryset(self):
        # Return recent files for the "Files on My Desk" section
        staff_user = self.get_staff_user()
        return File.objects.filter(current_location=staff_user).order_by("-created_at")[:10]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        # Hospital Staffing Overview
        context["total_staff"] = Staff.objects.count()
        context["staff_by_type"] = {
            label: Staff.objects.filter(staff_type=val).count()
            for val, label in Staff.STAFF_TYPE_CHOICES
        }

        # Staff File Activity (Last 30 Days)
        context["new_files_30d"] = File.objects.filter(created_at__gte=thirty_days_ago).count()
        # In a real system, we'd count leave apps, training etc. via specific models or file types.
        # For this MVP, we'll use file types if they match those in the PDF.
        # But we only have 'personal' and 'policy' for now.
        
        # Records Retention & Archival Queue
        # Files that have been 'closed' for more than say 30 days are candidates for archival review
        context["archival_queue"] = File.objects.filter(status="closed").order_by("-created_at")

        # Interdepartmental File Flows (Simplified: Count files sent to each dept recently)
        dept_flows = []
        for dept in Department.objects.all():
            count = File.objects.filter(department=dept, created_at__gte=thirty_days_ago).count()
            dept_flows.append({"name": dept.name, "count": count})
        context["dept_flows"] = dept_flows

        return context

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(
            self.request, "You do not have permission to access the Director Admin dashboard."
        )
        return redirect("document_management:my_files")
class RecipientSearchView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        if not query or len(query) < 2:
            return HttpResponse("")

        # Filter staff who are HODs or Unit Managers
        # Only Managers/HODs can be recipients for dispatch logic usually, ensuring hierarchy
        # Exclude self to prevent sending to oneself
        recipients = Staff.objects.filter(
            Q(headed_department__isnull=False) | Q(headed_unit__isnull=False)
        ).filter(
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(department__name__icontains=query) |
            Q(unit__name__icontains=query)
        ).exclude(user=request.user).distinct()[:10]

        # Simple HTML response for HTMX - Dispatch Modal Layout
        html = '<div class="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden max-h-60 overflow-y-auto">'
        if recipients:
            for staff in recipients:
                name = staff.user.get_full_name() or staff.user.username
                designation = staff.designation.name if staff.designation else "Staff"
                role_label = ""
                if staff.is_hod:
                    role_label = '<span class="ml-2 text-[9px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded font-bold uppercase">HOD</span>'
                elif staff.is_unit_manager:
                     role_label = '<span class="ml-2 text-[9px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-bold uppercase">Manager</span>'

                dept_code = staff.department.code if staff.department else 'N/A'
                
                html += f"""
                <div class="px-4 py-3 hover:bg-slate-50 cursor-pointer border-b border-slate-100 last:border-0 transition-colors"
                     @click="$dispatch('recipient-selected', {{ id: '{staff.user.id}', username: '{name}' }})">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs font-bold text-slate-900">{name} {role_label}</p>
                            <p class="text-[10px] text-slate-500 font-medium">{designation}</p>
                        </div>
                        <div class="text-right">
                             <p class="text-[9px] text-slate-400 font-bold uppercase tracking-wider">{dept_code}</p>
                        </div>
                    </div>
                </div>
                """
        else:
            html += '<div class="px-4 py-3 text-xs text-slate-500 italic text-center">No matching HODs or Managers found.</div>'
        html += '</div>'
        
        return HttpResponse(html)

class FileAccessRequestListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = FileAccessRequest
    template_name = "document_management/access_request_list.html"
    context_object_name = "requests"

    def test_func(self):
        return hasattr(self.request.user, 'staff') and self.request.user.staff.is_registry

    def get_queryset(self):
        return FileAccessRequest.objects.filter(status='pending').order_by('-created_at')

class FileAccessRequestApproveView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return hasattr(self.request.user, 'staff') and self.request.user.staff.is_registry

    def post(self, request, pk):
        from core.constants import ACCESS_REQUEST_DURATION_HOURS
        access_req = get_object_or_404(FileAccessRequest, pk=pk)
        access_req.status = 'approved'
        access_req.approved_at = timezone.now()
        access_req.expires_at = timezone.now() + timedelta(hours=ACCESS_REQUEST_DURATION_HOURS)
        access_req.save()

        log_action(request.user, "ACCESS_REQUEST_APPROVED", request=request, obj=access_req.file, details={'requested_by': access_req.requested_by.username})
        
        create_notification(
            user=access_req.requested_by,
            message=f"Your access request for file '{access_req.file.title}' has been approved. Access expires in {ACCESS_REQUEST_DURATION_HOURS} hours.",
            obj=access_req.file,
            link=access_req.file.get_absolute_url()
        )
        
        messages.success(request, f"Access request for {access_req.requested_by.username} approved.")
        return redirect('document_management:access_request_list')

class FileAccessRequestRejectView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return hasattr(self.request.user, 'staff') and self.request.user.staff.is_registry

    def post(self, request, pk):
        access_req = get_object_or_404(FileAccessRequest, pk=pk)
        access_req.status = 'rejected'
        access_req.save()

        log_action(request.user, "ACCESS_REQUEST_REJECTED", request=request, obj=access_req.file, details={'requested_by': access_req.requested_by.username})
        
        create_notification(
            user=access_req.requested_by,
            message=f"Your access request for file '{access_req.file.title}' has been rejected.",
            obj=access_req.file
        )
        
        messages.success(request, f"Access request for {access_req.requested_by.username} rejected.")
        return redirect('document_management:access_request_list')

class StaffSearchView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        
        # Start with all staff
        queryset = Staff.objects.all()

        # Exclude Superusers
        queryset = queryset.exclude(user__is_superuser=True)

        # Exclude Registry staff (assuming 'registry' in designation or department name)
        queryset = queryset.exclude(
            Q(designation__name__icontains='registry') | 
            Q(department__name__icontains='registry')
        )

        # Apply search query
        if query:
            queryset = queryset.filter(
                Q(user__username__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query) |
                Q(department__name__icontains=query)
            )
        
        # Limit results
        staff_members = queryset.select_related('user', 'department', 'designation').order_by('user__first_name')[:10]

        return render(request, 'document_management/partials/staff_search_results.html', {
            'staff_members': staff_members,
            'query': query
        })


class DocumentDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Delete a document from a file.
    Only Registry or users with active Read-Write access can delete documents.
    """

    def test_func(self):
        document = get_object_or_404(Document, pk=self.kwargs['pk'])
        file_obj = document.file
        user = self.request.user

        # Registry can NOT delete documents (they can only view, create, and delete FILES)

        # Check for active read-write access
        active_access = FileAccessRequest.objects.filter(
            file=file_obj,
            requested_by=user,
            status='approved',
            access_type='read_write'
        ).first()

        if active_access and active_access.is_active:
            return True

        # Allow the document uploader to delete their own documents
        if document.uploaded_by == user:
            return True

        return False

    def post(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        file_obj = document.file
        
        log_action(
            request.user, 
            "DOCUMENT_DELETED", 
            request=request, 
            obj=file_obj,
            details={'document_title': document.title, 'document_id': document.pk}
        )
        
        # Delete the document
        document.delete()
        
        messages.success(request, "Document deleted successfully.")
        return redirect(file_obj.get_absolute_url())

class FileDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Delete a file (folder) container.
    Only Registry or Superusers can delete files.
    """
    def test_func(self):
        user = self.request.user
        try:
            return user.staff.is_registry or user.is_superuser
        except AttributeError:
            return user.is_superuser

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        
        log_action(
            request.user, 
            "FILE_DELETED", 
            request=request, 
            obj=file_obj,
            details={'file_number': file_obj.file_number, 'title': file_obj.title}
        )
        
        file_title = file_obj.title
        file_number = file_obj.file_number
        
        # Delete the file
        file_obj.delete()
        
        messages.success(request, f"File {file_title} ({file_number}) has been permanently deleted.")
        return redirect('document_management:registry_hub')


class DocumentDetailView(HTMXLoginRequiredMixin, DetailView):
    """
    Detailed view of a single document from a file's chronicle.
    Allows users to view the full document content and dispatch actions.
    """
    model = Document
    template_name = "document_management/document_detail.html"
    context_object_name = "document"

    def has_permission(self):
        """Check if user has permission to view this document."""
        document = self.get_object()
        file_obj = document.file
        user = self.request.user

        # Admins/Superusers always have access
        if user.is_superuser or user.is_staff:
            return True

        # Try to get the Staff object for the current user
        staff_user = None
        try:
            staff_user = Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return False

        # Check if the user is the owner or has the file in their current location
        if (staff_user == file_obj.owner or staff_user == file_obj.current_location):
            return True

        # Registry can access all documents
        if staff_user and staff_user.is_registry:
            return True

        # HODs can access files within their department
        if staff_user and staff_user.is_hod and staff_user.department:
            if (file_obj.owner and file_obj.owner.department == staff_user.department):
                return True

        # Check for temporary access via FileAccessRequest
        active_request = FileAccessRequest.objects.filter(
            file=file_obj,
            requested_by=user,
            status='approved'
        ).filter(
            Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
        ).exists()
        if active_request:
            return True

        # Check if document is shared with user
        if document.shared_with.filter(id=user.id).exists():
            return True

        return False

    def dispatch(self, request, *args, **kwargs):
        """Override to check permissions before dispatching."""
        if not self.has_permission():
            if not request.user.is_authenticated:
                return redirect("user_management:login")
            messages.error(request, "You do not have permission to view this document.")
            return redirect("document_management:my_files")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.object
        file_obj = document.file
        
        # Access control flags
        is_registry = False
        try:
            is_registry = self.request.user.staff.is_registry
        except AttributeError:
            pass
        
        # Current Custodian and Owner checks
        is_custodian = hasattr(self.request.user, 'staff') and file_obj.current_location == self.request.user.staff
        is_owner = hasattr(self.request.user, 'staff') and file_obj.owner == self.request.user.staff
        
        # Check for approved access
        has_approved_access = FileAccessRequest.objects.filter(
            file=file_obj,
            requested_by=self.request.user,
            status='approved'
        ).filter(
            Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
        ).exists()
        
        access_type = None
        if has_approved_access:
            active_access = FileAccessRequest.objects.filter(
                file=file_obj,
                requested_by=self.request.user,
                status='approved'
            ).filter(
                Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
            ).first()
            if active_access:
                access_type = active_access.access_type
        
        # Permissions for actions
        context["can_add_minute"] = is_registry or is_custodian or (
            has_approved_access and 
            access_type == 'read_write' and 
            file_obj.status == 'active'
        )
        
        # Can send file only if not registry and is current custodian
        can_send_file = False
        if not is_registry and file_obj.status == 'active':
            if hasattr(self.request.user, 'staff') and file_obj.current_location == self.request.user.staff:
                can_send_file = True
        
        context["can_send_file"] = can_send_file
        
        return context

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(self.request, "You do not have permission to view this document.")
        return redirect("document_management:my_files")



class FileDocumentsView(HTMXLoginRequiredMixin, ListView):
    model = Document
    template_name = "document_management/partials/_document_rows.html"
    context_object_name = "documents"
    paginate_by = 1

    def get_queryset(self):
        file_pk = self.kwargs.get("pk")
        queryset = Document.objects.filter(file_id=file_pk)

        search_query = self.request.GET.get("q")
        if search_query:
            queryset = queryset.filter(title__icontains=search_query)

        return queryset.order_by("-uploaded_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["file_id"] = self.kwargs.get("pk")
        context["selected_search_query"] = self.request.GET.get("q", "")
        return context

class RecordExplorerView(HTMXLoginRequiredMixin, ListView):
    model = File
    template_name = "document_management/record_explorer.html"
    context_object_name = "files"
    paginate_by = 20

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user or not (staff_user.is_registry or staff_user.is_hod or staff_user.is_unit_manager):
            raise PermissionDenied("You do not have permission to access the Record Explorer.")

        # Role-based filtering (same as Registry Dashboard but focused on exploration)
        if staff_user.is_registry:
            queryset = File.objects.all()
        elif staff_user.is_hod:
            queryset = File.objects.filter(department=staff_user.department)
        elif staff_user.is_unit_manager:
            queryset = File.objects.filter(owner__unit=staff_user.unit)
        else:
            queryset = File.objects.none()

        # Search filter
        search_query = self.request.GET.get("q")
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(file_number__icontains=search_query)
            )

        return queryset.order_by("-created_at")

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            if "details" in self.request.path or self.request.GET.get("file_pk"):
                return ["document_management/partials/_explorer_file_detail.html"]
            return ["document_management/partials/_explorer_sidebar_list.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_search_query"] = self.request.GET.get("q", "")
        
        # If a specific file is requested via HTMX
        file_pk = self.request.GET.get("file_pk")
        if file_pk:
            context["selected_file"] = get_object_or_404(File, pk=file_pk)
            # Fetch documents with pagination (using same limit as FileDocumentsView)
            context["documents"] = Document.objects.filter(file_id=file_pk).order_by("-uploaded_at")[:5]
            context["has_more_documents"] = Document.objects.filter(file_id=file_pk).count() > 5
        
        return context

    def get_staff_user(self):
        try:
            return Staff.objects.get(user=self.request.user)
        except Staff.DoesNotExist:
            return None


class DocumentShareView(LoginRequiredMixin, View):
    def post(self, request, pk):
        User = get_user_model()
        document = get_object_or_404(Document, pk=pk)
        
        # Check permission to share
        file = document.file
        user = request.user
        staff = None
        try:
             staff = user.staff
        except:
             pass

        is_registry = staff.is_registry if staff else False
        is_owner = staff == file.owner if staff else False
        is_custodian = staff == file.current_location if staff else False
        
        # Check approved access
        has_access = FileAccessRequest.objects.filter(
            file=file, 
            requested_by=user, 
            status="approved"
        ).filter(
            Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
        ).exists()

        if not (user.is_superuser or is_registry or is_owner or is_custodian or has_access):
             messages.error(request, "You do not have permission to share this document.")
             return redirect(file.get_absolute_url())

        recipient_id = request.POST.get('recipient_id')
        if not recipient_id:
            messages.error(request, "No recipient specified.")
            return redirect(file.get_absolute_url())

        try:
            recipient = User.objects.get(pk=recipient_id)
            if recipient == user:
                 messages.warning(request, "You cannot share a document with yourself.")
            elif document.shared_with.filter(pk=recipient.pk).exists():
                 messages.info(request, f"Document is already shared with {recipient.get_full_name()}.")
            else:
                document.shared_with.add(recipient)
                
                # Notify recipient
                create_notification(
                    user=recipient,
                    message=f"{user.get_full_name()} shared a document with you: '{document.title or 'Minute/Signal'}' from file {file.file_number}",
                    obj=document,
                    link=file.get_absolute_url()
                )
                
                messages.success(request, f"Document successfully shared with {recipient.get_full_name()}.")
        except User.DoesNotExist:
            messages.error(request, "Recipient user not found.")

        return redirect(file.get_absolute_url())

class DocumentCreateView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentForm
    template_name = "document_management/document_create.html"

    def dispatch(self, request, *args, **kwargs):
        self.file_obj = get_object_or_404(File, pk=self.kwargs.get('file_pk'))
        
        staff_user = getattr(request.user, 'staff', None)
        
        # Check for approved access requests first (Override)
        has_approved_access = FileAccessRequest.objects.filter(
            file=self.file_obj,
            requested_by=request.user,
            status='approved',
            access_type='read_write' # Must be RW to add documents
        ).filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).exists()

        if has_approved_access:
             if self.file_obj.status != 'active':
                messages.error(request, "Documents can only be added to active files.")
                return redirect(self.file_obj.get_absolute_url())
             return super().dispatch(request, *args, **kwargs)

        # Strict Role-Based Access Control
        has_permission = False
        
        if self.file_obj.file_type == 'personal':
            # Personal Files: ONLY the Owner can add documents
            if self.file_obj.owner == staff_user:
                has_permission = True
        
        elif self.file_obj.file_type == 'policy':
             # Policy/Public Files: ONLY the Department HOD can add documents
             if staff_user and staff_user.is_hod and self.file_obj.department == staff_user.department:
                 has_permission = True
        
        else:
             # Fallback for other types (e.g. if added later): Default to Owner or HOD logic
             if self.file_obj.owner == staff_user:
                 has_permission = True
             if staff_user and staff_user.is_hod and self.file_obj.department == staff_user.department:
                 has_permission = True

        if not has_permission:
            messages.error(request, "You do not have permission to add documents to this file. Restricted to File Owner/HOD.")
            return redirect(self.file_obj.get_absolute_url())
            
        if self.file_obj.status != 'active':
            messages.error(request, "Documents can only be added to active files.")
            return redirect(self.file_obj.get_absolute_url())
            
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        parent_id = self.request.GET.get('parent_id')
        if parent_id:
            initial['parent'] = parent_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['file'] = self.file_obj
        parent_id = self.request.GET.get('parent_id')
        if parent_id:
            context['parent_doc'] = get_object_or_404(Document, pk=parent_id)
        
        # Add active signature for preview
        if hasattr(self.request.user, 'staff'):
            context['active_signature'] = self.request.user.staff.get_active_signature()
            
        return context

    def form_valid(self, form):
        form.instance.file = self.file_obj
        form.instance.uploaded_by = self.request.user
        
        # Digital Signature logic
        if form.cleaned_data.get('include_signature'):
            try:
                staff = self.request.user.staff
                active_sig = staff.get_active_signature()
                if active_sig:
                    form.instance.has_signature = True
                    form.instance.signature_record = active_sig
                else:
                    messages.warning(self.request, "You checked 'Attach Digital Signature' but have no signature uploaded in your profile.")
            except Staff.DoesNotExist:
                pass
        
        # Handle clear dispatch
        if self.file_obj.active_dispatch_document:
            is_custodian = hasattr(self.request.user, 'staff') and self.file_obj.current_location == self.request.user.staff
            if is_custodian:
                # If they are replying to the specific dispatch document
                if form.instance.parent == self.file_obj.active_dispatch_document:
                    self.file_obj.clear_dispatch()

        response = super().form_valid(form)
        
        log_action(
            self.request.user,
            "DOCUMENT_ADDED",
            request=self.request,
            obj=self.object,
            details={"file_id": self.file_obj.pk},
        )
        messages.success(self.request, "Document/Minute added successfully.")
        return response

    def get_success_url(self):
        return self.file_obj.get_absolute_url()
