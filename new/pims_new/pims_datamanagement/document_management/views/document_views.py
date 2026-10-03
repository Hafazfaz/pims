import contextlib
import logging

from audit_log.models import AuditLogEntry
from audit_log.utils import log_action
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, View
from notifications.models import Notification
from notifications.utils import create_notification
from organization.models import Staff

from ..forms import DocumentForm
from ..models import Document, File, FileAccessRequest, FileMovement
from .base import HTMXLoginRequiredMixin, inbox_action_response
from ..permissions import can_add_document, can_share_document


logger = logging.getLogger(__name__)


def _document_share_email_html(*, document, message, sender_name, sender_dept, shared_at):
    """Branded HTML body for document share emails (same look as file shares)."""
    import base64
    import os

    from django.utils.html import escape

    logo_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "static",
        "img",
        "logo_email.png",
    )
    logo_b64 = ""
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()

    parts = [
        '<div style="font-family:Segoe UI,Tahoma,Geneva,Verdana,sans-serif;max-width:600px;margin:0 auto;color:#333">',
        '<div style="background:#008751;padding:30px;text-align:center;border-radius:12px 12px 0 0">',
    ]
    if logo_b64:
        parts.append(
            f'<img src="data:image/png;base64,{logo_b64}" '
            'style="width:50px;height:58px;margin-bottom:10px" alt="PIMS Logo" />'
        )
    parts += [
        '<h1 style="color:#fff;margin:0;font-size:20px;letter-spacing:2px">PERSONNEL INFORMATION MANAGEMENT SYSTEM</h1>',
        '<p style="color:rgba(255,255,255,.8);margin:8px 0 0;font-size:12px">Document Share Notification</p></div>',
        '<div style="background:#fff;padding:30px;border:1px solid #e0e0e0">',
        '<p style="font-size:15px;margin:0 0 20px">Dear Colleague,</p>',
        f'<p style="font-size:15px;margin:0 0 20px"><strong>{escape(sender_name)}</strong> from '
        f'<strong>{escape(sender_dept)}</strong> has shared a document with you via PIMS.</p>',
    ]
    if message:
        parts.append(
            f'<p style="font-size:15px;margin:0 0 15px;padding:12px;background:#E6F3EE;'
            f'border-left:4px solid #008751;border-radius:4px">{escape(message)}</p>'
        )
    parts.append('<table style="width:100%;border-collapse:collapse;margin:20px 0">')
    rows = [
        ("Document", document.title or "Untitled"),
        ("File Number", document.file.file_number),
        ("File Title", document.file.title),
        ("File Type", document.file.get_file_type_display()),
        ("Status", document.get_status_display()),
        ("Shared By", sender_name),
        ("Department", sender_dept),
        ("Date", shared_at.strftime("%B %d, %Y @ %H:%M")),
    ]
    for label, value in rows:
        parts.append(
            '<tr>'
            f'<td style="padding:12px;background:#f8f9fa;font-weight:bold;width:40%;border-bottom:1px solid #e0e0e0">{label}</td>'
            f'<td style="padding:12px;border-bottom:1px solid #e0e0e0">{escape(str(value))}</td>'
            "</tr>"
        )
    parts.append("</table>")
    parts.append(
        '<p style="font-size:13px;color:#555;margin:20px 0 0">'
        "The document is attached as a PDF together with its original file.</p>"
    )
    parts.append(
        '<p style="font-size:12px;color:#888;margin:20px 0 0;border-top:1px solid #e0e0e0;padding-top:15px">'
        "This is an automated notification from PIMS. Please do not reply directly to this email.</p>"
    )
    parts.append("</div></div>")
    return "\n".join(parts)


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
        # Standalone urgent documents have no file — this view assumes one at
        # every turn. Send them to their own tracking page instead of 500ing.
        if request.user.is_authenticated and Document.objects.filter(
            pk=kwargs.get("pk"), file__isnull=True
        ).exists():
            return redirect("document_management:urgent_document_detail", pk=kwargs["pk"])
        if not self.has_permission():
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.object
        file_obj = document.file

        context["can_add_minute"] = can_add_document(self.request.user, file_obj)
        context["document_is_approved"] = document.status == "approved"

        # Sharing is document-only and email-only: requires the
        # can_share_documents permission (see DocumentShareEmailView).
        context["can_share_document"] = can_share_document(self.request.user)

        return context

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
        from ..models import EmailLog
        from django.conf import settings
        from django.core.mail import EmailMessage

        document = get_object_or_404(Document, pk=pk)

        # Sharing is document-only and email-only.
        if not can_share_document(request.user):
            messages.error(request, "You do not have permission to share documents.")
            return redirect(document.file.get_absolute_url())

        staff = getattr(request.user, "staff", None)
        if not staff:
            messages.error(request, "Staff profile not found.")
            return redirect(document.file.get_absolute_url())

        active_signature = staff.get_active_signature()
        if not active_signature or not active_signature.is_verified:
            messages.error(request, "You need an active digital signature to share documents.")
            return redirect(document.file.get_absolute_url())

        recipient_email = request.POST.get("recipient_email", "").strip()
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()
        include_signature = request.POST.get("include_signature") == "on"

        if not recipient_email:
            messages.error(request, "Recipient email is required.")
            return redirect(document.file.get_absolute_url())

        if not subject:
            subject = f"Shared Document: {document.title or 'Untitled'}"

        sender_name = request.user.get_full_name() or request.user.username
        sender_dept = staff.department.name if staff.department else "N/A"
        now = timezone.now()
        plain_body = (
            f"{message}\n\n---\n"
            f"Document: {document.title or 'Untitled'}\n"
            f"File: {document.file.file_number}\n"
            f"Shared by: {sender_name}\n"
            f"Department: {sender_dept}\n"
            f"Date: {now.strftime('%B %d, %Y @ %H:%M')}\n\n"
            "This document was shared via the Personnel Information Management System (PIMS)."
        )
        html_body = _document_share_email_html(
            document=document,
            message=message,
            sender_name=sender_name,
            sender_dept=sender_dept,
            shared_at=now,
        )

        status, error_message = "sent", ""
        try:
            email = EmailMessage(
                subject=subject,
                body=html_body,
                from_email=getattr(settings, "PIMS_SHARE_EMAIL", settings.DEFAULT_FROM_EMAIL),
                to=[recipient_email],
            )
            email.content_subtype = "html"

            # Branded PDF of the document (same generator the file flow used).
            try:
                from core.utils.pdf import generate_document_pdf

                pdf_bytes = generate_document_pdf(
                    document_title=document.title or f"Document #{document.pk}",
                    document_content=document.minute_content or "",
                    sender_name=sender_name,
                    sender_dept=sender_dept,
                    signature_image=active_signature.image if include_signature else None,
                )
                email.attach(
                    f"{document.title or f'document_{document.pk}'}.pdf",
                    pdf_bytes.read(),
                    "application/pdf",
                )
            except Exception:
                logger.warning("Share PDF failed for document %s", document.pk, exc_info=True)

            # Original uploaded file, when present.
            if document.attachment:
                try:
                    document.attachment.open()
                    email.attach(
                        document.attachment.name.split("/")[-1],
                        document.attachment.read(),
                    )
                except (FileNotFoundError, OSError):
                    pass

            # Digital signature image (opt-in via the modal checkbox).
            if include_signature:
                try:
                    signature_file = active_signature.image.open()
                    email.attach(
                        f"signature_{staff.user.username}.png",
                        signature_file.read(),
                        "image/png",
                    )
                except (FileNotFoundError, OSError):
                    pass

            email.send(fail_silently=False)
            logger.info("Document share email sent to %s | document=%s", recipient_email, document.pk)
            messages.success(request, f"Document shared successfully with {recipient_email}.")
            log_action(
                request.user,
                "DOCUMENT_SHARED_EMAIL",
                request=request,
                obj=document.file,
                details={
                    "document_id": document.pk,
                    "recipient": recipient_email,
                    "subject": subject,
                },
            )
        except Exception as e:
            status = "failed"
            error_message = str(e)
            logger.error(
                "Failed to send document share email to %s: %s", recipient_email, error_message
            )
            messages.error(request, f"Failed to send email: {error_message}")

        EmailLog.objects.create(
            sent_by=request.user,
            recipient_email=recipient_email,
            subject=subject,
            body=plain_body,
            status=status,
            error_message=error_message,
            file=document.file,
            has_signature=include_signature,
        )

        return redirect(document.file.get_absolute_url())


