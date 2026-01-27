import os
import io # Added for BytesIO
from django.core.files.base import ContentFile # Added for saving watermarked content
from django.conf import settings
from django.db import models
from organization.models import Department, Staff
from .utils import watermark_pdf_file # Import the utility


class File(models.Model):
    """
    Represents a File, which is a container for documents, minutes, and actions.
    This corresponds to a physical file in the registry.
    """

    FILE_TYPE_CHOICES = [
        ("personal", "Personal"),
        ("policy", "Policy"),
    ]
    STATUS_CHOICES = [
        ("inactive", "Inactive"),
        ("pending_activation", "Pending Activation"),
        ("active", "Active"),
        ("in_transit", "In Transit"), # Added new status
        ("closed", "Closed"),
        ("archived", "Archived"), # Added archived status
    ]

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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="inactive")
    created_at = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        related_name="owned_files",
    )
    current_location = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="files_at_location",
    )

    class Meta:
        permissions = [
            ("create_file", "Can create a new file"),
            ("activate_file", "Can activate an inactive file"),
            ("close_file", "Can close an active file"),
            ("send_file", "Can send a file to another user"),
            ("archive_file", "Can archive a file"), # New permission
        ]

    def __str__(self):
        return f"{self.title} ({self.file_number})"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("document_management:file_detail", kwargs={"pk": self.pk})

    def save(self, *args, **kwargs):
        # Enforce uppercase title
        self.title = self.title.upper()

        if not self.file_number:
            # Simplified file number generation for MVP
            prefix = "FMCAB"
            year = self.created_at.year if self.created_at else "XXXX"

            if self.file_type == "personal":
                type_code = "PS"  # Assuming 'Permanent Staff' for now
            elif self.file_type == "policy" and self.department:
                type_code = self.department.code
            else:
                type_code = "GEN"

            count = File.objects.filter(file_type=self.file_type).count()
            serial = f"{count + 1:04d}"

            self.file_number = f"{prefix}/{year}/{type_code}/{serial}"

        super().save(*args, **kwargs)


class Document(models.Model):
    """
    Represents a document or a minute attached to a File.
    """

    file = models.ForeignKey(File, related_name="documents", on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # A document can be either a text minute or an uploaded file
    minute_content = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to="", blank=True, null=True)

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
