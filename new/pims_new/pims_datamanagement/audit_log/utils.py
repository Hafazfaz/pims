from .models import AuditLogEntry
from django.contrib.contenttypes.models import ContentType

def log_action(user, action, request=None, obj=None, details=None):
    """
    Helper function to create an AuditLogEntry.
    """
    ip_address = None
    user_agent = None

    if request:
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT')

    content_type = None
    object_id = None
    if obj:
        content_type = ContentType.objects.get_for_model(obj)
        object_id = obj.pk

    AuditLogEntry.objects.create(
        user=user if user and user.is_authenticated else None, # Store None for anonymous users
        action=action,
        ip_address=ip_address,
        user_agent=user_agent,
        content_type=content_type,
        object_id=object_id,
        details=details
    )
