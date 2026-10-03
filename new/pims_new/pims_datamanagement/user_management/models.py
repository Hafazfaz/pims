from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    must_change_password = models.BooleanField(default=False)
    failed_login_attempts = models.IntegerField(default=0)
    lockout_until = models.DateTimeField(null=True, blank=True)
    last_password_change = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_session_key = models.CharField(max_length=40, null=True, blank=True)  # Max length for session keys

    class Meta(AbstractUser.Meta):
        permissions = [
            ("can_set_urgent_priority", "Can mark documents as Urgent or High Priority"),
            ("can_share_documents", "Can share documents with other users"),
            (
                "can_view_all_staff_files",
                "Can view all staff files and personnel records regardless of department or custody",
            ),
            # File access requests
            ("can_request_file_access", "Can request Read-Only access to files"),
            ("can_request_file_access_rw", "Can request Read & Write access to files"),
            ("can_approve_file_access", "Can approve or reject file access requests"),
            # File/document capabilities
            ("can_manage_registry", "Can perform Registry operations (create files, manage lifecycle, approve access)"),
            ("can_create_file", "Can create new files"),
            ("can_manage_file_lifecycle", "Can activate, close and archive files"),
            ("can_view_file", "Can view file details (subject to custody/scope)"),
            ("can_view_file_content", "Can view document contents (subject to custody/scope)"),
            ("can_add_document", "Can add a document/minute to a file"),
            ("can_dispatch_document", "Can dispatch or forward a document to another staff member"),
            ("can_delete_document", "Can delete a document"),
            ("can_approve_document", "Can approve or reject documents"),
            # Oversight / leadership
            ("can_supervise", "Can supervise staff (HOD, head of unit/section/division, or flagged supervisor)"),
            ("can_executive", "Has executive/MD level access across departments"),
            # Head-of-scope roles — granted per user by organization signals
            # whenever they are appointed head of a department / unit (or an
            # HOD-level designation is assigned).
            ("can_head_department", "Heads a department (HOD scope)"),
            ("can_head_unit", "Heads a unit (head-of-unit scope)"),
        ]


class UserSession(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="active_sessions")
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class PasswordHistory(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    password = models.CharField(max_length=128)  # Stores the hashed password
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name_plural = "Password Histories"

    def __str__(self):
        return f"Password history for {self.user.username} at {self.timestamp}"
