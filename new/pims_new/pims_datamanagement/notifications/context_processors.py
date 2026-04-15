from .models import Notification

def unread_notifications(request):
    if request.user.is_authenticated:
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return {'unread_notifications_count': count}
    return {'unread_notifications_count': 0}

def pending_activation_count(request):
    if request.user.is_authenticated and hasattr(request.user, 'staff') and request.user.staff.is_registry:
        from document_management.models import File, FileAccessRequest
        return {
            'pending_activation_count': File.objects.filter(status='pending_activation').count(),
            'pending_access_count': FileAccessRequest.objects.filter(status='pending').count(),
        }
    return {'pending_activation_count': 0, 'pending_access_count': 0}
