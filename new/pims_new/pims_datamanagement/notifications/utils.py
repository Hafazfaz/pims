from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail
from django.template.loader import render_to_string
from user_management.models import CustomUser

from .models import Notification


def create_notification(user, message, obj=None, link=None, recipient_list=None, send_email=False,
                        email_template=None, email_context=None, email_subject=None):
    """
    Helper function to create a Notification.

    user: The user who the notification is for.
    message: The notification message.
    obj: The object related to the notification (optional).
    link: An explicit URL for the notification (optional).
    recipient_list: A list of additional CustomUser objects to send the notification to.
                    If None, only 'user' receives it.
    send_email: If True, also sends an email notification.
    email_template: Optional custom email template path (e.g., "emails/file_creation_approved.html").
    email_context: Optional additional context for the email template.
    email_subject: Optional custom email subject line.
    """
    content_type = None
    object_id = None
    if obj:
        content_type = ContentType.objects.get_for_model(obj)
        object_id = obj.pk

    # Create notification for the primary user
    Notification.objects.create(user=user, message=message, content_type=content_type, object_id=object_id, link=link)

    # Send email if requested
    if send_email and user.email:
        _send_notification_email(
            user, message, link,
            template=email_template,
            extra_context=email_context,
            subject=email_subject
        )

    # Handle additional recipients for escalation (e.g., admins)
    if recipient_list:
        for recipient in recipient_list:
            if recipient != user:  # Avoid duplicate notifications if primary user is also in recipient_list
                Notification.objects.create(
                    user=recipient, message=message, content_type=content_type, object_id=object_id, link=link
                )
                if send_email and recipient.email:
                    _send_notification_email(
                        recipient, message, link,
                        template=email_template,
                        extra_context=email_context,
                        subject=email_subject
                    )


def _send_notification_email(user, message, link=None, template=None, extra_context=None, subject=None):
    """Send an email notification to a user."""
    try:
        email_subject = subject or "PIMS Notification"
        context = {
            "user": user,
            "message": message,
            "site_name": "PIMS",
            "site_url": getattr(settings, "BASE_URL", ""),
            "link": f"{settings.BASE_URL}{link}" if link else None,
        }
        if extra_context:
            context.update(extra_context)

        # Use custom template if provided, otherwise fall back to generic
        if template:
            html_message = render_to_string(template, context)
            text_template = template.replace(".html", ".txt")
            try:
                text_message = render_to_string(text_template, context)
            except Exception:
                text_message = message
        else:
            html_message = render_to_string("emails/notification.html", context)
            text_message = render_to_string("emails/notification.txt", context)

        send_mail(
            subject=email_subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )
    except Exception:
        pass


def notify_admins_of_critical_event(message, obj=None, link=None):
    """
    Sends a notification to all active superusers.
    """
    admin_users = CustomUser.objects.filter(is_active=True, is_superuser=True)
    if admin_users.exists():
        for admin_user in admin_users:
            create_notification(user=admin_user, message=message, obj=obj, link=link)
