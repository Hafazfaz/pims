from .models import AuditLogEntry


def log_action(user, action, request=None, obj=None, details=None):
    """
    Helper function to create an AuditLogEntry.
    Automatically captures file and document details if obj is provided.
    """
    ip_address = None
    user_agent = None

    if request:
        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT")

    content_type = None
    object_id = None

    # Initialize details if None
    if details is None:
        details = {}

    if obj:
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(obj)
        object_id = obj.pk

        # Auto-extract common metadata for easier reporting
        model_name = content_type.model

        if model_name == "file":
            details.setdefault("file", getattr(obj, "file_number", ""))
            details.setdefault("file_title", getattr(obj, "title", ""))
        elif model_name == "document":
            if hasattr(obj, "file"):
                details.setdefault("file", getattr(obj.file, "file_number", ""))
                details.setdefault("file_title", getattr(obj.file, "title", ""))
            details.setdefault("document_title", getattr(obj, "title", ""))

    AuditLogEntry.objects.create(
        user=user if user and user.is_authenticated else None,
        action=action,
        ip_address=ip_address,
        user_agent=user_agent,
        content_type=content_type,
        object_id=object_id,
        details=details,
    )
