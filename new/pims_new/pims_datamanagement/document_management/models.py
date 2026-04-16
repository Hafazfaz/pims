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

    @property
    def current_location_display(self):
        if not self.current_location:
            return None
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
        if self.file_type == 'personal' and not self.owner:
            raise ValidationError("Personal files must have an assigned owner (Staff).")

        if self.file_type == 'policy' and not self.department and not self.external_party:
            raise ValidationError("Policy files must be assigned to either a Department or an External Party.")

        # Registry staff cannot own files
        if self.owner and self.owner.is_registry:
            raise ValidationError("Registry staff cannot be assigned as file owners.")

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
        """Days the file has been at its current location, based on FileMovement."""
        from django.utils import timezone
        if not self.current_location:
            return 0
        last_movement = self.movements.filter(action='sent').order_by('-moved_at').first()
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
        last = self.movements.filter(action='sent').order_by('-moved_at').first()
        return last.moved_at if last else self.created_at

    @property
    def is_in_active_chain(self):
        """True if any document in this file has an active approval chain."""
        return self.documents.filter(approval_chain__status='active').exists()


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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    status_reason = models.TextField(blank=True, null=True, help_text="Reason for approval or rejection")
    
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


class FileMovement(models.Model):
    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='movements')
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='sent_movements'
    )
    sent_to = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_movements'
    )
    from_location = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='outgoing_movements'
    )
    note = models.TextField(blank=True, default='')
    attachment = models.FileField(upload_to='movement_attachments/', blank=True, null=True)
    moved_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=20, default='sent')  # 'sent' or 'recalled'

    class Meta:
        ordering = ['-moved_at']

    def __str__(self):
        return f"{self.file.file_number} — {self.action} at {self.moved_at:%Y-%m-%d %H:%M}"


class ApprovalChain(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('rejected', 'Rejected'),
    ]
    # Chain is now attached to a Document, not a File
    document = models.OneToOneField('Document', on_delete=models.CASCADE, related_name='approval_chain', null=True, blank=True)
    # Keep file FK for backwards compat but nullable
    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='approval_chains', null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_chains')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    current_step = models.PositiveIntegerField(default=1)

    def __str__(self):
        if self.document:
            return f"Chain for doc '{self.document}' [{self.status}]"
        return f"Chain for {self.file.file_number} [{self.status}]"

    @property
    def is_active(self):
        return self.status == 'active'

    def get_current_step(self):
        return self.steps.filter(order=self.current_step).first()

    def _get_file(self):
        return self.document.file if self.document else self.file

    def _get_registry(self):
        from organization.models import Staff as StaffModel
        from django.db.models import Q
        return StaffModel.objects.filter(
            Q(designation__name__icontains='registry') | Q(user__groups__name__iexact='Registry')
        ).first()

    def advance(self):
        """Move to next step or close chain and return file to registry."""
        next_step = self.steps.filter(order__gt=self.current_step, status='pending').order_by('order').first()
        file_obj = self._get_file()
        if next_step:
            self.current_step = next_step.order
            self.save()
            file_obj.current_location = next_step.approver
            file_obj.save()
        else:
            self.status = 'closed'
            self.save()
            # Return file to registry
            registry = self._get_registry()
            file_obj.current_location = registry
            file_obj.save()
            # Notify sender
            from notifications.utils import create_notification
            create_notification(
                user=self.created_by,
                message=f"Approval chain for '{self.document or file_obj.file_number}' completed. File returned to registry.",
                obj=file_obj,
                link=file_obj.get_absolute_url(),
            )

    def reject_to_previous(self, from_order):
        """Send back to previous approver, or back to sender if step 1."""
        file_obj = self._get_file()
        prev_step = self.steps.filter(order__lt=from_order).order_by('-order').first()
        if prev_step:
            prev_step.status = 'pending'
            prev_step.save()
            self.current_step = prev_step.order
            self.save()
            file_obj.current_location = prev_step.approver
            file_obj.save()
        else:
            self.status = 'rejected'
            self.save()
            # Return to sender
            from notifications.utils import create_notification
            create_notification(
                user=self.created_by,
                message=f"Approval chain for '{self.document or file_obj.file_number}' was rejected at step {from_order}. File returned to you.",
                obj=file_obj,
                link=file_obj.get_absolute_url(),
            )
            try:
                sender_staff = self.created_by.staff
                file_obj.current_location = sender_staff
            except Exception:
                pass
            file_obj.save()


class ApprovalStep(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    chain = models.ForeignKey(ApprovalChain, on_delete=models.CASCADE, related_name='steps')
    approver = models.ForeignKey('organization.Staff', on_delete=models.CASCADE, related_name='approval_steps')
    order = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    note = models.TextField(blank=True)
    signature = models.ForeignKey('organization.StaffSignature', on_delete=models.SET_NULL, null=True, blank=True)
    actioned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['order']
        unique_together = [('chain', 'order')]

    def __str__(self):
        return f"Step {self.order} — {self.approver} [{self.status}]"


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


class ChainTemplate(models.Model):
    """Reusable approval chain template created by admin/registry."""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chain_templates',
        help_text="Leave blank for org-wide templates."
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        scope = self.department.name if self.department else "Org-Wide"
        return f"{self.name} [{scope}]"


class ChainTemplateStep(models.Model):
    """A single step in a chain template, defined by role not person."""

    ROLE_TYPE_CHOICES = [
        ('specific_person', 'Specific Person'),
        ('unit_manager', 'Unit Manager'),
        ('hod', 'Head of Department'),
        ('designation', 'By Designation'),
        ('director_general', 'Director General'),
    ]

    DEPARTMENT_SCOPE_CHOICES = [
        ('sender', "Sender's Department"),
        ('specific', 'Specific Department'),
    ]

    template = models.ForeignKey(ChainTemplate, on_delete=models.CASCADE, related_name='steps')
    order = models.PositiveIntegerField()
    role_type = models.CharField(max_length=30, choices=ROLE_TYPE_CHOICES)
    # For role_type = 'hod' or 'unit_manager' — which dept?
    department_scope = models.CharField(
        max_length=20, choices=DEPARTMENT_SCOPE_CHOICES, default='sender', blank=True
    )
    specific_department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='template_steps'
    )
    # For role_type = 'designation'
    designation = models.ForeignKey(
        'organization.Designation', on_delete=models.SET_NULL, null=True, blank=True
    )
    # For role_type = 'specific_person'
    staff = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_template_steps'
    )

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Step {self.order}: {self.get_role_type_display()}"

    def resolve(self, sender_staff):
        """Resolve this step to an actual Staff instance at dispatch time."""
        if self.role_type == 'specific_person':
            return self.staff

        dept = (
            sender_staff.department
            if self.department_scope == 'sender'
            else self.specific_department
        )

        if self.role_type == 'unit_manager':
            unit = sender_staff.unit if self.department_scope == 'sender' else None
            if unit and unit.head:
                return unit.head
            # fallback: any unit head in dept
            from organization.models import Unit
            u = Unit.objects.filter(department=dept, head__isnull=False).first()
            return u.head if u else None

        if self.role_type == 'hod':
            return dept.head if dept else None

        if self.role_type == 'director_general':
            return Staff.objects.filter(
                user__groups__name__iexact='Executive'
            ).first()

        if self.role_type == 'designation':
            return Staff.objects.filter(
                designation=self.designation, department=dept
            ).first()

        return None
