from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditLogEntry(models.Model):
    ACTION_CHOICES = [
        ("LOGIN", "User Logged In"),
        ("LOGOUT", "User Logged Out"),
        ("LOGIN_FAILED", "User Login Failed"),
        ("PASSWORD_CHANGED", "User Password Changed"),
        ("ACCOUNT_LOCKED", "User Account Locked"),
        ("ACCOUNT_UNLOCKED", "User Account Unlocked"),
        ("FILE_CREATED", "File Created"),
        ("FILE_UPDATED", "File Updated"),
        ("FILE_ACTIVATED", "File Activated"),
        ("FILE_CLOSED", "File Closed"),
        ("FILE_ARCHIVED", "File Archived"),
        ("FILE_SENT", "File Sent"),
        ("DOCUMENT_ADDED", "Document Added"),
        ("DOCUMENT_UPDATED", "Document Updated"),
        ("DOCUMENT_APPROVED", "Document Approved"),
        ("DOCUMENT_REJECTED", "Document Rejected"),
        ("DOCUMENT_FORWARDED", "Document Forwarded"),
        ("DOCUMENT_DELETED", "Document Deleted"),
        ("CHAIN_CREATED", "Approval Chain Created"),
        ("CHAIN_STARTED", "Approval Chain Started"),
        ("CHAIN_STEP_APPROVED", "Chain Step Approved"),
        ("CHAIN_STEP_REJECTED", "Chain Step Rejected"),
        ("CHAIN_DELETED", "Approval Chain Deleted"),
        ("CHAIN_TEMPLATE_SAVED", "Chain Template Saved"),
        ("CHAIN_TEMPLATE_DELETED", "Chain Template Deleted"),
        ("CHAIN_APPLIED", "Chain Template Applied"),
        ("ACCESS_REQUEST_SUBMITTED", "Access Request Submitted"),
        ("ACCESS_REQUEST_APPROVED", "Access Request Approved"),
        ("ACCESS_REQUEST_REJECTED", "Access Request Rejected"),
        ("FILE_ACTIVATION_REQUESTED", "File Activation Requested"),
        ("MOVEMENT_CLOSED", "Movement Closed"),
        ("USER_CREATED", "User Created"),
        ("USER_UPDATED", "User Updated"),
        ("USER_DELETED", "User Deleted"),
        # Add more actions as needed
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs"
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)

    # Generic foreign key to the object that was affected
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    details = models.JSONField(blank=True, null=True)  # For storing extra information like old/new values

    class Meta:
        ordering = ["-timestamp"]
        verbose_name_plural = "Audit Log Entries"

    def __str__(self):
        return f"{self.action} by {self.user or 'Anonymous'} at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
