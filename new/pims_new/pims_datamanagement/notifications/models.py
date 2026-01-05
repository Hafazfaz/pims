from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    
    # Generic foreign key to the object that the notification is about
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Optional link for the notification, e.g., to a file's detail page
    link = models.URLField(max_length=500, blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = "Notifications"

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message[:50]}..."

    def mark_as_read(self):
        self.is_read = True
        self.save()

    def get_link(self):
        # Fallback to generic object link if a specific link is not provided
        if self.link:
            return self.link
        if self.content_object:
            # Attempt to get an absolute URL if the object has one
            if hasattr(self.content_object, 'get_absolute_url'):
                return self.content_object.get_absolute_url()
        return None
