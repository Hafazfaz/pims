from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, View, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import HttpResponse # Import HttpResponse for HTMX responses
from .models import File, Document # Import Document model
from .forms import FileForm, DocumentForm, SendFileForm # Import the FileForm, DocumentForm, and SendFileForm

class RegistryDashboardView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = File
    template_name = 'document_management/registry_dashboard.html'
    context_object_name = 'files'
    permission_required = 'document_management.view_file' # Custom permission

    def get_queryset(self):
        # Display all files for the Registry dashboard
        return File.objects.all().order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pending_activation_files'] = File.objects.filter(status='pending_activation').order_by('-created_at')
        return context

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('user_management:login')
        return render(self.request, '403.html', status=403)

class FileCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = File
    form_class = FileForm
    template_name = 'document_management/file_form.html'
    success_url = reverse_lazy('document_management:registry_dashboard')
    permission_required = 'document_management.create_file'

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.current_location = self.request.user
        return super().form_valid(form)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('user_management:login')
        return render(self.request, '403.html', status=403)

class MyFilesView(LoginRequiredMixin, ListView):
    model = File
    template_name = 'document_management/my_files.html'
    context_object_name = 'owned_files' # Renamed to be specific

    def get_queryset(self):
        return File.objects.filter(owner=self.request.user).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['inbox_files'] = File.objects.filter(current_location=self.request.user).order_by('-created_at')
        return context

class FileRequestActivationView(LoginRequiredMixin, View):
    def post(self, request, pk):
        file = get_object_or_404(File, pk=pk, owner=request.user)
        if file.status == 'inactive':
            file.status = 'pending_activation'
            file.save()
            messages.success(request, f"Activation request for file '{file.title}' submitted.")
        else:
            messages.warning(request, f"File '{file.title}' is already {file.get_status_display()}.")
        return redirect('document_management:my_files')

class FileApproveActivationView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'document_management.activate_file'

    def post(self, request, pk):
        file = get_object_or_404(File, pk=pk)
        if file.status == 'pending_activation':
            file.status = 'active'
            file.save()
            messages.success(request, f"File '{file.title}' has been activated.")
        else:
            messages.warning(request, f"File '{file.title}' is not pending activation.")
        return redirect('document_management:registry_dashboard')

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('user_management:login')
        messages.error(self.request, "You do not have permission to approve file activations.")
        return redirect('document_management:registry_dashboard')

class FileDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = File
    template_name = 'document_management/file_detail.html'
    context_object_name = 'file'
    permission_required = 'document_management.view_file'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['documents'] = self.object.documents.all()
        context['document_form'] = DocumentForm() # Add an empty form for GET requests
        context['send_file_form'] = SendFileForm() # Add an empty form for GET requests
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Determine which form was submitted
        if 'minute_content' in request.POST or 'attachment' in request.FILES:
            # DocumentForm submission
            if not (request.user.has_perm('document_management.add_minute') or request.user.has_perm('document_management.add_attachment')):
                messages.error(request, "You do not have permission to add documents or minutes to this file.")
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
                context['document_form'] = form
                return self.render_to_response(context)
        elif 'recipient' in request.POST:
            # SendFileForm submission
            if not request.user.has_perm('document_management.send_file'):
                messages.error(request, "You do not have permission to send files.")
                return redirect(self.object.get_absolute_url())

            form = SendFileForm(request.POST)
            if form.is_valid():
                recipient = form.cleaned_data['recipient']
                self.object.current_location = recipient
                self.object.save()
                messages.success(request, f"File sent to {recipient.get_full_name() or recipient.username}.")
                # For HTMX, we might want to return a partial update or a header
                if request.headers.get('HX-Request'):
                    # If it's an HTMX request, just return a success message or refresh a component
                    return HttpResponse(f'<div class="alert alert-success" role="alert">File sent to {recipient.get_full_name() or recipient.username}.</div>')
                return redirect(self.object.get_absolute_url())
            else:
                context = self.get_context_data()
                context['send_file_form'] = form
                if request.headers.get('HX-Request'):
                    # If HTMX, return the form with errors
                    return render(request, 'document_management/partials/send_file_form.html', context)
                return self.render_to_response(context)
        
        # Fallback if no form is recognized
        messages.error(request, "Invalid form submission.")
        return redirect(self.object.get_absolute_url())

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('user_management:login')
        messages.error(self.request, "You do not have permission to view this file.")
        return redirect('document_management:my_files')
