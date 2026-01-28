from django.contrib.auth.signals import user_logged_out
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from audit_log.utils import log_action
from user_management.models import CustomUser

@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user: # Ensure user is not anonymous
        log_action(user, 'LOGOUT', request=request)


@receiver(post_save, sender=CustomUser)
def log_user_save(sender, instance, created, **kwargs):
    action = 'USER_CREATED' if created else 'USER_UPDATED'
    # Request is not directly available in signals, so we pass None
    # If request context is crucial, a middleware to attach it to a thread-local variable would be needed.
    log_action(instance, action, obj=instance, details={'username': instance.username})

@receiver(post_delete, sender=CustomUser)
def log_user_delete(sender, instance, **kwargs):
    # Avoid passing instance as the user or obj since it's already deleted in the DB
    # when this signal runs, which would cause an IntegrityError in SQLite.
    log_action(None, 'USER_DELETED', obj=None, details={'username': instance.username})
