from django.core.files.base import ContentFile
from django.conf import settings
from django.db import models
from organization.models import Department, Staff
from core.constants import FILE_TYPE_CHOICES, STATUS_CHOICES
from core.utils.pdf import watermark_pdf_file



class File(models.Model):
    """
    Represents a File, which is a container for documents, minutes, and actions.
    This corresponds to a physical file in the registry.
    """

    title = models.CharField(
        max_length=255, help_text="The title of the file, always in uppercase."
    )
    file_number = models.CharField(
        max_length=50, unique=True, blank=True, help_text="Auto-generated file number."
    )
    file_type = models.CharField(
        max_length=10, choices=FILE_TYPE_CHOICES, default="personal"
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True
    )
    external_party = models.CharField(
        max_length=255, 
        null=True, 
        blank=True, 
        help_text="Name of external organization (for Corporate/External Policy files)"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="inactive")
    created_at = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_files",
        help_text="Assigned Staff (Required for Personal Files)"
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

    # Document-Centric Dispatch
    active_dispatch_document = models.ForeignKey(
        'Document',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_dispatches",
        help_text="The specific document that triggered the current dispatch."
    )

    def clear_dispatch(self):
        self.active_dispatch_document = None
        self.save()


    class Meta:
        permissions = [
            ("create_file", "Can create a new file"),
            ("activate_file", "Can activate an inactive file"),
            ("close_file", "Can close an active file"),
            ("send_file", "Can send a file to another user"),
            ("archive_file", "Can archive a file"), # New permission
        ]

    @property
    def owner_display(self):
        if self.file_type == 'personal' and self.owner:
            return self.owner.user.get_full_name() or self.owner.user.username
        elif self.file_type == 'policy':
            if self.external_party:
                return self.external_party
            if self.department:
                return self.department.name
        return "N/A"

    def __str__(self):
        return f"{self.title} ({self.file_number})"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("document_management:file_detail", kwargs={"pk": self.pk})

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.file_type == 'personal' and not self.owner:
            raise ValidationError("Personal files must have an assigned owner (Staff).")
        
        if self.file_type == 'policy' and not self.department and not self.external_party:
            raise ValidationError("Policy files must be assigned to either a Department or an External Party.")

        # Enforce 1:1 Personal File per Staff
        if self.file_type == 'personal' and self.owner:
            existing = File.objects.filter(file_type='personal', owner=self.owner).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError(f"A personal folder already exists for {self.owner}. Each staff member can only have one personal folder.")

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
                if self.department:
                    type_code = self.department.code
                else:
                    # For external parties, use a generic EXT code or first 3 chars
                    type_code = "EXT"
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
        """
        Calculate how many days the file has been at its current location.
        Uses audit log entries to find the last FILE_SENT action.
        """
        from django.utils import timezone
        from audit_log.models import AuditLogEntry
        from django.contrib.contenttypes.models import ContentType
        
        if not self.current_location:
            return 0
        
        # Get the most recent FILE_SENT audit log entry for this file
        file_ct = ContentType.objects.get_for_model(File)
        last_movement = AuditLogEntry.objects.filter(
            content_type=file_ct,
            object_id=self.pk,
            action='FILE_SENT'
        ).order_by('-timestamp').first()
        
        if last_movement:
            # Calculate days since last movement
            duration = timezone.now() - last_movement.timestamp
            return duration.days
        else:
            # If no FILE_SENT log exists, use file creation date
            duration = timezone.now() - self.created_at
            return duration.days
    
    def is_overdue(self, threshold_days=2):
        """
        Check if the file has been in current location longer than threshold.
        Default threshold is 2 days.
        """
        return self.get_custody_duration() > threshold_days
    
    @property
    def last_movement_date(self):
        """
        Get the timestamp of the last time this file was sent to someone.
        Returns the creation date if file has never been moved.
        """
        from audit_log.models import AuditLogEntry
        from django.contrib.contenttypes.models import ContentType
        
        file_ct = ContentType.objects.get_for_model(File)
        last_movement = AuditLogEntry.objects.filter(
            content_type=file_ct,
            object_id=self.pk,
            action='FILE_SENT'
        ).order_by('-timestamp').first()
        
        return last_movement.timestamp if last_movement else self.created_at


class Document(models.Model):
    """
    Represents a document or a minute attached to a File.
    """

    file = models.ForeignKey(File, related_name="documents", on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # New: Add title for labeling official documents (e.g. "Birth Certificate")
    title = models.CharField(max_length=255, blank=True, null=True)

    # Hierarchical threading
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='replies'
    )

    # A document can be either a text minute or an uploaded file
    minute_content = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to="", blank=True, null=True)
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
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('cancelled', 'Cancelled'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='approved')
    
    # Granular Access Control
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='shared_documents', 
        blank=True,
        help_text="Users who have been granted specific access to view this document."
    )

    @property
    def is_shared(self):
        return self.shared_with.exists()

    def can_view(self, user):
        """
        Check if the user can view this specific document.
        Returns True if user is the uploader, or falls into shared_with.
        Does NOT check File-level permissions (that should be checked separately).
        """
        if user == self.uploaded_by:
            return True
        if self.shared_with.filter(pk=user.pk).exists():
            return True
        return False


    class Meta:
        ordering = ["-uploaded_at"]
        permissions = [
            ("add_minute", "Can add a minute to a file"),
            ("add_attachment", "Can add an attachment to a file"),
        ]

    def save(self, *args, **kwargs):
        if self.attachment and settings.ENABLE_DOCUMENT_WATERMARKING:
            # Check if it's a PDF
            if self.attachment.name.lower().endswith('.pdf'):
                import io
                import os
                # Read the original PDF content
                original_pdf_content = self.attachment.read()
                original_pdf_file = io.BytesIO(original_pdf_content)

                # Watermark the PDF
                watermarked_pdf_content = watermark_pdf_file(
                    original_pdf_file,
                    watermark_text=settings.DOCUMENT_WATERMARK_TEXT
                )
                
                # Create a new ContentFile from the watermarked content
                # And replace the attachment with the watermarked version
                filename = os.path.basename(self.attachment.name)
                self.attachment.save(filename, ContentFile(watermarked_pdf_content.getvalue()), save=False)

        super().save(*args, **kwargs)


    def __str__(self):
        if self.minute_content:
            return f"Minute on {self.file.title} at {self.uploaded_at.strftime('%Y-%m-%d')}"
        elif self.attachment:
            return f"Attachment for {self.file.title} at {self.uploaded_at.strftime('%Y-%m-%d')}"
        return f"Empty document entry for {self.file.title}"


class FileAccessRequest(models.Model):
    """
    Model for requesting temporary access to a file's original documents.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]
    
    ACCESS_TYPE_CHOICES = [
        ('read_only', 'Read Only'),
        ('read_write', 'Read & Write'),
    ]

    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='access_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reason = models.TextField()
    access_type = models.CharField(max_length=20, choices=ACCESS_TYPE_CHOICES, default='read_only')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Request for {self.file.file_number} by {self.requested_by.username}"

    @property
    def is_active(self):
        from django.utils import timezone
        return self.status == 'approved' and (self.expires_at is None or self.expires_at > timezone.now())
