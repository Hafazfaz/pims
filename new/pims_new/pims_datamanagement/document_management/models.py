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
            from django.utils import timezone
            # Improved file number generation
            prefix = "FMCAB"
            
            # Use current time if created_at isn't set yet (auto_now_add is set after first save)
            current_date = self.created_at if self.created_at else timezone.now()
            year = current_date.year

            if self.file_type == "personal":
                type_code = "PS"
            elif self.file_type == "policy" and self.department:
                type_code = self.department.code
            else:
                type_code = "GEN"

            # Get the next serial number for this type/year combination
            # We filter for similar patterns to ensure we don't duplicate
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


class Document(models.Model):
    """
    Represents a document or a minute attached to a File.
    """

    file = models.ForeignKey(File, related_name="documents", on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

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
