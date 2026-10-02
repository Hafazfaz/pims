import contextlib

from audit_log.utils import log_action
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, View
from notifications.utils import create_notification
from organization.models import Staff

from ..forms import DocumentForm, DocumentUploadForm, SendFileForm
from ..models import Document, File, FileAccessRequest, FileMovement
from .base import HTMXLoginRequiredMixin
from ..permissions import can_add_document, can_share_document


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
        # Registry uploads are official records: auto-approved. Everyone else's
        # uploads stay pending until an approver signs off. The file itself
        # keeps its current status (active until dispatched).
        if file_obj is not None and (user.is_superuser or is_registry):
            document.status = "approved"
        document.save()
        # Multi-file upload: first file lives on the document, the rest land
        # on DocumentAttachment rows.
        _save_extra_uploads(
            document,
            form.files.getlist("attachment"),
            skip=form.cleaned_data.get("attachment"),
            uploaded_by=user,
        )
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

        # Content ACL (role + owner/custodian/approved-request/movement/share),
        # evaluated against this specific document so approved documents stay
        # locked for standing access. Must pass file_obj AND document — file
        # level alone would wrongly admit owners to approved contents.
        from ..permissions import can_view_document_content, can_view_document

        if not can_view_document_content(user, file=file_obj, document=document):
            return False

        if can_view_document(user, document):
            return True

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

        # Allow holder of an active file-level movement (custodian dispatched
        # via Send Note / document route) to open any document in that file —
        # this is what lets the inbox file view link every row.
        latest = (
            FileMovement.objects.filter(file=file_obj, sent_to=staff_user, action="sent")
            .order_by("-moved_at")
            .first()
        )
        if latest and latest.is_active_access:
            return True

        return False

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

        # Same rule set as the endpoint (DocumentCreateView.dispatch), so the
        # button is only shown when adding will actually be allowed.
        context["can_add_minute"] = can_add_document(self.request.user, file_obj)

        from document_management.permissions import can_manual_dispatch

        can_send_file = False
        # Can only dispatch if: active file AND not already approved AND
        # sender holds a dispatch privilege (regular staff cannot dispatch).
        if (
            file_obj.status == "active"
            and document.status != "approved"
            and (is_owner or is_custodian or is_registry)
            and can_manual_dispatch(self.request.user)
        ):
            can_send_file = True

        context["can_send_file"] = can_send_file
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

        # Build recipient list using central permission function
        from document_management.permissions import get_dispatch_recipients

        recipient_qs = get_dispatch_recipients(self.request.user, file_obj)
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

        from document_management.permissions import can_manual_dispatch as _can_dispatch

        if not _can_dispatch(request.user):
            messages.error(
                request,
                "Only Registry, HODs, supervisors, and executives can dispatch files. "
                "Your documents route automatically to your head.",
            )
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

        # Validate routing using central permission function
        if not is_registry and staff_user:
            from document_management.permissions import get_dispatch_recipients

            allowed_recipients = get_dispatch_recipients(request.user, file_obj)
            if recipient.pk not in allowed_recipients.values_list("pk", flat=True):
                messages.error(
                    request,
                    "You can only send this file to your unit manager, HOD, or other authorized recipients based on your role.",
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

        # Attach reference documents: tag them as shared with the recipient
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

        # Send email when document reaches HOD (policy) or Owner (personal) for approval
        is_hod_recipient = recipient.is_hod and file_obj.file_type == "policy" and file_obj.department == recipient.department
        is_owner_recipient = file_obj.file_type == "personal" and file_obj.owner == recipient

        if is_hod_recipient or is_owner_recipient:
            approval_link = reverse_lazy("document_management:document_approve_dispatch", kwargs={"pk": document.pk})
            role = "Head of Department" if is_hod_recipient else "File Owner"
            create_notification(
                user=recipient_user,
                message=(
                    f"Action Required: Document '{document.title or 'Untitled'}' in file "
                    f"{file_obj.file_number} requires your approval as {role}."
                ),
                obj=file_obj,
                link=approval_link,
                send_email=True,
                email_template="emails/document_dispatch_approval.html",
                email_context={
                    "file": file_obj,
                    "document": document,
                    "sender": request.user,
                    "role": role,
                },
                email_subject=f"Action Required: Approve Document - {file_obj.file_number}",
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
        try:
            document = self.get_object()
            return redirect(document.file.get_absolute_url())
        except Exception:
            return redirect("document_management:my_files")


class FileDocumentsView(HTMXLoginRequiredMixin, ListView):
    model = Document
    template_name = "document_management/partials/_document_rows.html"
    context_object_name = "documents"
    paginate_by = 1

    def get_queryset(self):
        from django.http import Http404

        from ..permissions import can_view_staff_documents, has_content_scope

        # Registry (and anyone lacking view_staff_documents) must not page
        # through staff document titles either.
        if not can_view_staff_documents(self.request.user):
            return Document.objects.none()

        file_pk = self.kwargs.get("pk")
        # Enforce the same content-scope rule as My Files: viewers without
        # scope (owner, unit head, HOD/supervisor, custodian, grant, share)
        # get no rows. Owners paging their own personal file are allowed —
        # titles alone no longer leak beyond what they may view.
        try:
            file_obj = File.objects.select_related("owner").get(pk=file_pk)
        except File.DoesNotExist:
            raise Http404
        self._file_obj = file_obj
        staff = getattr(self.request.user, "staff", None)
        if staff and file_obj.file_type == "personal" and file_obj.owner_id == staff.pk:
            if not has_content_scope(self.request.user, file_obj):
                return Document.objects.none()
        queryset = Document.objects.filter(file_id=file_pk)

        search_query = self.request.GET.get("q")
        if search_query:
            queryset = queryset.filter(title__icontains=search_query)

        return queryset.order_by("-uploaded_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["file_id"] = self.kwargs.get("pk")
        context["file_obj"] = getattr(self, "_file_obj", None)
        context["selected_search_query"] = self.request.GET.get("q", "")
        staff = getattr(self.request.user, "staff", None)
        context["can_browse_subordinates"] = bool(
            staff and (staff.is_hod or staff.is_privileged_head or staff.is_head_of_unit)
        )
        return context


class DocumentShareView(LoginRequiredMixin, View):
    def post(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        from ..permissions import can_view_document_content

        if not can_view_document_content(request.user, file=document.file) and document.uploaded_by != request.user:
            messages.error(request, "You do not have permission to share this document.")
            return redirect(document.file.get_absolute_url())
        user_ids = request.POST.getlist("user_ids")
        document.shared_with.set(user_ids)
        messages.success(request, "Document sharing updated.")
        return redirect("document_management:document_detail", pk=pk)


class DocumentShareEmailView(LoginRequiredMixin, View):
    """
    Share a document via email with the sender's digital signature attached.
    Only available to users with can_share_documents permission (HODs).
    """

    def post(self, request, pk):
        from ..permissions import can_share_document

        from django.core.mail import send_mail
        from django.conf import settings

        document = get_object_or_404(Document, pk=pk)

        # Check permission
        if not can_share_document(request.user):
            messages.error(request, "You do not have permission to share documents.")
            return redirect(document.file.get_absolute_url())

        # Check if user has an active verified signature
        staff = getattr(request.user, "staff", None)
        if not staff:
            messages.error(request, "Staff profile not found.")
            return redirect(document.file.get_absolute_url())

        active_signature = staff.get_active_signature()
        if not active_signature or not active_signature.is_verified:
            messages.error(request, "You need an active digital signature to share documents.")
            return redirect(document.file.get_absolute_url())

        # Get email parameters
        recipient_email = request.POST.get("recipient_email", "").strip()
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()

        if not recipient_email:
            messages.error(request, "Recipient email is required.")
            return redirect(document.file.get_absolute_url())

        if not subject:
            subject = f"Shared Document: {document.title or 'Untitled'}"

        # Build email message
        sender_name = request.user.get_full_name() or request.user.username
        file_number = document.file.file_number

        email_message = f"""
{message}

---
Document: {document.title or 'Untitled'}
File: {file_number}
Shared by: {sender_name}
Department: {staff.department.name if staff.department else 'N/A'}
Date: {timezone.now().strftime("%B %d, %Y @ %H:%M")}

This document was shared via the Personnel Information Management System (PIMS).
"""

        # Attach signature image
        signature_attachment = None
        if active_signature.image:
            signature_attachment = active_signature.image

        try:
            send_mail(
                subject=subject,
                message=email_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
                attachments=[(f"signature_{staff.user.username}.png", signature_attachment.read(), "image/png")] if signature_attachment else None,
            )
            messages.success(request, f"Document shared successfully with {recipient_email}.")
            log_action(
                request.user,
                "DOCUMENT_SHARED_EMAIL",
                request=request,
                obj=document.file,
                details={"document_id": document.pk, "recipient": recipient_email, "subject": subject}
            )
        except Exception as e:
            messages.error(request, f"Failed to send email: {str(e)}")

        return redirect(document.file.get_absolute_url())


class DocumentNewVersionView(LoginRequiredMixin, View):
    """Create a new version of an existing document."""

    def post(self, request, pk):
        original = get_object_or_404(Document, pk=pk)
        from ..permissions import can_view_document_content, is_registry

        if (
            not can_view_document_content(request.user, file=original.file)
            and not is_registry(request.user)
            and original.uploaded_by != request.user
        ):
            messages.error(request, "You do not have permission to create a new version of this document.")
            return redirect(original.file.get_absolute_url())
        title = request.POST.get("title", original.title)
        minute_content = request.POST.get("minute_content", "").strip()
        uploads = request.FILES.getlist("attachment")

        # New version links to the original via parent.
        # Registry versions are official records: auto-approved. Other
        # versions start pending until approved.
        staff = getattr(request.user, "staff", None)
        new_status = (
            "approved"
            if (request.user.is_superuser or (staff and staff.is_registry))
            else "pending"
        )
        new_doc = Document.objects.create(
            file=original.file,
            uploaded_by=request.user,
            title=title or original.title,
            minute_content=minute_content or original.minute_content,
            document_type=original.document_type,
            parent=original,
            status=new_status,
        )
        if uploads:
            new_doc.attachment = uploads[0]
            new_doc.save()
            _save_extra_uploads(new_doc, uploads[1:], uploaded_by=request.user)

        messages.success(request, "New version created.")
        return redirect("document_management:document_detail", pk=original.pk)


def can_download_document_file(user, document):
    """Full protection gate for viewing/downloading a document's files.

    Layer 1 (content ACL): standing access for superusers, Executives,
    MD/Mayor, owners, and uploaders; everyone else — including HODs, unit
    heads, and supervisors — passes only with custody, an approved request,
    an active movement, or a direct share. Registry NEVER passes.
    Layer 2 (scope): must also be owner/custodian, hold an approved
    request/share, sit in the file's jurisdiction, or carry the role scope
    (so View and Download stay in sync).
    """
    from ..permissions import can_view_document_content, has_content_scope

    file_obj = document.file
    if file_obj is None:
        return user.is_superuser or document.uploaded_by == user
    if not can_view_document_content(user, file=file_obj, document=document):
        return False

    allowed = False
    staff = getattr(user, "staff", None)

    # Role scope (owner / unit head / dept HOD-supervisor / uploader) —
    # no custody required, mirrors the content gate.
    if has_content_scope(user, file_obj, document=document):
        allowed = True

    # Oversight-head scoped download: same department as the file owner.
    # Pure heads-of-unit are treated like regular staff (no scope grant).
    dept_scoped = bool(
        staff
        and staff.is_privileged_head
        and file_obj.file_type == "personal"
        and file_obj.owner
        and staff.department_id
        and file_obj.owner.department_id == staff.department_id
    )

    if user.is_superuser or (
        staff
        and (
            staff.is_hod
            or staff.is_privileged_head
            or staff.is_executive
            or staff.is_md
            or getattr(staff, "is_mayor", False)
        )
        and (
            staff == file_obj.owner
            or staff == file_obj.current_location
            or getattr(staff, "is_mayor", False)
            or staff.is_executive
            or staff.is_md
            or (staff.is_hod and file_obj.owner and file_obj.owner.department == staff.department)
            or dept_scoped
        )
    ):
        allowed = True

    if (
        not allowed
        and document.uploaded_by == user
        and staff
        and (
            staff.is_hod
            or staff.is_privileged_head
            or staff.is_executive
            or staff.is_md
            or getattr(staff, "is_mayor", False)
        )
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

    return allowed


def _s3_presigned_url(field_file, inline, mime_type, filename, expiry=None):
    """Short-lived S3 URL for one file — issued only AFTER access is granted.

    The bucket itself stays fully private (no public access); this URL dies
    after PROTECTED_FILE_URL_EXPIRY seconds.
    """
    import boto3
    from botocore.config import Config
    from django.conf import settings as dj_settings

    storage = field_file.storage
    bucket = getattr(storage, "bucket_name", None) or dj_settings.AWS_STORAGE_BUCKET_NAME
    s3 = boto3.client(
        "s3",
        region_name=getattr(storage, "region_name", None) or dj_settings.AWS_S3_REGION_NAME,
        endpoint_url=getattr(storage, "endpoint_url", None) or dj_settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=getattr(storage, "access_key", None) or dj_settings.AWS_S3_ACCESS_KEY_ID,
        aws_secret_access_key=getattr(storage, "secret_key", None) or dj_settings.AWS_S3_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
    )
    params = {"Bucket": bucket, "Key": field_file.name}
    if mime_type:
        params["ResponseContentType"] = mime_type
    params["ResponseContentDisposition"] = "inline" if inline else f'attachment; filename="{filename}"'
    return s3.generate_presigned_url(
        "get_object", Params=params, ExpiresIn=expiry or dj_settings.PROTECTED_FILE_URL_EXPIRY
    )


def _serve_field_file(field_file, inline):
    """Serve a FileField with inline-view or download disposition.

    Local disk: direct FileResponse (SAMEORIGIN framing for inline views).
    S3 / remote storage: redirect to a short-lived presigned URL minted after
    the caller's permission check — the bucket itself is never public.
    """
    import logging
    import mimetypes

    from django.core.files.storage import FileSystemStorage
    from django.http import FileResponse

    logger = logging.getLogger("document_management")
    filename = field_file.name.split("/")[-1]
    mime_type, _ = mimetypes.guess_type(filename)

    if isinstance(field_file.storage, FileSystemStorage):
        from pathlib import Path

        file_path = field_file.path
        if not Path(file_path).exists():
            return None
        f = Path(file_path).open("rb")  # noqa: SIM115  # FileResponse manages closure
        response = FileResponse(f, content_type=mime_type or "application/octet-stream")
        response["Content-Disposition"] = "inline" if inline else f'attachment; filename="{filename}"'
        if inline:
            response["X-Frame-Options"] = "SAMEORIGIN"
        return response

    try:
        return redirect(_s3_presigned_url(field_file, inline, mime_type, filename))
    except Exception:
        logger.warning("Presigned URL failed; streaming file through Django.", exc_info=True)
        f = field_file.open("rb")
        response = FileResponse(f, content_type=mime_type or "application/octet-stream")
        response["Content-Disposition"] = "inline" if inline else f'attachment; filename="{filename}"'
        if inline:
            response["X-Frame-Options"] = "SAMEORIGIN"
        return response


class DocumentDownloadView(LoginRequiredMixin, View):
    """
    Serves a document attachment if the user passes the content + scope gate
    (standing access for owner/uploader/Executive/MD/Mayor; custody or
    explicit grant for everyone else). Registry staff can never download
    contents.
    """

    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        file_obj = document.file
        user = request.user

        if not can_download_document_file(user, document):
            messages.error(request, "You do not have permission to download this document.")
            return redirect(file_obj.get_absolute_url() if file_obj else "document_management:my_files")

        if not document.attachment:
            # Legacy slot empty but extras may exist — point at the first file.
            first_extra = document.extra_attachments.first()
            if first_extra:
                return redirect("document_management:attachment_download", att_pk=first_extra.pk)
            messages.error(request, "This document has no attachment.")
            return redirect(file_obj.get_absolute_url())

        inline = request.GET.get("inline") == "1"
        response = _serve_field_file(document.attachment, inline=inline)
        if response is None:
            messages.error(request, "Attachment file not found on server.")
            return redirect(file_obj.get_absolute_url())
        log_action(user, "DOCUMENT_DOWNLOADED", request=request, obj=document)
        return response


def _save_extra_uploads(document, uploads, skip=None, uploaded_by=None):
    """Persist every file from a multi-select upload beyond the primary one."""
    from ..models import DocumentAttachment

    saved = 0
    for f in uploads:
        if skip is not None and f is skip:
            continue
        DocumentAttachment.objects.create(document=document, file=f, uploaded_by=uploaded_by)
        saved += 1
    return saved


class AttachmentDownloadView(LoginRequiredMixin, View):
    """Serve one extra attachment of a document — same protection as downloads."""

    def get(self, request, att_pk):
        from ..models import DocumentAttachment

        attachment = get_object_or_404(DocumentAttachment, pk=att_pk)
        document = attachment.document
        file_obj = document.file

        if not can_download_document_file(request.user, document):
            messages.error(request, "You do not have permission to download this document.")
            return redirect(file_obj.get_absolute_url() if file_obj else "document_management:my_files")

        inline = request.GET.get("inline") == "1"
        response = _serve_field_file(attachment.file, inline=inline)
        if response is None:
            messages.error(request, "Attachment file not found on server.")
            return redirect(file_obj.get_absolute_url() if file_obj else "document_management:my_files")
        log_action(request.user, "DOCUMENT_DOWNLOADED", request=request, obj=document)
        return response


class AttachmentViewerView(HTMXLoginRequiredMixin, View):
    """In-browser viewer for one file on a document (PDF/image preview).

    ``att_key`` is ``main`` for the legacy slot or a DocumentAttachment pk.
    Same protection gate as downloads — anyone blocked there is blocked here.
    """

    def get(self, request, doc_pk, att_key):
        from ..models import DocumentAttachment

        document = get_object_or_404(Document, pk=doc_pk)
        file_obj = document.file

        if not can_download_document_file(request.user, document):
            messages.error(request, "You do not have permission to view this document.")
            if file_obj:
                return redirect(file_obj.get_absolute_url())
            return redirect("document_management:my_files")

        if att_key == "main":
            if not document.attachment:
                first_extra = document.extra_attachments.first()
                if first_extra:
                    return redirect(
                        "document_management:attachment_view", att_pk=first_extra.pk
                    )
                messages.error(request, "This document has no attachment.")
                return redirect(file_obj.get_absolute_url() if file_obj else "document_management:my_files")
            field_file = document.attachment
            download_url = reverse_lazy("document_management:document_download", kwargs={"pk": document.pk})
        else:
            try:
                att_pk = int(att_key)
            except (TypeError, ValueError):
                raise Http404
            attachment = get_object_or_404(DocumentAttachment, pk=att_pk, document=document)
            field_file = attachment.file
            download_url = reverse_lazy("document_management:attachment_download", kwargs={"att_pk": attachment.pk})

        import mimetypes

        filename = field_file.name.split("/")[-1]
        mime_type, _ = mimetypes.guess_type(filename)
        kind = "other"
        if (mime_type or "").startswith("image/"):
            kind = "image"
        elif (mime_type or "") == "application/pdf" or filename.lower().endswith(".pdf"):
            kind = "pdf"

        return render(
            request,
            "document_management/attachment_view.html",
            {
                "document": document,
                "file": file_obj,
                "filename": filename,
                "mime_type": mime_type,
                "kind": kind,
                "download_url": download_url,
                "inline_url": f"{download_url}?inline=1",
                "att_key": att_key,
            },
        )


class DocumentCreateView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentForm
    template_name = "document_management/document_create.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.file_obj = get_object_or_404(File, pk=self.kwargs.get("file_pk"))

        # One rule set, shared with the button visibility (can_add_minute):
        # document_management.permissions.can_add_document.
        if not can_add_document(request.user, self.file_obj, require_active=False):
            messages.error(
                request, "You do not have permission to add documents to this file. Restricted to File Owner/HOD."
            )
            return redirect(self.file_obj.get_absolute_url())

        if self.file_obj.status != "active":
            messages.error(request, "Documents can only be added to active files.")
            return redirect(self.file_obj.get_absolute_url())

        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        # HTMX dispatch-recipient search for the Add Document modal:
        # ?dispatch_search=1&q=... returns option rows calling
        # selectDocDispatchStaff(staff_pk, name, meta).
        if request.headers.get("HX-Request") and request.GET.get("dispatch_search"):
            self.file_obj = get_object_or_404(File, pk=self.kwargs.get("file_pk"))
            return self._dispatch_recipient_options(request)
        return super().get(request, *args, **kwargs)

    def _dispatch_recipient_options(self, request):
        from django.db.models import Q

        from document_management.permissions import get_dispatch_recipients

        query = request.GET.get("q", "").strip()
        selected = (request.GET.get("send_to") or request.GET.get("selected") or "").strip()
        eligible = get_dispatch_recipients(request.user, self.file_obj).select_related(
            "user", "designation", "department"
        )
        if query and len(query) >= 1:
            eligible = eligible.filter(
                Q(user__username__icontains=query)
                | Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(department__name__icontains=query)
                | Q(designation__name__icontains=query)
            ).distinct()[:10]
        else:
            eligible = eligible[:10]
        if not eligible:
            return HttpResponse(
                '<div class="p-4 text-center text-sm text-slate-400">No eligible recipients found.</div>'
            )
        html = '<div class="divide-y divide-slate-100">'
        for staff in eligible:
            name = staff.user.get_full_name() or staff.user.username
            safe = name.replace("'", "\\'")
            desig = staff.designation.name if staff.designation else ""
            dept = staff.department.name if staff.department else ""
            meta = " — ".join(p for p in [desig, dept] if p)
            safe_meta = meta.replace("'", "\\'")
            is_selected = bool(selected) and str(staff.pk) == str(selected)
            row_cls = (
                "flex items-center justify-between px-4 py-3 cursor-pointer "
                + ("bg-nigeria-green/10 border-l-4 border-nigeria-green" if is_selected else "hover:bg-slate-50")
            )
            btn = (
                '<span class="ml-3 inline-flex items-center gap-1 px-3 py-1.5 bg-green-50 border border-green-200 '
                'text-green-800 text-[10px] font-black uppercase rounded-lg">✓ Selected</span>'
                if is_selected
                else '<button type="button" class="ml-3 px-3 py-1.5 bg-nigeria-green text-white '
                'text-[10px] font-black uppercase rounded-lg" '
                f"onclick=\"selectDocDispatchStaff('{staff.pk}', '{safe}', '{safe_meta}')\">Select</button>"
            )
            html += (
                f'<div class="{row_cls}">'
                f'<div class="min-w-0"><p class="text-sm font-bold text-slate-900">{name}</p>'
                f'<p class="text-[10px] text-slate-500 font-medium">{meta}</p></div>'
                f"{btn}</div>"
            )
        html += "</div>"
        return HttpResponse(html)

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

        # Registry uploads are official records: auto-approved, no routing.
        # Everyone else's uploads stay pending and route for review until the
        # last approver signs off (which flips the document to approved and
        # the file back to active).
        staff = getattr(self.request.user, "staff", None)
        is_registry_upload = self.request.user.is_superuser or (staff and staff.is_registry)
        if is_registry_upload:
            form.instance.status = "approved"

        if getattr(self.file_obj, "active_dispatch_document", None):
            is_custodian = (
                hasattr(self.request.user, "staff") and self.file_obj.current_location == self.request.user.staff
            )
            if is_custodian and form.instance.parent == self.file_obj.active_dispatch_document:
                self.file_obj.clear_dispatch()

        response = super().form_valid(form)
        document = self.object

        # Multi-file upload: first file lives on the document, the rest land
        # on DocumentAttachment rows.
        _save_extra_uploads(
            document,
            form.files.getlist("attachment"),
            skip=form.cleaned_data.get("attachment"),
            uploaded_by=self.request.user,
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

        # Route the file. Registry uploads stay approved but may still be
        # dispatched: an optional send_to routes with a movement +
        # notification; without it the file keeps its status and the owner
        # is simply notified instead.
        send_to_staff = form.cleaned_data.get("send_to")
        staff_user = getattr(self.request.user, "staff", None)

        if send_to_staff and is_registry_upload:
            from document_management.permissions import get_dispatch_recipients

            if not get_dispatch_recipients(self.request.user, self.file_obj).filter(
                pk=send_to_staff.pk
            ).exists():
                messages.error(self.request, "Selected recipient is not eligible for dispatch.")
                return redirect(self.file_obj.get_absolute_url())

        from ..permissions import is_privileged_viewer

        if (
            not send_to_staff
            and staff_user
            and not is_registry_upload
            and not is_privileged_viewer(self.request.user)
        ):
            # Auto-route lower staff (including pure heads-of-unit) up the
            # reporting hierarchy — skipping self so a unit manager routes to THEIR head.
            for head in (
                staff_user.unit.head if staff_user.unit else None,
                staff_user.section.head if staff_user.section else None,
                staff_user.division.head if staff_user.division else None,
                staff_user.department.head if staff_user.department else None,
            ):
                if head and head.pk != staff_user.pk:
                    send_to_staff = head
                    break

        if send_to_staff:
            from_location = staff_user
            self.file_obj.current_location = send_to_staff
            self.file_obj.status = "in_transit"
            self.file_obj.save()

            FileMovement.objects.create(
                file=self.file_obj,
                sent_by=self.request.user,
                from_location=from_location,
                sent_to=send_to_staff,
                action="sent",
                document=document,
            )
            # Sender hands off custody — expire their approved grants like send_file does,
            # so they don't keep Full Access while the file is in transit with someone else.
            FileAccessRequest.objects.filter(
                file=self.file_obj, requested_by=self.request.user, status="approved"
            ).update(status="expired")
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
            if is_registry_upload:
                # Registry filing: notify the file owner (personal) or the
                # department head (policy) that an approved document landed.
                notify_user = None
                if self.file_obj.file_type == "personal" and self.file_obj.owner:
                    notify_user = self.file_obj.owner.user
                elif (
                    self.file_obj.file_type == "policy"
                    and self.file_obj.department
                    and self.file_obj.department.head
                ):
                    notify_user = self.file_obj.department.head.user
                if notify_user and notify_user != self.request.user:
                    create_notification(
                        user=notify_user,
                        message=(
                            f"Registry added '{document.title or 'Untitled'}' to file "
                            f"{self.file_obj.file_number} — {self.file_obj.title}."
                        ),
                        obj=self.file_obj,
                        link=self.file_obj.get_absolute_url(),
                    )
                messages.success(self.request, "Document added and approved. Owner notified.")
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


class StandaloneUrgentDocumentCreateView(LoginRequiredMixin, CreateView):
    """Create a standalone urgent/high priority document not tied to any file."""
    model = Document
    form_class = DocumentForm
    template_name = "document_management/standalone_urgent_create.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        # Only users with urgent permission can create standalone urgent docs
        if not request.user.has_perm("user_management.can_set_urgent_priority"):
            messages.error(request, "You do not have permission to create urgent documents.")
            return redirect("document_management:inbox")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_form(self, form_class=None):
        # Standalone documents are not tied to a file, so there is no
        # dispatch target — drop the routing field entirely.
        form = super().get_form(form_class)
        form.fields.pop("send_to", None)
        return form

    def get_initial(self):
        initial = super().get_initial()
        initial["priority"] = "urgent"  # Default to urgent
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if hasattr(self.request.user, "staff"):
            context["active_signature"] = self.request.user.staff.get_active_signature()
        return context

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        form.instance.file = None  # Standalone document
        priority = form.cleaned_data.get("priority", "urgent")
        form.instance.priority = priority
        form.instance.status = "pending"
        response = super().form_valid(form)
        document = self.object

        # Notify HODs/supervisors of this urgent document
        if priority in ("urgent", "high"):
            from organization.models import Staff
            from notifications.utils import create_notification

            from document_management.views.base import EXCLUDE_REGISTRY_Q

            recipients = (
                Staff.objects.exclude(EXCLUDE_REGISTRY_Q)
                .exclude(user=self.request.user)
                .filter(
                    Q(is_hod=True) | Q(is_effective_supervisor=True) | Q(is_executive=True) | Q(is_md=True)
                )
                .select_related("user")
            )
            for recipient in recipients:
                if recipient.user:
                    create_notification(
                        user=recipient.user,
                        message=(
                            f"URGENT Document Created: '{document.title or 'Untitled'}' "
                            f"by {self.request.user.get_full_name() or self.request.user.username}."
                        ),
                        obj=document,
                        link=reverse_lazy("document_management:inbox_document_standalone", kwargs={"pk": document.pk}),
                    )

        messages.success(self.request, f"Urgent document '{document.title or 'Untitled'}' created successfully.")
        log_action(
            self.request.user,
            "STANDALONE_URGENT_DOCUMENT_CREATED",
            request=self.request,
            obj=document,
            details={"priority": document.priority},
        )
        return response

    def get_success_url(self):
        return reverse_lazy("document_management:inbox") + "?mode=urgent"
