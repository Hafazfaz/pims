from audit_log.utils import log_action  # Import audit logging utility
from django.contrib import messages
from django.contrib.auth.mixins import (LoginRequiredMixin,
                                        PermissionRequiredMixin,
                                        UserPassesTestMixin)
from django.db.models import Q  # Import Q for complex lookups
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import (CreateView, DetailView, ListView, UpdateView,
                                  View)
from notifications.utils import \
    create_notification  # Import notification utility
from organization.models import Staff

from .forms import (DocumentForm, DocumentUploadForm, FileForm, FileUpdateForm,
                    SendFileForm)
from .models import Document, File
from django.utils import timezone
from datetime import timedelta
from organization.models import Department, Staff


class RegistryDashboardView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = File
    template_name = "document_management/registry_dashboard.html"
    context_object_name = "files"
    permission_required = "document_management.view_file"  # Custom permission

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")

        queryset = File.objects.filter(owner__unit=staff_user.unit)

        # Apply search filters
        search_query = self.request.GET.get("q")
        file_type = self.request.GET.get("file_type")
        status = self.request.GET.get("status")
        owner_id = self.request.GET.get("owner")
        current_location_id = self.request.GET.get("current_location")
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")

        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query)
                | Q(file_number__icontains=search_query)
            )
        if file_type:
            queryset = queryset.filter(file_type=file_type)
        if status:
            queryset = queryset.filter(status=status)
        if owner_id:
            queryset = queryset.filter(owner_id=owner_id)
        if current_location_id:
            queryset = queryset.filter(current_location_id=current_location_id)
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)

        # Exclude archived files from the main list by default, but allow explicit search
        if status != "archived":
            queryset = queryset.exclude(status="archived")

        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")

        # Pending activation files and archived files (unchanged)
        context["pending_activation_files"] = File.objects.filter(
            status="pending_activation", owner__unit=staff_user.unit
        ).order_by("-created_at")
        context["archived_files"] = File.objects.filter(
            status="archived", owner__unit=staff_user.unit
        ).order_by("-created_at")

        # Add filter options to context for form stickiness and dropdowns
        context["all_file_types"] = File.FILE_TYPE_CHOICES
        context["all_statuses"] = File.STATUS_CHOICES
        context["all_owners_in_unit"] = Staff.objects.filter(
            unit=staff_user.unit
        ).order_by("user__username")
        context["all_locations_in_unit"] = Staff.objects.filter(
            unit=staff_user.unit
        ).order_by("user__username")

        context["selected_search_query"] = self.request.GET.get("q", "")
        context["selected_file_type"] = self.request.GET.get("file_type", "")
        context["selected_status"] = self.request.GET.get("status", "")
        context["selected_owner"] = self.request.GET.get("owner", "")
        context["selected_current_location"] = self.request.GET.get(
            "current_location", ""
        )
        context["selected_start_date"] = self.request.GET.get("start_date", "")
        context["selected_end_date"] = self.request.GET.get("end_date", "")

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


class HODDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = File
    template_name = "document_management/hod_dashboard.html"
    context_object_name = "files"

    def test_func(self):
        staff_user = self.get_staff_user()
        return staff_user and (staff_user.is_hod or self.request.user.is_superuser)

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
        context["archived_files_count"] = department_files.filter(
            status="archived"
        ).count()

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


class FileCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = File
    form_class = FileForm
    template_name = "document_management/file_form.html"
    success_url = reverse_lazy("document_management:registry_dashboard")
    permission_required = "document_management.create_file"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = self.get_staff_user()
        if not user:
            raise Http404("Staff user not found or doesn't exist.")

        form.instance.current_location = user
        form.instance.department = user.department

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


class MyFilesView(LoginRequiredMixin, ListView):
    model = File
    template_name = "document_management/my_files.html"
    context_object_name = "owned_files"  # Renamed to be specific

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        return File.objects.filter(owner=staff_user).order_by("-created_at")

    def get_context_data(self, **kwargs):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        context = super().get_context_data(**kwargs)
        context["inbox_files"] = File.objects.filter(
            current_location=staff_user
        ).order_by("-created_at")
        return context

    def get_staff_user(self):
        user = self.request.user
        try:
            staff = Staff.objects.get(user=user)
            return staff
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
            file.status = "pending_activation"
            file.save()
            messages.success(
                request, f"Activation request for file '{file.title}' submitted."
            )
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
        return redirect("document_management:registry_dashboard")

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(
            self.request, "You do not have permission to approve file activations."
        )
        return redirect("document_management:registry_dashboard")


class FileDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = File
    template_name = "document_management/file_detail.html"
    context_object_name = "file"
    permission_required = "document_management.view_file"

    def has_permission(self):
        # First, check if the user has the general 'view_file' permission
        if not super().has_permission():
            return False

        # Get the file object that is being accessed
        try:
            target_file = self.get_object()
        except Http404:
            return False  # File not found, so no permission

        user = self.request.user
        # Admins/Superusers always have access
        if user.is_superuser or user.is_staff:
            return True

        # Try to get the Staff object for the current user
        staff_user = None
        try:
            staff_user = Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return False  # User is not a staff member, so no access beyond generic permission

        # Check if the user is the owner or has the file in their current location
        if (
            staff_user == target_file.owner
            or staff_user == target_file.current_location
        ):
            return True

        # Logic for Registry to access files within their unit
        if staff_user and staff_user.is_registry and staff_user.unit:
            if target_file.owner and target_file.owner.unit == staff_user.unit:
                return True

        # Logic for HODs to access files within their department
        if staff_user and staff_user.is_hod and staff_user.department:
            if (
                target_file.owner
                and target_file.owner.department == staff_user.department
            ):
                return True

        # If none of the above conditions are met, deny permission
        return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch only top-level documents (those without a parent)
        context["documents"] = self.object.documents.filter(parent__isnull=True).order_by("-uploaded_at")
        context["document_form"] = DocumentForm()
        context["send_file_form"] = SendFileForm(user=self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Determine which form was submitted
        if "minute_content" in request.POST or "attachment" in request.FILES:
            # DocumentForm submission
            if not (
                request.user.has_perm("document_management.add_minute")
                or request.user.has_perm("document_management.add_attachment")
            ):
                messages.error(
                    request,
                    "You do not have permission to add documents or minutes to this file.",
                )
                return redirect(self.object.get_absolute_url())

            form = DocumentForm(request.POST, request.FILES)
            if form.is_valid():
                document = form.save(commit=False)
                document.file = self.object
                document.uploaded_by = request.user
                document.save()
                log_action(
                    request.user,
                    "DOCUMENT_ADDED",
                    request=request,
                    obj=document,
                    details={"file_id": self.object.pk},
                )
                messages.success(request, "Document/Minute added successfully.")
                return redirect(self.object.get_absolute_url())
            else:
                context = self.get_context_data()
                context["document_form"] = form
                return self.render_to_response(context)
        elif "recipient" in request.POST:
            # SendFileForm submission
            if not request.user.has_perm("document_management.send_file"):
                messages.error(request, "You do not have permission to send files.")
                return redirect(self.object.get_absolute_url())

            # Check if the file is active before sending
            if self.object.status == "inactive":
                messages.error(
                    request,
                    f"File '{self.object.title}' must be active to be sent. Current status: {self.object.get_status_display()}.",
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
                self.object.save()
                log_action(
                    request.user,
                    "FILE_SENT",
                    request=request,
                    obj=self.object,
                    details={
                        "from_location": str(previous_location),
                        "to_location": str(recipient_staff),
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
        # Only the owner of the file can update it
        file = self.get_object()
        user_staff = None
        try:
            user_staff = Staff.objects.get(user=self.request.user)
        except Staff.DoesNotExist:
            return False  # Not a staff user

        return file.owner == user_staff

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


class FileCloseView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "document_management.close_file"

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
        messages.error(self.request, "You do not have permission to close files.")
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
        recipients = Staff.objects.filter(
            Q(headed_department__isnull=False) | Q(headed_unit__isnull=False)
        ).filter(
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(department__name__icontains=query) |
            Q(unit__name__icontains=query)
        ).distinct()[:10]  # Limit results to 10 for performance

        return render(request, 'document_management/recipient_search_results.html', {
            'recipients': recipients,
            'query': query
        })
