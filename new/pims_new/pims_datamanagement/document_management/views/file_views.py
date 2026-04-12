from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import CreateView, DetailView, ListView, UpdateView, TemplateView, View
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.http import Http404, HttpResponse
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from django.db.models import Q, Prefetch
from audit_log.models import AuditLogEntry
from audit_log.utils import log_action
from organization.models import Staff, Department
from ..models import File, FileAccessRequest, FileMovement, Document
from ..forms import FileForm, FileUpdateForm, SendFileForm, FileAccessRequestForm
from .base import HTMXLoginRequiredMixin

class ExecutiveDashboardView(HTMXLoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    Comprehensive dashboard for executives, HODs, and unit managers.
    Shows department/unit-specific metrics based on role.
    """
    template_name = "document_management/executive_dashboard.html"
    permission_required = "document_management.view_file"

    def test_func(self):
        staff_user = self.get_staff_user()
        return staff_user and (staff_user.is_hod or staff_user.is_unit_manager or staff_user.is_md)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_user = self.get_staff_user()
        
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        
        if not (staff_user.is_hod or staff_user.is_unit_manager or staff_user.is_md):
            raise PermissionDenied("Only executives, HODs, unit managers, and MD can access this dashboard.")

        today = timezone.now().date()
        
        if self.request.user.is_superuser:
            scope_filter = Q()
            context['scope_title'] = 'Organization-Wide'
        elif staff_user.is_md:
            scope_filter = Q()
            context['scope_title'] = 'Organization-Wide (MD)'
        elif staff_user.is_hod:
            scope_filter = Q(department=staff_user.department)
            context['scope_title'] = f'{staff_user.department.name} Department'
        elif staff_user.is_unit_manager:
            scope_filter = Q(owner__unit=staff_user.unit)
            context['scope_title'] = f'{staff_user.unit.name} Unit'
        else:
            scope_filter = Q(owner=staff_user)
            context['scope_title'] = 'Personal'

        context['total_files'] = File.objects.filter(scope_filter).count()
        context['active_files'] = File.objects.filter(scope_filter, status='active').count()
        context['pending_activation'] = File.objects.filter(scope_filter, status='pending_activation').count()
        context['closed_files'] = File.objects.filter(scope_filter, status='closed').count()
        context['archived_files'] = File.objects.filter(scope_filter, status='archived').count()

        context['personal_files_count'] = File.objects.filter(scope_filter, file_type='personal').count()
        context['policy_files_count'] = File.objects.filter(scope_filter, file_type='policy').count()

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
        
        context['overdue_files'] = overdue_list[:10]
        context['overdue_count'] = len(overdue_list)
        context['outgoing_files_count'] = outgoing_files.count()

        context['recent_files'] = File.objects.filter(scope_filter).order_by('-created_at')[:10]

        context['docs_added_today'] = Document.objects.filter(
            file__in=File.objects.filter(scope_filter),
            uploaded_at__date=today
        ).count()
        
        context['files_created_this_week'] = File.objects.filter(
            scope_filter,
            created_at__gte=today - timedelta(days=7)
        ).count()

        if staff_user.is_hod:
            context['total_staff'] = Staff.objects.filter(department=staff_user.department).count()
            staff_with_files = File.objects.filter(
                scope_filter,
                file_type='personal'
            ).values_list('owner_id', flat=True).distinct()
            context['staff_with_files_count'] = len(staff_with_files)
            context['staff_without_files_count'] = context['total_staff'] - context['staff_with_files_count']
        
        elif staff_user.is_unit_manager:
            context['total_staff'] = Staff.objects.filter(unit=staff_user.unit).count()
            staff_with_files = File.objects.filter(
                scope_filter,
                file_type='personal'
            ).values_list('owner_id', flat=True).distinct()
            context['staff_with_files_count'] = len(staff_with_files)
            context['staff_without_files_count'] = context['total_staff'] - context['staff_with_files_count']

        context['pending_access_requests'] = FileAccessRequest.objects.filter(
            file__in=File.objects.filter(scope_filter),
            status='pending'
        ).order_by('-created_at')[:5]

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
            self.request, "You do not have permission to access the executive dashboard."
        )
        return redirect("document_management:my_files")

class HODDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = File
    template_name = "document_management/hod_dashboard.html"
    context_object_name = "files"

    def test_func(self):
        staff_user = self.get_staff_user()
        return staff_user and (staff_user.is_hod or staff_user.is_unit_manager)

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")

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

        if staff_user.is_unit_manager:
            custody_files = File.objects.filter(
                current_location__unit=staff_user.unit,
                status='active'
            ).exclude(current_location=None).select_related('current_location', 'owner').order_by('-created_at')
        else:
            custody_files = File.objects.filter(
                current_location__department=staff_user.department,
                status='active'
            ).exclude(current_location=None).select_related('current_location', 'owner').order_by('-created_at')
        
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

        form.instance.current_location = user_staff
        form.instance.created_by = self.request.user

        if form.cleaned_data.get('file_type') == 'personal' and not form.instance.department:
            owner = form.cleaned_data.get('owner')
            if owner:
                form.instance.department = owner.department

        self.object = form.save()

        for f in self.request.FILES.getlist("attachments"):
            Document.objects.create(
                file=self.object, attachment=f, uploaded_by=self.request.user
            )

        log_action(
            self.request.user, "FILE_CREATED", request=self.request, obj=self.object
        )

        messages.success(self.request, "File and documents created successfully.")
        return redirect(self.get_success_url())

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
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

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["document_management/partials/_my_files_list.html"]
        return [self.template_name]

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        
        queryset = File.objects.filter(
            Q(owner=staff_user) | Q(created_by=self.request.user)
        ).distinct()

        search_query = self.request.GET.get("q")
        if search_query:
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
        
        personal_folder = File.objects.filter(owner=staff_user, file_type='personal').first()
        context["staff_file_number"] = personal_folder.file_number if personal_folder else "NOT ASSIGNED"
        
        context["selected_search_query"] = self.request.GET.get("q", "")
        return context

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None

class MessagesView(HTMXLoginRequiredMixin, ListView):
    """Inbox for incoming folder dispatches."""
    model = File
    template_name = "document_management/messages.html"
    context_object_name = "inbox_files"
    paginate_by = 10

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user profile not found.")
        
        queryset = File.objects.filter(
            current_location=staff_user,
            status='active'
        ).exclude(owner=staff_user).order_by("-created_at")

        search_query = self.request.GET.get("q")
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) | Q(file_number__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_search_query"] = self.request.GET.get("q", "")
        return context

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None

class FileRequestActivationView(LoginRequiredMixin, View):
    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        staff_user = self.get_staff_user()
        
        if file_obj.owner != staff_user and file_obj.created_by != request.user:
            messages.error(request, "Only the owner or creator can request activation.")
            return redirect('document_management:my_files')

        if file_obj.status != 'inactive':
            messages.error(request, "Only inactive files can be submitted for activation.")
            return redirect('document_management:my_files')

        file_obj.status = 'pending_activation'
        file_obj.save()

        log_action(request.user, "FILE_ACTIVATION_REQUESTED", request=request, obj=file_obj)
        messages.success(request, f"File {file_obj.file_number} has been submitted for activation.")
        return redirect('document_management:my_files')

class FileRecallView(HTMXLoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "document_management.view_file"

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        staff_user = self.get_staff_user()
        
        if file_obj.owner != staff_user and not staff_user.is_registry:
            messages.error(request, "Only the file owner or registry staff can recall a file.")
            return redirect(file_obj.get_absolute_url())

        if file_obj.current_location == staff_user:
            messages.info(request, "File is already with you.")
            return redirect(file_obj.get_absolute_url())

        old_location = file_obj.current_location
        file_obj.current_location = None  # always returns to registry
        file_obj.status = 'active'
        file_obj.save()

        FileMovement.objects.create(
            file=file_obj,
            sent_by=request.user,
            from_location=old_location,
            sent_to=None,
            action='recalled',
        )
        log_action(
            request.user, 
            "FILE_RECALLED", 
            request=request, 
            obj=file_obj,
            details={"from": old_location.user.get_full_name() if old_location else "Registry"}
        )
        messages.success(request, f"File {file_obj.file_number} has been recalled to your custody.")
        return redirect(file_obj.get_absolute_url())

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None

class FileDetailView(HTMXLoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = File
    template_name = "document_management/file_detail.html"
    context_object_name = "file"
    permission_required = "document_management.view_file"

    def has_permission(self):
        file_obj = self.get_object()
        user = self.request.user
        
        if user.is_superuser:
            return True

        staff_user = getattr(user, 'staff', None)
        if not staff_user:
            return False

        if staff_user.is_registry:
            return True

        if file_obj.file_type == 'policy':
            if staff_user.is_hod and file_obj.department == staff_user.department:
                return True
            if staff_user.is_unit_manager and file_obj.department == staff_user.department:
                return True

        if file_obj.owner == staff_user:
            return True

        if file_obj.current_location == staff_user:
            return True

        has_approved_access = FileAccessRequest.objects.filter(
            file=file_obj,
            requested_by=user,
            status='approved'
        ).filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).exists()

        if has_approved_access:
            return True

        return False

    def can_view_original(self, file, user):
        if user.is_superuser:
            return True
        staff = getattr(user, 'staff', None)
        if not staff:
            return False
            
        if staff.is_registry:
            return True
            
        if file.owner == staff:
            return True
            
        if file.current_location == staff:
            return True
            
        has_rw_access = FileAccessRequest.objects.filter(
            file=file,
            requested_by=user,
            status='approved',
            access_type='read_write'
        ).filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).exists()
        
        if has_rw_access:
            return True
            
        return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        file_obj = self.get_object()
        user = self.request.user
        
        is_custodian = hasattr(user, 'staff') and file_obj.current_location == user.staff
        
        has_approved_access = FileAccessRequest.objects.filter(
            file=file_obj,
            requested_by=user,
            status='approved'
        ).filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).exists()

        has_rw_access = FileAccessRequest.objects.filter(
            file=file_obj,
            requested_by=user,
            status='approved',
            access_type='read_write'
        ).filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).exists()

        is_registry = hasattr(user, 'staff') and user.staff.is_registry
        
        context["can_add_minutes"] = is_custodian or has_rw_access or is_registry
        context["can_send_file"] = is_custodian or is_registry
        context["is_custodian"] = is_custodian
        context["has_approved_access"] = has_approved_access
        context["has_rw_access"] = has_rw_access
        context["is_registry"] = is_registry
        context["can_view_original"] = self.can_view_original(file_obj, user)
        context["send_file_form"] = SendFileForm()
        context["access_request_form"] = FileAccessRequestForm()
        context["pending_access_request"] = FileAccessRequest.objects.filter(
            file=file_obj, requested_by=user, status='pending'
        ).exists()
        context["movements"] = file_obj.movements.select_related(
            'sent_by', 'from_location__user', 'sent_to__user'
        )[:20]
        from core.constants import STATUS_CHOICES
        context["status_choices"] = STATUS_CHOICES
        
        return context

    def post(self, request, *args, **kwargs):
        file_obj = self.get_object()
        action = request.POST.get("action")

        if action == "request_access":
            already_pending = FileAccessRequest.objects.filter(
                file=file_obj, requested_by=request.user, status='pending'
            ).exists()
            if already_pending:
                messages.warning(request, "You already have a pending access request for this file.")
            else:
                FileAccessRequest.objects.create(
                    file=file_obj,
                    requested_by=request.user,
                    access_type=request.POST.get("access_type", "read_only"),
                    reason=request.POST.get("reason", ""),
                    status='pending',
                )
                log_action(request.user, "ACCESS_REQUEST_SUBMITTED", request=request, obj=file_obj)
                messages.success(request, "Access request submitted. Registry will review shortly.")
            return redirect(file_obj.get_absolute_url())

        if action == "send_file":
            staff_user = getattr(request.user, 'staff', None)
            is_registry = staff_user and staff_user.is_registry
            
            if file_obj.current_location != staff_user and not is_registry:
                messages.error(request, "Only the current custodian or registry can send this file.")
                return redirect(file_obj.get_absolute_url())

            form = SendFileForm(request.POST, request.FILES)
            if form.is_valid():
                recipient = form.cleaned_data["recipient"]
                old_location = file_obj.current_location
                note = request.POST.get("movement_note", "")
                file_obj.current_location = recipient
                file_obj.status = 'active'
                file_obj.save()

                FileMovement.objects.create(
                    file=file_obj,
                    sent_by=request.user,
                    from_location=old_location,
                    sent_to=recipient,
                    note=note,
                    attachment=form.cleaned_data.get("movement_attachment"),
                    action='sent',
                )
                log_action(
                    request.user,
                    "FILE_SENT",
                    request=request,
                    obj=file_obj,
                    details={"to": recipient.user.get_full_name()}
                )
                messages.success(request, f"File sent to {recipient.user.get_full_name()}.")
                return redirect("document_management:my_files")

        elif action == "update_document_status":
            doc_id = request.POST.get("document_id")
            new_status = request.POST.get("status")
            status_reason = request.POST.get("status_reason", "")
            
            from django.shortcuts import get_object_or_404
            from document_management.models import Document
            
            document = get_object_or_404(Document, pk=doc_id, file=file_obj)
            
            # Check permissions
            if document.uploaded_by != request.user and not getattr(request.user, 'is_superuser', False):
                messages.error(request, "You do not have permission to update this document's status.")
            elif new_status not in dict(Document.STATUS_CHOICES):
                messages.error(request, "Invalid status selected.")
            elif new_status == "cancelled" and not status_reason.strip():
                messages.error(request, "A reason is required when cancelling a document.")
            else:
                document.status = new_status
                document.status_reason = status_reason
                document.save()
                
                log_action(
                    request.user,
                    "DOCUMENT_STATUS_UPDATED",
                    request=request,
                    obj=document,
                    details={"new_status": new_status, "reason": status_reason}
                )
                messages.success(request, f"Document status updated to {new_status.title()}.")
            
            return redirect(file_obj.get_absolute_url())

        elif action == "sign_document":
            doc_id = request.POST.get("document_id")
            from django.shortcuts import get_object_or_404
            from document_management.models import Document, DocumentSignature
            
            document = get_object_or_404(Document, pk=doc_id, file=file_obj)
            try:
                staff = request.user.staff
                active_sig = staff.get_active_signature()
                if active_sig:
                    if DocumentSignature.objects.filter(document=document, signatory=request.user).exists():
                        messages.warning(request, "You have already signed this document.")
                    else:
                        DocumentSignature.objects.create(
                            document=document,
                            signatory=request.user,
                            signature_record=active_sig
                        )
                        log_action(
                            request.user,
                            "DOCUMENT_SIGNED",
                            request=request,
                            obj=document,
                            details={"signatory": request.user.get_full_name()}
                        )
                        messages.success(request, "Signature attached successfully.")
                else:
                    messages.warning(request, "You have no active signature uploaded in your profile.")
            except Exception:
                messages.error(request, "Only staff members can attach signatures.")
            
            return redirect(file_obj.get_absolute_url())

        return self.get(request, *args, **kwargs)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(self.request, "You do not have permission to view this file.")
        return redirect("document_management:my_files")

class FileUpdateView(HTMXLoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = File
    form_class = FileUpdateForm
    template_name = "document_management/file_form.html"
    context_object_name = "file"

    def get_success_url(self):
        return self.object.get_absolute_url()

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, "FILE_UPDATED", request=self.request, obj=self.object)
        messages.success(self.request, "File updated successfully.")
        return response

    def test_func(self):
        file_obj = self.get_object()
        user = self.request.user
        return user.is_superuser or (hasattr(user, 'staff') and user.staff.is_registry)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(self.request, "You do not have permission to update this file.")
        return redirect(self.get_object().get_absolute_url())

class FileCloseView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        file_obj = get_object_or_404(File, pk=self.kwargs['pk'])
        user = self.request.user
        if user.is_superuser:
            return True
        staff = getattr(user, 'staff', None)
        if not staff:
            return False
        return staff.is_registry or (staff.is_hod and file_obj.department == staff.department)

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        file_obj.status = 'closed'
        file_obj.save()
        log_action(request.user, "FILE_CLOSED", request=request, obj=file_obj)
        messages.success(request, f"File {file_obj.file_number} has been closed.")
        return redirect(file_obj.get_absolute_url())

    def handle_no_permission(self):
        messages.error(self.request, "You do not have permission to close this file.")
        return redirect('document_management:my_files')

class FileArchiveView(HTMXLoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "document_management.archive_file"

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        file_obj.status = 'archived'
        file_obj.save()

        log_action(request.user, "FILE_ARCHIVED", request=request, obj=file_obj)
        messages.success(request, f"File {file_obj.file_number} has been moved to archives.")
        
        if request.headers.get("HX-Request"):
            return HttpResponse(status=204, headers={"HX-Trigger": "fileArchived"})
            
        return redirect('document_management:registry_hub')

    def handle_no_permission(self):
        messages.error(self.request, "You do not have permission to archive files.")
        return redirect('document_management:registry_hub')

class DirectorAdminDashboardView(HTMXLoginRequiredMixin, UserPassesTestMixin, ListView):
    model = File
    template_name = "document_management/admin_dashboard.html"
    context_object_name = "recent_files"

    def test_func(self):
        return self.request.user.is_superuser

    def get_staff_user(self):
        try:
            return Staff.objects.get(user=self.request.user)
        except Staff.DoesNotExist:
            return None

    def get_queryset(self):
        return File.objects.all().order_by("-created_at")[:10]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_files_count"] = File.objects.count()
        context["active_files_count"] = File.objects.filter(status="active").count()
        context["pending_activation_count"] = File.objects.filter(status="pending_activation").count()
        context["archived_files_count"] = File.objects.filter(status="archived").count()
        
        context["total_staff_count"] = Staff.objects.count()
        context["total_departments_count"] = Department.objects.count()
        
        today = timezone.now().date()
        context["actions_today"] = AuditLogEntry.objects.filter(timestamp__date=today).count()
        context["recent_activities"] = AuditLogEntry.objects.select_related('user').all()[:10]
        
        return context

    def handle_no_permission(self):
        messages.error(self.request, "Only directors/superusers can access the admin dashboard.")
        return redirect("document_management:my_files")

class FileDeleteView(HTMXLoginRequiredMixin, UserPassesTestMixin, View):
    """Delete a file (folder) container. Only Registry or Superusers can delete files."""
    
    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
        try:
            return user.staff.is_registry
        except AttributeError:
            return False

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        file_number = file_obj.file_number
        
        log_action(
            request.user,
            "FILE_DELETED",
            request=request,
            details={"file_number": file_number, "title": file_obj.title}
        )
        
        file_obj.delete()
        messages.success(request, f"File {file_number} deleted successfully.")
        return redirect('document_management:registry_hub')

class RecordExplorerView(HTMXLoginRequiredMixin, ListView):
    model = File
    template_name = "document_management/record_explorer.html"
    context_object_name = "files"
    paginate_by = 20

    def get_queryset(self):
        queryset = File.objects.filter(status='active').order_by('file_number')
        
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(
                Q(file_number__icontains=q) |
                Q(title__icontains=q) |
                Q(department__name__icontains=q)
            )
            
        dept = self.request.GET.get('department')
        if dept:
            queryset = queryset.filter(department_id=dept)
            
        return queryset

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            target = self.request.headers.get("HX-Target", "")
            if target == "file-detail-content":
                return ["document_management/partials/_explorer_file_detail.html"]
            return ["document_management/partials/_explorer_sidebar_list.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['departments'] = Department.objects.all().order_by('name')
        context['selected_dept'] = self.request.GET.get('department', '')
        context['q'] = self.request.GET.get('q', '')

        file_pk = self.request.GET.get('file_pk')
        if file_pk:
            try:
                selected_file = File.objects.get(pk=file_pk)
                documents = selected_file.documents.order_by('-uploaded_at')[:10]
                context['selected_file'] = selected_file
                context['documents'] = documents
                context['has_more_documents'] = selected_file.documents.count() > 10
            except File.DoesNotExist:
                pass

        return context

    def get_staff_user(self):
        try:
            return Staff.objects.get(user=self.request.user)
        except Staff.DoesNotExist:
            return None
