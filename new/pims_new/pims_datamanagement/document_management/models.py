import logging
import tempfile
from pathlib import Path

from core.constants import FILE_STATUS_CHOICES, FILE_TYPE_CHOICES, STATUS_CHOICES
from core.utils.pdf import watermark_pdf_file
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from organization.models import Department, Division, Section, Staff, Unit


logger = logging.getLogger(__name__)


def _apply_pdf_watermark(field_file):
    """Stamp the PIMS watermark onto a PDF FieldFile in place (no save)."""
    import io

    if not field_file or not field_file.name.lower().endswith(".pdf"):
        return
    if not settings.ENABLE_DOCUMENT_WATERMARKING:
        return
    original_pdf_content = field_file.read()
    watermarked_pdf_content = watermark_pdf_file(
        io.BytesIO(original_pdf_content), watermark_text=settings.DOCUMENT_WATERMARK_TEXT
    )
    filename = Path(field_file.name).name
    field_file.save(filename, ContentFile(watermarked_pdf_content.getvalue()), save=False)


class File(models.Model):
    """
    Represents a File, which is a container for documents, minutes, and actions.
    This corresponds to a physical file in the registry.
    """

    title = models.CharField(max_length=255, help_text="The title of the file, always in uppercase.")
    file_number = models.CharField(max_length=50, unique=True, blank=True, help_text="Auto-generated file number.")
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, default="personal")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional: associate file with a division.",
    )
    section = models.ForeignKey(
        Section, on_delete=models.SET_NULL, null=True, blank=True, help_text="Optional: associate file with a section."
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional: narrow policy file to a specific unit within the department.",
    )
    external_party = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Name of external organization (for Corporate/External Policy files)",
    )
    status = models.CharField(max_length=20, choices=FILE_STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_files",
        help_text="Assigned Staff (Required for Personal Files)",
    )
    current_location = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="files_at_location",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_files",
    )

    class Meta:
        constraints = [
            # Personal files are strictly 1:1 with their Staff owner —
            # backs up the same check in clean() at the database level.
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(file_type="personal"),
                name="unique_personal_file_per_owner",
            ),
        ]
        permissions = [
            ("create_file", "Can create a new file"),
            ("activate_file", "Can activate an inactive file"),
            ("close_file", "Can close an active file"),
            ("send_file", "Can send a file to another user"),
            ("archive_file", "Can archive a file"),  # New permission
        ]

    @property
    def owner_display(self):
        if self.file_type == "personal" and self.owner:
            return self.owner.user.get_full_name() or self.owner.user.username
        elif self.file_type == "policy":
            if self.external_party:
                return self.external_party
            if self.department:
                return self.department.name
        return "N/A"

    @property
    def current_location_display(self):
        # Custody must never render as empty — legacy rows with NULL
        # (from the old recall bug) are treated as with Registry.
        if not self.current_location:
            return "Registry"
        if self.current_location.is_registry:
            return "Registry"
        return self.current_location.user.get_full_name() or self.current_location.user.username

    def __str__(self):
        return f"{self.title} ({self.file_number})"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("document_management:file_detail", kwargs={"pk": self.pk})

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.file_type == "personal" and not self.owner:
            raise ValidationError("Personal files must have an assigned owner (Staff).")

        if self.file_type == "policy" and not self.department and not self.external_party:
            raise ValidationError("Policy files must be assigned to either a Department or an External Party.")

        # Registry staff cannot own files
        if self.owner and self.owner.is_registry:
            raise ValidationError("Registry staff cannot be assigned as file owners.")

        # Enforce 1:1 Personal File per Staff
        if self.file_type == "personal" and self.owner:
            existing = File.objects.filter(file_type="personal", owner=self.owner).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError(
                    f"A personal folder already exists for {self.owner}. "
                    "Each staff member can only have one personal folder."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        # Enforce uppercase title
        self.title = self.title.upper()

        if not self.file_number:
            from django.utils import timezone

            # Improved file number generation
            prefix = "FMCAB"

            # Use current time if created_at isn't set yet
            current_date = self.created_at if self.created_at else timezone.now()
            year = current_date.year

            if self.file_type == "personal":
                type_code = "PS"
            elif self.file_type == "policy":
                type_code = self.department.code if self.department else "EXT"
            else:
                type_code = "GEN"

            # Serial number logic
            pattern = f"{prefix}/{year}/{type_code}/"
            last_file = File.objects.filter(file_number__startswith=pattern).order_by("-file_number").first()

            if last_file:
                try:
                    last_serial = int(last_file.file_number.split("/")[-1])
                    new_serial = last_serial + 1
                except (ValueError, IndexError):
                    new_serial = File.objects.filter(file_type=self.file_type).count() + 1
            else:
                new_serial = 1

            self.file_number = f"{prefix}/{year}/{type_code}/{new_serial:04d}"

        super().save(*args, **kwargs)

    def get_custody_duration(self):
        """Days the file has been at its current location, based on FileMovement."""
        from django.utils import timezone

        if not self.current_location:
            return 0
        last_movement = self.movements.filter(action="sent").order_by("-moved_at").first()
        ref = last_movement.moved_at if last_movement else self.created_at
        return (timezone.now() - ref).days

    def is_overdue(self, threshold_days=2):
        """
        Check if the file has been in current location longer than threshold.
        Default threshold is 2 days.
        """
        return self.get_custody_duration() > threshold_days

    @property
    def last_movement_date(self):
        last = self.movements.filter(action="sent").order_by("-moved_at").first()
        return last.moved_at if last else self.created_at

    def can_user_view_contents(self, user):
        """
        Check if a user can view document contents of this file.
        Follows standard role-based rules.
        """
        if user.is_superuser:
            return True
        staff = getattr(user, "staff", None)
        if not staff:
            return False
        if staff.is_registry:
            return False
        if getattr(staff, "is_mayor", False):
            return True
        return True


class DocumentType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class Document(models.Model):
    """
    Represents a document or a minute attached to a File.
    Can also exist as a standalone document (not tied to any file).
    """

    file = models.ForeignKey(File, related_name="documents", on_delete=models.CASCADE, null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    document_type = models.ForeignKey(
        DocumentType, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents"
    )

    # New: Add title for labeling official documents (e.g. "Birth Certificate")
    title = models.CharField(max_length=255, blank=True, null=True)

    # Hierarchical threading
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")

    # A document can be either a text minute or an uploaded file
    minute_content = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to="", blank=True, null=True)
    preview_pdf = models.FileField(
        upload_to="document_previews/",
        blank=True,
        null=True,
        help_text="Auto-generated PDF preview for Office documents (DOCX, etc.).",
    )
    has_signature = models.BooleanField(default=False)
    signature_record = models.ForeignKey(
        "organization.StaffSignature",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signed_documents",
    )

    # Document Status
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("in_transit", "In Transit"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    status_reason = models.TextField(blank=True, null=True, help_text="Reason for approval or rejection")

    # Priority / Urgency
    PRIORITY_CHOICES = [
        ("normal", "Normal"),
        ("high", "High Priority"),
        ("urgent", "Urgent"),
    ]
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="normal", help_text="Urgency level of this document."
    )

    # Granular Access Control
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="shared_documents",
        blank=True,
        help_text="Users who have been granted specific access to view this document.",
    )

    @property
    def is_shared(self):
        return self.shared_with.exists()

    def __str__(self):
        """A label a human can read in a notification or audit entry.

        Titles are optional — auto-routed minutes often carry none — so fall
        back to the file the document lives in rather than letting Django
        render ``Document object (185)`` into people's messages.
        """
        if self.title:
            return self.title
        if self.file_id and self.file:
            return f"Untitled document in {self.file.file_number}"
        return "Untitled document"

    def can_view(self, user):
        """
        Check if the user can view this specific document.
        Returns True if user is the uploader, or falls into shared_with.
        Does NOT check File-level permissions (that should be checked separately).
        """
        if user == self.uploaded_by:
            return True
        return bool(self.shared_with.filter(pk=user.pk).exists())

    class Meta:
        ordering = ["-uploaded_at"]
        permissions = [
            ("add_minute", "Can add a minute to a file"),
            ("add_attachment", "Can add an attachment to a file"),
            (
                "view_staff_documents",
                "Can view staff personnel documents (titles and metadata). "
                "Granted to every group except Registry.",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.attachment:
            _apply_pdf_watermark(self.attachment)
        super().save(*args, **kwargs)
        # Generate a PDF preview for Office documents once the row has a PK.
        if self.attachment and not self.preview_pdf:
            self._maybe_generate_preview_pdf()

    def _maybe_generate_preview_pdf(self):
        from document_management.utils import CONVERTIBLE_TO_PREVIEW

        ext = Path(self.attachment.name).suffix.lower()
        if ext not in CONVERTIBLE_TO_PREVIEW:
            return
        try:
            self.generate_preview_pdf()
        except Exception:
            logger.exception("Failed to generate preview PDF for document %s", self.pk)

    def generate_preview_pdf(self):
        """Convert the Office attachment to a PDF preview and store it.

        Returns the generated preview FileField, or None if the attachment is
        not a supported Office document or conversion fails.
        """
        from django.core.files import File as DjangoFile

        from document_management.utils import CONVERTIBLE_TO_PREVIEW, convert_office_to_pdf

        if not self.attachment:
            return None
        ext = Path(self.attachment.name).suffix.lower()
        if ext not in CONVERTIBLE_TO_PREVIEW:
            return None
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / Path(self.attachment.name).name
            with self.attachment.open("rb") as src:
                source_path.write_bytes(src.read())
            pdf_path = convert_office_to_pdf(source_path, tmpdir)
            if not pdf_path:
                return None
            with pdf_path.open("rb") as f:
                filename = f"{self.pk or 'doc'}_preview.pdf"
                self.preview_pdf.save(filename, DjangoFile(f), save=False)
        # Persist only the preview_pdf field; avoid recursion.
        self.save(update_fields=["preview_pdf"])
        return self.preview_pdf
        if self.minute_content:
            return f"Minute on {self.file.title} at {self.uploaded_at.strftime('%Y-%m-%d')}"
        elif self.attachment:
            return f"Attachment for {self.file.title} at {self.uploaded_at.strftime('%Y-%m-%d')}"
        return f"Empty document entry for {self.file.title}"

    @property
    def has_files(self):
        """True if the document carries any file (legacy or extra attachments)."""
        return bool(self.attachment) or self.extra_attachments.exists()

    @property
    def attachment_count(self):
        """Total number of files on this document (legacy + extras)."""
        return (1 if self.attachment else 0) + self.extra_attachments.count()

    @property
    def attachment_filename(self):
        """Basename of the legacy attachment file."""
        return Path(self.attachment.name).name if self.attachment else ""


class DocumentAttachment(models.Model):
    """An additional file on a Document — one document can carry many files.

    The first upload still lives on ``Document.attachment`` (back-compat);
    every further file from a multi-select upload lands here.
    """

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="extra_attachments")
    file = models.FileField(upload_to="document_attachments/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="uploaded_attachments"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"Attachment {Path(self.file.name).name} on {self.document}"

    @property
    def filename(self):
        return Path(self.file.name).name

    def save(self, *args, **kwargs):
        if self.file:
            _apply_pdf_watermark(self.file)
        super().save(*args, **kwargs)


class DocumentSignature(models.Model):
    """Records a digital signature applied to a document."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="signatures")
    signatory = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="document_signatures"
    )
    signature_record = models.ForeignKey(
        "organization.StaffSignature", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    note = models.TextField(blank=True, help_text="Context or reason for signing")

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("document", "signatory")]

    def __str__(self):
        return f"Signature by {self.signatory.get_full_name()} on {self.document}"


class FileMovement(models.Model):
    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name="movements")
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="sent_movements"
    )
    sent_to = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name="received_movements"
    )
    from_location = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name="outgoing_movements"
    )
    document = models.ForeignKey(
        "Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
        help_text="The specific document being sent in this movement.",
    )
    note = models.TextField(blank=True, default="")
    attachment = models.FileField(upload_to="movement_attachments/", blank=True, null=True)
    moved_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=20, default="sent")  # 'sent', 'recalled', 'closed'
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("forwarded", "Forwarded"),
        ],
        default="pending",
    )

    # End-of-movement registry fields (required on close)
    closed_at = models.DateTimeField(null=True, blank=True)
    version_reference = models.ForeignKey(
        "Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movement_version_refs",
        help_text="Previous version of a document referenced at end of movement.",
    )
    file_reference = models.ForeignKey(
        File,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movement_file_refs",
        help_text="Another file referenced at end of movement.",
    )

    # Access expiry: a dispatched movement grants the recipient access until this
    # datetime. When None, access is indefinite. Drives is_active_access.
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this movement's granted access expires. Null = indefinite.",
    )

    # 48-hour transit alert bookkeeping: when the sender was first warned that
    # this dispatch has been sitting in transit, and when the last reminder went
    # out. Null first = no alert sent yet; follow-ups go out daily after that.
    transit_alert_first_sent_at = models.DateTimeField(null=True, blank=True)
    transit_alert_last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-moved_at"]

    def __str__(self):
        return f"{self.file.file_number} — {self.action} at {self.moved_at:%Y-%m-%d %H:%M}"

    @property
    def is_active_access(self):
        """A movement grants the recipient view access when active and unexpired."""
        from django.utils import timezone

        if self.action not in ("sent", "approved", "forwarded"):
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return True

    @property
    def is_stuck_in_transit(self):
        """True when this dispatch has been awaiting receipt for over 48 hours."""
        from django.utils import timezone

        if self.action != "sent" or self.status != "pending" or self.closed_at:
            return False
        if not self.file_id or self.file.status != "in_transit":
            return False
        return timezone.now() - self.moved_at > timezone.timedelta(hours=48)




class FileAccessRequest(models.Model):
    """
    Model for requesting temporary access to a file's original documents.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    ]

    ACCESS_TYPE_CHOICES = [
        ("read_only", "Read Only"),
        ("read_write", "Read & Write"),
    ]

    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name="access_requests")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reason = models.TextField()
    access_type = models.CharField(max_length=20, choices=ACCESS_TYPE_CHOICES, default="read_only")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Request for {self.file.file_number} by {self.requested_by.username}"

    @property
    def is_active(self):
        from django.utils import timezone

        return self.status == "approved" and (self.expires_at is None or self.expires_at > timezone.now())




class EmailLog(models.Model):
    STATUS_CHOICES = [
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_email_logs",
    )
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="sent")
    error_message = models.TextField(blank=True, default="")
    file = models.ForeignKey(
        File,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )
    has_signature = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        verbose_name = "Email Log"
        verbose_name_plural = "Email Logs"

    def __str__(self):
        return f"{self.subject} -> {self.recipient_email} ({self.status})"