class DocumentEditView(LoginRequiredMixin, View):
    """Edit a document in place — title, content, attachments.

    Replaces the old "new version" flow: the row is updated rather than a
    child document being created under ``parent`` (versioning itself was
    removed from the schema in migration 0028).
    """

    def post(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        from ..models import DocumentAttachment
        from ..permissions import can_view_document_content, is_registry

        if (
            not can_view_document_content(request.user, file=document.file, document=document)
            and not is_registry(request.user)
            and document.uploaded_by != request.user
        ):
            messages.error(request, "You do not have permission to edit this document.")
            return redirect(self._detail_url(document))

        document.title = request.POST.get("title", "").strip() or document.title
        if "minute_content" in request.POST:
            document.minute_content = request.POST.get("minute_content", "").strip()

        uploads = request.FILES.getlist("attachment")
        replacing_files = bool(uploads)
        if replacing_files:
            document.attachment = uploads[0]
        document.save()

        if replacing_files:
            # New files replace the previous set (legacy slot + extras).
            document.extra_attachments.all().delete()
            _save_extra_uploads(document, uploads[1:], uploaded_by=request.user)

        log_action(
            request.user,
            "DOCUMENT_UPDATED",
            request=request,
            obj=document,
            details={
                "document_title": document.title,
                "files_replaced": replacing_files,
            },
        )
        messages.success(request, "Document updated.")
        return redirect(self._detail_url(document))

    @staticmethod
    def _detail_url(document):
        if document.file_id is None:
            return reverse("document_management:urgent_document_detail", kwargs={"pk": document.pk})
        return reverse("document_management:document_detail", kwargs={"pk": document.pk})


def can_download_document_file(user, document):
    """Full protection gate for viewing/downloading a document's files.

    Layer 1 (content ACL): standing access for superusers, Executives,
    MD/Mayor, owners, and uploaders; everyone else — including HODs, unit
    heads, and supervisors — passes only with custody, an approved request,
    an active movement, or a direct share. Registry NEVER passes.
    Layer 2 (scope): must also be owner/custodian, hold an approved
    request/share, sit in the file's jurisdiction, or carry the role scope
    (so View and Download stay in sync).
    Standalone documents (no file): any staff member except Registry, since
    those are broadcast to the whole urgent list — never a personnel file.
    """
    from ..permissions import can_view_document_content, has_content_scope

    file_obj = document.file
    if file_obj is None:
        # Standalone (urgent) documents carry no file ACL, so the audience is
        # the one the urgent list already shows them to: any staff member,
        # except Registry (separation of duties) — plus the filer/superuser.
        if user.is_superuser or document.uploaded_by == user:
            return True
        staff = getattr(user, "staff", None)
        return staff is not None and not staff.is_registry
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
    explicit grant for everyone else). Registry staff can never open
    document contents.

    Plain downloads are disabled system-wide: only ``?inline=1`` (the
    in-browser preview pipeline) is served.
    """

    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        file_obj = document.file
        user = request.user

        if not can_download_document_file(user, document):
            messages.error(request, "You do not have permission to view this document.")
            return redirect(file_obj.get_absolute_url() if file_obj else "document_management:my_files")

        if not document.attachment:
            # Legacy slot empty but extras may exist — point at the first file.
            first_extra = document.extra_attachments.first()
            if first_extra:
                return redirect(
                    "document_management:attachment_view",
                    doc_pk=document.pk,
                    att_key=first_extra.pk,
                )
            messages.error(request, "This document has no attachment.")
            return redirect(file_obj.get_absolute_url() if file_obj else "document_management:my_files")

        if request.GET.get("inline") != "1":
            messages.error(request, "Downloading is disabled — attachments are view-only in the browser.")
            return redirect("document_management:attachment_view", doc_pk=document.pk, att_key="main")

        # For Office documents, preview the generated PDF so the user can view
        # it in the browser without downloading the original file.
        if document.preview_pdf:
            response = _serve_field_file(document.preview_pdf, inline=True)
        else:
            response = _serve_field_file(document.attachment, inline=True)
        if response is None:
            messages.error(request, "Attachment file not found on server.")
            return redirect(file_obj.get_absolute_url() if file_obj else "document_management:my_files")
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
    """Serve one extra attachment of a document — same protection as downloads.

    Plain downloads are disabled system-wide: only ``?inline=1`` (the
    in-browser preview pipeline) is served.
    """

    def get(self, request, att_pk):
        from ..models import DocumentAttachment

        attachment = get_object_or_404(DocumentAttachment, pk=att_pk)
        document = attachment.document
        file_obj = document.file

        if not can_download_document_file(request.user, document):
            messages.error(request, "You do not have permission to view this document.")
            return redirect(file_obj.get_absolute_url() if file_obj else "document_management:my_files")

        if request.GET.get("inline") != "1":
            messages.error(request, "Downloading is disabled — attachments are view-only in the browser.")
            return redirect(
                "document_management:attachment_view",
                doc_pk=document.pk,
                att_key=attachment.pk,
            )

        response = _serve_field_file(attachment.file, inline=True)
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
        # Office documents are read through their generated PDF preview —
        # downloads are off, so the browser viewer is the only way in.
        elif att_key == "main" and document.preview_pdf:
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
            from document_management.views.base import EXCLUDE_REGISTRY_Q
            from notifications.utils import create_notification
            from organization.models import Staff

            recipients = [
                staff
                for staff in Staff.objects.exclude(EXCLUDE_REGISTRY_Q)
                .exclude(user=self.request.user)
                .select_related("user")
                if staff.is_hod or staff.is_effective_supervisor or staff.is_executive or staff.is_md
            ]
            for recipient in recipients:
                if recipient.user:
                    create_notification(
                        user=recipient.user,
                        message=(
                            f"URGENT Document Created: '{document.title or 'Untitled'}' "
                            f"by {self.request.user.get_full_name() or self.request.user.username}."
                        ),
                        obj=document,
                        link=reverse_lazy("document_management:inbox") + "?mode=urgent",
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


class StandaloneUrgentDocumentDetailView(HTMXLoginRequiredMixin, DetailView):
    """Tracking page for a standalone urgent/high-priority document.

    Standalone urgent documents carry no file, so they have no movement and
    none of the existing detail pages can open them — the urgent inbox could
    only show a dead dash. This view is their page: status, priority, the
    document content, and the activity trail.
    """

    model = Document
    template_name = "document_management/urgent_document_detail.html"
    context_object_name = "document"

    # Readable trail labels for audit actions that carry no display choice.
    ACTION_LABELS = {
        "DOCUMENT_APPROVED": "Approved by a head / supervisor",
        "DOCUMENT_REJECTED": "Sent back to the filer",
        "DOCUMENT_DOWNLOADED": "Attachment downloaded",
        "DOCUMENT_UPDATED": "Document updated",
    }

    def get_queryset(self):
        return Document.objects.filter(file__isnull=True).select_related("uploaded_by", "document_type")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        document = get_object_or_404(Document, pk=kwargs["pk"])
        # File-backed documents keep their regular detail page.
        if document.file_id is not None:
            return redirect("document_management:document_detail", pk=document.pk)
        # Same audience as the urgent inbox list: anyone with a staff profile,
        # plus the uploader and superusers.
        if not (request.user.is_superuser or document.uploaded_by_id == request.user.pk or hasattr(request.user, "staff")):
            messages.error(request, "You do not have access to this document.")
            return redirect(f"{reverse('document_management:inbox')}?mode=urgent")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.object
        user = self.request.user
        staff = getattr(user, "staff", None)

        audit_entries = list(
            AuditLogEntry.objects.filter(object_id=document.pk, content_type__model="document")
            .select_related("user")
            .order_by("timestamp")
        )
        alerts_qs = Notification.objects.filter(
            object_id=document.pk, content_type__model="document"
        )
        alert_total = alerts_qs.count()
        latest_alert = alerts_qs.order_by("-timestamp").first()

        timeline = [
            {
                "timestamp": document.uploaded_at,
                "label": "Urgent document filed",
                "user": document.uploaded_by,
                "detail": None,
            }
        ]
        for entry in audit_entries:
            # The creation is already the "filed" line above — one event, one row.
            if entry.action == "STANDALONE_URGENT_DOCUMENT_CREATED":
                continue
            timeline.append(
                {
                    "timestamp": entry.timestamp,
                    "label": self.ACTION_LABELS.get(entry.action, entry.get_action_display()),
                    "user": entry.user,
                    "detail": entry.details.get("reason") if isinstance(entry.details, dict) else None,
                }
            )
        # One line for the broadcast instead of a row per recipient.
        if latest_alert is not None:
            timeline.append(
                {
                    "timestamp": latest_alert.timestamp,
                    "label": (
                        f"Alerts sent to {alert_total} "
                        f"head{'s' if alert_total != 1 else ''} & supervisors"
                    ),
                    "user": None,
                    "detail": None,
                }
            )
        timeline.sort(key=lambda item: item["timestamp"], reverse=True)

        # Registry never reads contents (separation of duties); everyone else
        # on this page already sees the document in their urgent inbox.
        context["can_view_content"] = bool(
            user.is_superuser or (staff is not None and not staff.is_registry)
        )
        context["can_open_files"] = can_download_document_file(user, document)
        context["is_uploader"] = document.uploaded_by_id == user.pk
        context["is_pending"] = document.status in ("pending", "in_transit")
        # Same audience/roles as the movement-based action endpoint: heads,
        # supervisors, unit managers, executives — never the filer themselves,
        # and never Registry (separation of duties: they log and track, they
        # do not decide on contents).
        context["can_action"] = bool(
            staff
            and staff.is_effective_supervisor
            and not staff.is_registry
            and document.uploaded_by_id != user.pk
            and context["is_pending"]
        )
        context["timeline"] = timeline
        context["alert_count"] = alert_total
        context["waiting_since"] = document.uploaded_at
        return context


class StandaloneUrgentDocumentActionView(HTMXLoginRequiredMixin, View):
    """Approve or reject a standalone urgent document.

    Standalone urgent documents have no FileMovement, so the movement-based
    :class:`DocumentActionView` can never reach them — the urgent list had no
    working action for those rows.

    - Approve: the document is closed as approved and the filer is notified.
    - Reject: a reason is required and the document is returned to the filer
      (status ``rejected`` + the reason stored on it, alert sent back).

    Both outcomes drop the item out of everyone's untreated urgent list.
    """

    def post(self, request, pk):
        document = get_object_or_404(Document, pk=pk, file__isnull=True)
        staff = getattr(request.user, "staff", None)
        action = request.POST.get("action", "")
        note = request.POST.get("note", "").strip()

        back_url = self._safe_next(request, document)

        if not staff or not staff.is_effective_supervisor:
            messages.error(request, "Only HODs, supervisors, and unit managers can action urgent documents.")
            return inbox_action_response(request, back_url)
        if staff.is_registry:
            messages.error(request, "Registry records and tracks urgent documents — it does not decide on them.")
            return inbox_action_response(request, back_url)
        if document.uploaded_by_id == request.user.pk:
            messages.error(request, "You cannot approve or reject your own document.")
            return inbox_action_response(request, back_url)
        if document.status not in ("pending", "in_transit"):
            messages.error(request, "This document has already been actioned.")
            return inbox_action_response(request, back_url)

        actor = request.user.get_full_name() or request.user.username
        title = document.title or "Untitled"

        if action == "approve":
            document.status = "approved"
            document.save(update_fields=["status"])
            log_action(
                request.user,
                "DOCUMENT_APPROVED",
                request=request,
                obj=document,
                details={"document_title": title, "priority": document.priority, "note": note},
            )
            create_notification(
                user=document.uploaded_by,
                message=f"{actor} approved your urgent document '{title}'.",
                obj=document,
                link=reverse("document_management:urgent_document_detail", kwargs={"pk": document.pk}),
            )
            messages.success(request, f"Urgent document '{title}' approved.")
        elif action == "reject":
            if not note:
                messages.error(request, "A reason is required when sending a document back.")
                return inbox_action_response(request, back_url)
            document.status = "rejected"
            document.status_reason = note
            document.save(update_fields=["status", "status_reason"])
            log_action(
                request.user,
                "DOCUMENT_REJECTED",
                request=request,
                obj=document,
                details={"document_title": title, "priority": document.priority, "reason": note},
            )
            create_notification(
                user=document.uploaded_by,
                message=f"{actor} sent your urgent document '{title}' back to you. Reason: {note}",
                obj=document,
                link=reverse("document_management:urgent_document_detail", kwargs={"pk": document.pk}),
            )
            messages.success(request, f"Sent back to {document.uploaded_by.get_full_name() or document.uploaded_by.username}.")
        else:
            messages.error(request, "Unknown action.")
            return inbox_action_response(request, back_url)

        return inbox_action_response(request, back_url)

    @staticmethod
    def _safe_next(request, document):
        """Where to land after acting — the posted ?next= or the tracking page."""
        from django.utils.http import url_has_allowed_host_and_scheme

        next_url = request.POST.get("next", "") or request.GET.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return next_url
        return reverse("document_management:urgent_document_detail", kwargs={"pk": document.pk})
