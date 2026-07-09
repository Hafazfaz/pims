import contextlib

from audit_log.utils import log_action
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, View
from notifications.utils import create_notification
from organization.models import Staff

from ..forms import DocumentForm, DocumentUploadForm, SendFileForm
from ..models import Document, File, FileAccessRequest, FileMovement
from .base import HTMXLoginRequiredMixin


class DocumentUploadView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentUploadForm
    template_name = "document_management/document_upload_form.html"

    def get_file(self):
        file_pk = self.kwargs.get("file_pk") or self.request.GET.get("file_pk")
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
            initial["file"] = file
        parent_id = self.request.GET.get("parent_id")
        if parent_id:
            initial["parent"] = parent_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["preselected_file"] = self.get_file()
        return context

    def get_success_url(self):
        file = self.get_file()
        if file:
            return reverse_lazy("document_management:file_detail", kwargs={"pk": file.pk})
        return reverse_lazy("document_management:my_files")

    def form_valid(self, form):
        document = form.save(commit=False)
        document.priority = form.cleaned_data.get("priority", "normal")
        file_obj = document.file
        user = self.request.user
        staff = getattr(user, "staff", None)

        is_registry = staff and staff.is_registry
        is_custodian = staff and file_obj.current_location == staff
        has_rw = (
            is_custodian
            and FileAccessRequest.objects.filter(
                file=file_obj, requested_by=user, status="approved", access_type="read_write"
            )
            .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
            .exists()
        )

        if not (is_registry or has_rw):
            messages.error(self.request, "You do not have permission to add documents to this file.")
            return redirect(file_obj.get_absolute_url())

        document.uploaded_by = user
        document.save()
        messages.success(self.request, "Document uploaded successfully.")
        return redirect(self.get_success_url())

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "You do not have permission to upload documents.")
        return redirect("document_management:my_files")


class DocumentDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Delete a document from a file.
    Only Registry or users with active Read-Write access can delete documents.
    """

    def test_func(self):
        document = get_object_or_404(Document, pk=self.kwargs["pk"])
        file_obj = document.file
        user = self.request.user

        active_access = FileAccessRequest.objects.filter(
            file=file_obj, requested_by=user, status="approved", access_type="read_write"
        ).first()

        if active_access and active_access.is_active:
            return True

        return document.uploaded_by == user

    def post(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        file_obj = document.file

        log_action(
            request.user,
            "DOCUMENT_DELETED",
            request=request,
            obj=file_obj,
            details={"document_title": document.title, "document_id": document.pk},
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
        if not self.request.user.is_authenticated:
            return False
        document = self.get_object()
        file_obj = document.file
        user = self.request.user

        try:
            staff_user = Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return False

        # Only HODs, Supervisors, Executives, and MD can view document contents
        # Registry and general staff cannot view document contents
        from ..permissions import can_view_document_content

        if not can_view_document_content(user):
            return False

        if staff_user == file_obj.current_location:
            return True

        # Registry content restriction is already enforced above

        active_request = (
            FileAccessRequest.objects.filter(
                file=file_obj,
                requested_by=user,
                status="approved",
            )
            .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
            .exists()
        )
        if active_request:
            return True

        if document.shared_with.filter(id=user.id).exists():
            return True

        # Allow recipient of a pending movement to view the document
        if FileMovement.objects.filter(document=document, sent_to=staff_user, status="pending").exists():
            return True

        # Allow current approver on the chain to view the document
        active_chain = document.approval_chains.filter(status="active").first()
        return bool(active_chain and active_chain.steps.filter(approver=staff_user).exists())

    def dispatch(self, request, *args, **kwargs):
        if not self.has_permission():
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.object
        file_obj = document.file

        is_registry = False
        with contextlib.suppress(AttributeError):
            is_registry = self.request.user.staff.is_registry

        is_custodian = hasattr(self.request.user, "staff") and file_obj.current_location == self.request.user.staff
        is_owner = hasattr(self.request.user, "staff") and file_obj.owner == self.request.user.staff

        has_approved_access = (
            FileAccessRequest.objects.filter(file=file_obj, requested_by=self.request.user, status="approved")
            .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
            .exists()
        )

        access_type = None
        if has_approved_access:
            active_access = (
                FileAccessRequest.objects.filter(file=file_obj, requested_by=self.request.user, status="approved")
                .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
                .first()
            )
            if active_access:
                access_type = active_access.access_type

        context["can_add_minute"] = (
            is_registry or (is_custodian and access_type == "read_write")
        ) and file_obj.status == "active"

        can_send_file = False
        # Can only dispatch if: active file, no active chain, AND not already approved
        if (
            file_obj.status == "active"
            and not file_obj.is_in_active_chain
            and document.status != "approved"
            and (is_owner or is_custodian or is_registry)
        ):
            can_send_file = True

        context["can_send_file"] = can_send_file
        context["has_active_chain"] = file_obj.is_in_active_chain
        context["document_is_approved"] = document.status == "approved"

        # Document chronicle
        doc_chronicle = []
        doc_chronicle.append({"type": "version", "item": document, "timestamp": document.uploaded_at})
        doc_chronicle.sort(key=lambda x: x["timestamp"])
        context["doc_chronicle"] = doc_chronicle

        # Send file form
        sender_staff = getattr(self.request.user, "staff", None)
        context["send_file_form"] = SendFileForm(
            user=self.request.user,
            file_obj=file_obj,
            document=document,
            staff=sender_staff,
        )

        # Build recipient list (same logic as file_detail)
        from organization.models import Department as Dept
        from organization.models import Unit

        from document_management.views.base import EXCLUDE_REGISTRY_Q

        base_qs = (
            Staff.objects.exclude(EXCLUDE_REGISTRY_Q)
            .exclude(user=self.request.user)
            .select_related("user", "designation", "unit", "department")
        )
        if sender_staff:
            if sender_staff.is_registry or sender_staff.is_md or sender_staff.is_executive:
                recipient_qs = base_qs
            elif sender_staff.is_hod or sender_staff.is_head_of_unit:
                pks = set()
                for d in Dept.objects.filter(head__isnull=False):
                    pks.add(d.head.pk)
                for u in Unit.objects.filter(head__isnull=False):
                    pks.add(u.head.pk)
                for s in base_qs.filter(is_supervisor=True):
                    pks.add(s.pk)
                pks.discard(sender_staff.pk)
                recipient_qs = base_qs.filter(pk__in=pks)
            elif sender_staff.is_supervisor:
                pks = set()
                for d in Dept.objects.filter(head__isnull=False):
                    pks.add(d.head.pk)
                for u in Unit.objects.filter(head__isnull=False):
                    pks.add(u.head.pk)
                recipient_qs = base_qs.filter(pk__in=pks)
            else:
                if sender_staff.unit and sender_staff.unit.head:
                    recipient_qs = base_qs.filter(pk=sender_staff.unit.head.pk)
                elif sender_staff.department and sender_staff.department.head:
                    recipient_qs = base_qs.filter(pk=sender_staff.department.head.pk)
                else:
                    recipient_qs = base_qs.none()
        else:
            recipient_qs = base_qs
        context["approver_choices"] = recipient_qs.order_by("user__last_name")

        return context

    def post(self, request, *args, **kwargs):
        document = self.get_object()
        file_obj = document.file
        staff_user = getattr(request.user, "staff", None)
        is_registry = staff_user and staff_user.is_registry

        is_custodian = staff_user and file_obj.current_location == staff_user
        is_owner = staff_user and file_obj.owner == staff_user

        if not (is_owner or is_custodian or is_registry):
            messages.error(request, "You do not have permission to send this file.")
            return redirect(request.path)

        if file_obj.status != "active":
            messages.error(request, "Only active files can be sent.")
            return redirect(request.path)

        form = SendFileForm(
            request.POST, request.FILES, user=request.user, file_obj=file_obj, document=document, staff=staff_user
        )
        if not form.is_valid():
            messages.error(request, "Please correct the form errors.")
            return redirect(request.path)

        recipient_user = form.cleaned_data["recipient"]
        try:
            recipient = recipient_user.staff
        except Staff.DoesNotExist:
            messages.error(request, "Selected recipient has no staff profile.")
            return redirect(request.path)

        # Routing rules
        if not is_registry and staff_user:
            if staff_user.is_md or staff_user.is_executive:
                pass  # can send to anyone
            elif staff_user.is_hod or staff_user.is_head_of_unit:
                # HOD / Head of Unit → any HOD, any head of unit, any supervisor
                from organization.models import Department as Dept
                from organization.models import Staff as StaffModel

                allowed_pks = set()
                for d in Dept.objects.filter(head__isnull=False):
                    allowed_pks.add(d.head.pk)
                for s in StaffModel.objects.filter(is_supervisor=True):
                    allowed_pks.add(s.pk)
                # all heads of unit
                from organization.models import Unit

                for u in Unit.objects.filter(head__isnull=False):
                    allowed_pks.add(u.head.pk)
                allowed_pks.discard(staff_user.pk)
                if recipient.pk not in allowed_pks:
                    messages.error(request, "You can only send to a HOD, head of unit, or supervisor.")
                    return redirect(request.path)
            elif staff_user.is_supervisor:
                # Supervisor (non-HOD, non-unit-manager) → unit managers or HODs only
                from organization.models import Department as Dept
                from organization.models import Staff as StaffModel

                allowed_pks = set()
                for d in Dept.objects.filter(head__isnull=False):
                    allowed_pks.add(d.head.pk)
                for s in StaffModel.objects.filter(is_head_of_unit=True):
                    allowed_pks.add(s.pk)
                if recipient.pk not in allowed_pks:
                    messages.error(request, "Supervisors can only send to unit managers or HODs.")
                    return redirect(request.path)
            else:
                # Regular staff → unit manager if exists, else HOD
                allowed_pks = set()
                if staff_user.unit and staff_user.unit.head:
                    allowed_pks.add(staff_user.unit.head.pk)
                elif staff_user.department and staff_user.department.head:
                    allowed_pks.add(staff_user.department.head.pk)
                if recipient.pk not in allowed_pks:
                    messages.error(
                        request,
                        "You can only send this file to your unit manager, or your HOD if there is no unit manager.",
                    )
                    return redirect(request.path)

        old_location = file_obj.current_location
        FileMovement.objects.create(
            file=file_obj,
            document=document,
            sent_by=request.user,
            from_location=old_location,
            sent_to=recipient,
            note=form.cleaned_data.get("note", ""),
            attachment=form.cleaned_data.get("movement_attachment"),
            action="sent",
        )

        # Attach reference documents to the movement's version_reference (first one) or store via M2M on chain
        # Since we're not using chains, store them on the document's shared_with or just log them
        ref_docs = form.cleaned_data.get("reference_documents")
        if ref_docs:
            # Tag the document as shared with the recipient so they can see the refs
            document.shared_with.add(recipient_user)
            for ref in ref_docs:
                ref.shared_with.add(recipient_user)

        # Auto-grant read-only access to the file for the recipient
        FileAccessRequest.objects.get_or_create(
            file=file_obj,
            requested_by=recipient_user,
            defaults={
                "reason": f"Auto-granted: file sent by {request.user.get_full_name() or request.user.username}",
                "access_type": "read_only",
                "status": "approved",
            },
        )
        # Auto-grant read-only access for the sender so they can still view after sending
        FileAccessRequest.objects.get_or_create(
            file=file_obj,
            requested_by=request.user,
            defaults={
                "reason": "Auto-granted: sender retains read-only access",
                "access_type": "read_only",
                "status": "approved",
            },
        )

        document.status = "in_transit"
        document.save(update_fields=["status"])

        file_obj.current_location = recipient
        file_obj.status = "in_transit"
        file_obj.save()

        log_action(
            request.user,
            "FILE_SENT",
            request=request,
            obj=file_obj,
            details={"to": recipient.user.get_full_name(), "document_id": document.pk},
        )
        create_notification(
            user=recipient_user,
            message=(
                f"{request.user.get_full_name() or request.user.username} "
                f"sent you file {file_obj.file_number} "
                f"with document: {document.title or 'Untitled'}."
            ),
            obj=file_obj,
            link=reverse_lazy("document_management:inbox"),
        )
        messages.success(request, f"File sent to {recipient.user.get_full_name() or recipient_user.username}.")
        return redirect(file_obj.get_absolute_url())

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["document_management/partials/_document_panel.html"]
        return [self.template_name]

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
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
        document = get_object_or_404(Document, pk=pk)
        from ..permissions import can_view_document_content

        if not can_view_document_content(request.user) and document.uploaded_by != request.user:
            messages.error(request, "You do not have permission to share this document.")
            return redirect(document.file.get_absolute_url())
        user_ids = request.POST.getlist("user_ids")
        document.shared_with.set(user_ids)
        messages.success(request, "Document sharing updated.")
        return redirect("document_management:document_detail", pk=pk)


class DocumentNewVersionView(LoginRequiredMixin, View):
    """Create a new version of an existing document."""

    def post(self, request, pk):
        original = get_object_or_404(Document, pk=pk)
        from ..permissions import can_view_document_content, is_registry

        if (
            not can_view_document_content(request.user)
            and not is_registry(request.user)
            and original.uploaded_by != request.user
        ):
            messages.error(request, "You do not have permission to create a new version of this document.")
            return redirect(original.file.get_absolute_url())
        title = request.POST.get("title", original.title)
        minute_content = request.POST.get("minute_content", "").strip()
        attachment = request.FILES.get("attachment")

        # New version chains off the original via parent
        new_doc = Document.objects.create(
            file=original.file,
            uploaded_by=request.user,
            title=title or original.title,
            minute_content=minute_content or original.minute_content,
            document_type=original.document_type,
            parent=original,
        )
        if attachment:
            new_doc.attachment = attachment
            new_doc.save()

        messages.success(request, "New version created.")
        return redirect("document_management:document_detail", pk=original.pk)


class DocumentDownloadView(LoginRequiredMixin, View):
    """
    Serves a document attachment only if the user is HOD, Supervisor, Executive, or MD.
    Registry staff and general staff cannot download document contents.
    """

    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        file_obj = document.file
        user = request.user

        # Enforce content access restriction
        from ..permissions import can_view_document_content

        if not can_view_document_content(user):
            messages.error(request, "You do not have permission to download this document.")
            return redirect(file_obj.get_absolute_url())

        # Check permission
        allowed = False
        staff = getattr(user, "staff", None)

        if user.is_superuser or (
            staff
            and (staff.is_hod or staff.is_effective_supervisor or staff.is_executive or staff.is_md)
            and (
                staff == file_obj.owner
                or staff == file_obj.current_location
                or (staff.is_hod and file_obj.owner and file_obj.owner.department == staff.department)
            )
        ):
            allowed = True

        if (
            not allowed
            and document.uploaded_by == user
            and staff
            and (staff.is_hod or staff.is_effective_supervisor or staff.is_executive or staff.is_md)
        ):
            allowed = True

        if not allowed:
            allowed = (
                FileAccessRequest.objects.filter(file=file_obj, requested_by=user, status="approved")
                .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
                .exists()
            )

        if not allowed:
            allowed = document.shared_with.filter(pk=user.pk).exists()

        if not allowed:
            messages.error(request, "You do not have permission to download this document.")
            return redirect(file_obj.get_absolute_url())

        import mimetypes
        from pathlib import Path

        from django.http import FileResponse

        if not document.attachment:
            messages.error(request, "This document has no attachment.")
            return redirect(file_obj.get_absolute_url())

        file_path = document.attachment.path
        if not Path(file_path).exists():
            messages.error(request, "Attachment file not found on server.")
            return redirect(file_obj.get_absolute_url())

        mime_type, _ = mimetypes.guess_type(file_path)
        inline = request.GET.get("inline") == "1"
        disposition = "inline" if inline else f'attachment; filename="{document.attachment.name.split("/")[-1]}"'
        f = Path(file_path).open("rb")  # noqa: SIM115  # FileResponse manages closure
        response = FileResponse(f, content_type=mime_type or "application/octet-stream")
        response["Content-Disposition"] = disposition
        if inline:
            response["X-Frame-Options"] = "SAMEORIGIN"
        log_action(user, "DOCUMENT_DOWNLOADED", request=request, obj=document)
        return response


class DocumentCreateView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentForm
    template_name = "document_management/document_create.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.file_obj = get_object_or_404(File, pk=self.kwargs.get("file_pk"))

        staff_user = getattr(request.user, "staff", None)

        has_approved_access = (
            FileAccessRequest.objects.filter(
                file=self.file_obj, requested_by=request.user, status="approved", access_type="read_write"
            )
            .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
            .exists()
        )

        if has_approved_access:
            if self.file_obj.status != "active":
                messages.error(request, "Documents can only be added to active files.")
                return redirect(self.file_obj.get_absolute_url())
            return super().dispatch(request, *args, **kwargs)

        has_permission = False

        if staff_user and staff_user.is_registry:
            has_permission = True

        elif self.file_obj.file_type == "personal":
            if self.file_obj.owner == staff_user:
                has_permission = True

        elif self.file_obj.file_type == "policy":
            if staff_user and staff_user.is_hod and self.file_obj.department == staff_user.department:
                has_permission = True

        else:
            if self.file_obj.owner == staff_user:
                has_permission = True
            if staff_user and staff_user.is_hod and self.file_obj.department == staff_user.department:
                has_permission = True

        if not has_permission:
            messages.error(
                request, "You do not have permission to add documents to this file. Restricted to File Owner/HOD."
            )
            return redirect(self.file_obj.get_absolute_url())

        if self.file_obj.status != "active":
            messages.error(request, "Documents can only be added to active files.")
            return redirect(self.file_obj.get_absolute_url())

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        parent_id = self.request.GET.get("parent_id")
        if parent_id:
            initial["parent"] = parent_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["file"] = self.file_obj
        parent_id = self.request.GET.get("parent_id")
        if parent_id:
            context["parent_doc"] = get_object_or_404(Document, pk=parent_id)

        if hasattr(self.request.user, "staff"):
            context["active_signature"] = self.request.user.staff.get_active_signature()

        return context

    def form_valid(self, form):
        form.instance.file = self.file_obj
        form.instance.uploaded_by = self.request.user
        priority = form.cleaned_data.get("priority", "normal")
        if priority in ("urgent", "high") and not self.request.user.has_perm("user_management.can_set_urgent_priority"):
            priority = "normal"
        form.instance.priority = priority

        if getattr(self.file_obj, "active_dispatch_document", None):
            is_custodian = (
                hasattr(self.request.user, "staff") and self.file_obj.current_location == self.request.user.staff
            )
            if is_custodian and form.instance.parent == self.file_obj.active_dispatch_document:
                self.file_obj.clear_dispatch()

        response = super().form_valid(form)
        document = self.object

        # Send notifications for urgent/high priority documents
        if document.priority in ("urgent", "high"):
            from organization.models import Staff as StaffModel

            from document_management.views.base import EXCLUDE_REGISTRY_Q

            urgent_recipients = (
                StaffModel.objects.exclude(EXCLUDE_REGISTRY_Q).exclude(user=self.request.user).select_related("user")
            )
            priority_label = dict(Document.PRIORITY_CHOICES).get(document.priority, document.priority)
            for recipient_staff in urgent_recipients:
                create_notification(
                    user=recipient_staff.user,
                    message=(
                        f"{priority_label.upper()} Document: '{document.title or 'Untitled'}' "
                        f"added to file {self.file_obj.file_number} "
                        f"by {self.request.user.get_full_name() or self.request.user.username}."
                    ),
                    obj=self.file_obj,
                    link=self.file_obj.get_absolute_url(),
                )

        if form.cleaned_data.get("include_signature"):
            try:
                staff = self.request.user.staff
                active_sig = staff.get_active_signature()
                if active_sig:
                    from ..models import DocumentSignature

                    DocumentSignature.objects.create(
                        document=document, signatory=self.request.user, signature_record=active_sig
                    )
                else:
                    messages.warning(
                        self.request,
                        "You checked 'Attach Digital Signature' but have no signature uploaded in your profile.",
                    )
            except Exception:
                pass

        send_to_staff = form.cleaned_data.get("send_to")
        if send_to_staff:
            from_location = getattr(self.request.user, "staff", None)
            self.file_obj.current_location = send_to_staff
            self.file_obj.save()

            FileMovement.objects.create(
                file=self.file_obj,
                sent_by=self.request.user,
                from_location=from_location,
                sent_to=send_to_staff,
                action="sent",
                document=document,
            )

            log_action(
                self.request.user,
                "FILE_SENT",
                request=self.request,
                obj=self.file_obj,
                details={"to": send_to_staff.user.get_full_name()},
            )
            create_notification(
                user=send_to_staff.user,
                message=(
                    f"{self.request.user.get_full_name()} "
                    f"sent you file {self.file_obj.file_number} — {self.file_obj.title}."
                ),
                obj=self.file_obj,
                link=self.file_obj.get_absolute_url(),
            )
            messages.success(
                self.request, f"Document added and routed to {send_to_staff.user.get_full_name()} for review."
            )
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
