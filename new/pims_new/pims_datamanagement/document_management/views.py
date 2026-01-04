from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, View

from .forms import DocumentForm, FileForm, SendFileForm
from .models import Document, File
from organization.models import Staff


class RegistryDashboardView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = File
    template_name = "document_management/registry_dashboard.html"
    context_object_name = "files"
    permission_required = "document_management.view_file"  # Custom permission

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        return File.objects.filter(owner__unit=staff_user.unit).order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        context["pending_activation_files"] = File.objects.filter(
            status="pending_activation", owner__unit=staff_user.unit
        ).order_by("-created_at")
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
            return False # File not found, so no permission

        user = self.request.user
        # Admins/Superusers always have access
        if user.is_superuser or user.is_staff:
            return True

        # Try to get the Staff object for the current user
        staff_user = None
        try:
            staff_user = Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return False # User is not a staff member, so no access beyond generic permission

        # Check if the user is the owner or has the file in their current location
        if staff_user == target_file.owner or staff_user == target_file.current_location:
            return True

        # Logic for Registry and HODs to access files within their unit
        if staff_user and staff_user.unit: # Ensure the current user is associated with a unit
            # Check if the current user is a Registry or HOD
            if staff_user.is_registry or staff_user.is_hod:
                if target_file.owner and target_file.owner.unit == staff_user.unit:
                    return True

        # If none of the above conditions are met, deny permission
        return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["documents"] = self.object.documents.all()
        context["document_form"] = DocumentForm()
        context["send_file_form"] = SendFileForm()
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

            form = SendFileForm(request.POST)
            if form.is_valid():
                recipient = form.cleaned_data["recipient"]
                self.object.current_location = recipient
                self.object.save()
                messages.success(
                    request,
                    f"File sent to {recipient.get_full_name() or recipient.username}.",
                )
                # For HTMX, we might want to return a partial update or a header
                if request.headers.get("HX-Request"):
                    # If it's an HTMX request, just return a success message or refresh a component
                    return HttpResponse(
                        f'<div class="alert alert-success" role="alert">File sent to {recipient.get_full_name() or recipient.username}.</div>'
                    )
                return redirect(self.object.get_absolute_url())
            else:
                context = self.get_context_data()
                context["send_file_form"] = form
                if request.headers.get("HX-Request"):
                    # If HTMX, return the form with errors as an alert
                    error_html = '<div class="alert alert-danger" role="alert"><p class="mb-1"><strong>Error sending file:</strong></p><ul class="mb-0">'
                    for field in form:
                        for error in field.errors:
                            error_html += f"<li>{field.label}: {error}</li>"
                    for error in form.non_field_errors():
                        error_html += f"<li>{error}</li>"
                    error_html += "</ul></div>"
                    return self.render_to_response(context)
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
    template_name = "document_management/file_form.html" # Reusing the form template
    context_object_name = "file"

    def get_success_url(self):
        return reverse_lazy("document_management:file_detail", kwargs={"pk": self.object.pk})

    def test_func(self):
        # Only the owner of the file can update it
        file = self.get_object()
        user_staff = None
        try:
            user_staff = Staff.objects.get(user=self.request.user)
        except Staff.DoesNotExist:
            return False # Not a staff user

        return file.owner == user_staff

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("user_management:login")
        messages.error(self.request, "You do not have permission to edit this file.")
        return redirect("document_management:my_files")


class DocumentUploadView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentUploadForm
    template_name = "document_management/document_upload_form.html" # A new template for this
    success_url = reverse_lazy("document_management:my_files")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
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