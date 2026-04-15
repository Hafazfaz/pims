from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import CreateView, DetailView, ListView, View
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth import get_user_model
from audit_log.utils import log_action
from notifications.utils import create_notification
from organization.models import Staff
from ..models import File, Document, FileAccessRequest
from ..forms import DocumentForm, DocumentUploadForm
from .base import HTMXLoginRequiredMixin

class DocumentUploadView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentUploadForm
    template_name = "document_management/document_upload_form.html"

    def get_file(self):
        file_pk = self.kwargs.get('file_pk') or self.request.GET.get('file_pk')
        if file_pk:
            return get_object_or_404(File, pk=file_pk)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        file = self.get_file()
        if file:
            initial['file'] = file
        parent_id = self.request.GET.get('parent_id')
        if parent_id:
            initial['parent'] = parent_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['preselected_file'] = self.get_file()
        return context

    def get_success_url(self):
        file = self.get_file()
        if file:
            return reverse_lazy("document_management:file_detail", kwargs={"pk": file.pk})
        return reverse_lazy("document_management:my_files")

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

class DocumentDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Delete a document from a file.
    Only Registry or users with active Read-Write access can delete documents.
    """

    def test_func(self):
        document = get_object_or_404(Document, pk=self.kwargs['pk'])
        file_obj = document.file
        user = self.request.user

        active_access = FileAccessRequest.objects.filter(
            file=file_obj,
            requested_by=user,
            status='approved',
            access_type='read_write'
        ).first()

        if active_access and active_access.is_active:
            return True

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
        
        document.delete()
        
        messages.success(request, "Document deleted successfully.")
        return redirect(file_obj.get_absolute_url())

class DocumentDetailView(HTMXLoginRequiredMixin, DetailView):
    """
    Detailed view of a single document from a file's chronicle.
    Allows users to view the full document content and dispatch actions.
    """
    model = Document
    template_name = "document_management/document_detail.html"
    context_object_name = "document"

    def has_permission(self):
        document = self.get_object()
        file_obj = document.file
        user = self.request.user

        try:
            staff_user = Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return False

        if (staff_user == file_obj.owner or staff_user == file_obj.current_location):
            return True

        if staff_user and staff_user.is_registry:
            return True

        if staff_user and staff_user.is_hod and staff_user.department:
            if (file_obj.owner and file_obj.owner.department == staff_user.department):
                return True

        active_request = FileAccessRequest.objects.filter(
            file=file_obj,
            requested_by=user,
            status='approved',
            access_type='read_write'
        ).filter(
            Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
        ).exists()
        if active_request:
            return True

        if document.shared_with.filter(id=user.id).exists():
            return True

        return False

    def dispatch(self, request, *args, **kwargs):
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
        
        is_registry = False
        try:
            is_registry = self.request.user.staff.is_registry
        except AttributeError:
            pass
        
        is_custodian = hasattr(self.request.user, 'staff') and file_obj.current_location == self.request.user.staff
        
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
        
        context["can_add_minute"] = is_registry or is_custodian or (
            has_approved_access and 
            access_type == 'read_write' and 
            file_obj.status == 'active'
        )
        
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

class DocumentShareView(LoginRequiredMixin, View):
    def post(self, request, pk):
        User = get_user_model()
        document = get_object_or_404(Document, pk=pk)
        
        file = document.file
        user = request.user
        staff = None
        try:
             staff = user.staff
        except AttributeError:
             pass

        is_registry = staff.is_registry if staff else False
        is_owner = staff == file.owner if staff else False
        is_custodian = staff == file.current_location if staff else False
        
        has_access = FileAccessRequest.objects.filter(
            file=file, 
            requested_by=user, 
            status="approved",
            access_type='read_write'
        ).filter(
            Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)
        ).exists()

        if not (is_registry or is_owner or is_custodian or has_access):
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

class DocumentDownloadView(LoginRequiredMixin, View):
    """
    Serves a document attachment only if the user has approved access to the file
    (read_only or read_write), is the owner/custodian, registry, or the uploader.
    """
    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        file_obj = document.file
        user = request.user

        # Check permission
        allowed = False
        staff = getattr(user, 'staff', None)

        if user.is_superuser:
            allowed = True
        elif staff:
            if staff.is_registry or staff == file_obj.owner or staff == file_obj.current_location:
                allowed = True
            elif staff.is_hod and file_obj.owner and file_obj.owner.department == staff.department:
                allowed = True
        
        if not allowed and document.uploaded_by == user:
            allowed = True

        if not allowed:
            allowed = FileAccessRequest.objects.filter(
                file=file_obj,
                requested_by=user,
                status='approved'
            ).filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).exists()

        if not allowed:
            allowed = document.shared_with.filter(pk=user.pk).exists()

        if not allowed:
            messages.error(request, "You do not have permission to download this document.")
            return redirect(file_obj.get_absolute_url())

        import mimetypes
        from django.http import FileResponse
        file_path = document.attachment.path
        mime_type, _ = mimetypes.guess_type(file_path)
        response = FileResponse(open(file_path, 'rb'), content_type=mime_type or 'application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{document.attachment.name.split("/")[-1]}"'
        log_action(user, "DOCUMENT_DOWNLOADED", request=request, obj=document)
        return response
    model = Document
    form_class = DocumentForm
    template_name = "document_management/document_create.html"

    def dispatch(self, request, *args, **kwargs):
        self.file_obj = get_object_or_404(File, pk=self.kwargs.get('file_pk'))
        
        staff_user = getattr(request.user, 'staff', None)
        
        has_approved_access = FileAccessRequest.objects.filter(
            file=self.file_obj,
            requested_by=request.user,
            status='approved',
            access_type='read_write'
        ).filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).exists()

        if has_approved_access:
             if self.file_obj.status != 'active':
                messages.error(request, "Documents can only be added to active files.")
                return redirect(self.file_obj.get_absolute_url())
             return super().dispatch(request, *args, **kwargs)

        has_permission = False
        
        if self.file_obj.file_type == 'personal':
            if self.file_obj.owner == staff_user:
                has_permission = True
        
        elif self.file_obj.file_type == 'policy':
             if staff_user and staff_user.is_hod and self.file_obj.department == staff_user.department:
                 has_permission = True
        
        else:
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
        
        if hasattr(self.request.user, 'staff'):
            context['active_signature'] = self.request.user.staff.get_active_signature()
            
        return context

    def form_valid(self, form):
        form.instance.file = self.file_obj
        form.instance.uploaded_by = self.request.user
        
        if self.file_obj.active_dispatch_document:
            is_custodian = hasattr(self.request.user, 'staff') and self.file_obj.current_location == self.request.user.staff
            if is_custodian:
                if form.instance.parent == self.file_obj.active_dispatch_document:
                    self.file_obj.clear_dispatch()

        response = super().form_valid(form)
        document = self.object
        
        if form.cleaned_data.get('include_signature'):
            try:
                staff = self.request.user.staff
                active_sig = staff.get_active_signature()
                if active_sig:
                    from ..models import DocumentSignature
                    DocumentSignature.objects.create(
                        document=document,
                        signatory=self.request.user,
                        signature_record=active_sig
                    )
                else:
                    messages.warning(self.request, "You checked 'Attach Digital Signature' but have no signature uploaded in your profile.")
            except Exception:
                pass
                
        send_to_staff = form.cleaned_data.get('send_to')
        if send_to_staff:
            self.file_obj.current_location = send_to_staff
            self.file_obj.save()
            
            log_action(
                self.request.user,
                "FILE_SENT",
                request=self.request,
                obj=self.file_obj,
                details={"to": send_to_staff.user.get_full_name()}
            )
            create_notification(
                user=send_to_staff.user,
                message=f"{self.request.user.get_full_name()} sent you file {self.file_obj.file_number} — {self.file_obj.title}.",
                obj=self.file_obj,
                link=self.file_obj.get_absolute_url()
            )
            messages.success(self.request, f"Document added and routed to {send_to_staff.user.get_full_name()} for review.")
        else:
            messages.success(self.request, "Document/Minute added successfully.")
        
        log_action(
            self.request.user,
            "DOCUMENT_ADDED",
            request=self.request,
            obj=document,
            details={"file_id": self.file_obj.pk},
        )
        return response

    def get_success_url(self):
        return self.file_obj.get_absolute_url()
