from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse


@shared_task
def send_file_retention_reminders():
    """
    Check all files where the current custodian has had the file >48 hours.
    Send email + in-app notification reminders.
    """
    from organization.models import Staff
    from notifications.utils import create_notification
    from .models import File, FileMovement

    # Find registry staff to exclude
    registry_ids = Staff.objects.filter(
        Q(designation__name__icontains='registry') |
        Q(user__groups__name__iexact='Registry')
    ).values_list('id', flat=True)

    # Files with a non-registry current custodian
    files = File.objects.filter(
        status__in=('active', 'in_transit'),
        current_location__isnull=False,
    ).exclude(current_location__id__in=registry_ids)

    reminded_count = 0
    for file_obj in files:
        if file_obj.is_overdue(threshold_days=2):
            custodian = file_obj.current_location
            if not custodian or not custodian.user:
                continue

            duration = file_obj.get_custody_duration()
            # Send in-app notification
            create_notification(
                user=custodian.user,
                message=f"REMINDER: File {file_obj.file_number} — {file_obj.title} has been with you for {duration} day(s). Please action and forward.",
                obj=file_obj,
                link=file_obj.get_absolute_url(),
            )

            # Send email notification
            subject = f"PIMS Reminder: File {file_obj.file_number} – Action Required"
            email_context = {
                'user': custodian.user,
                'file': file_obj,
                'duration_days': duration,
                'site_name': 'PIMS',
                'file_url': f"{settings.BASE_URL}{file_obj.get_absolute_url()}",
            }
            html_message = render_to_string('emails/file_retention_reminder.html', email_context)
            text_message = render_to_string('emails/file_retention_reminder.txt', email_context)

            try:
                send_mail(
                    subject=subject,
                    message=text_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[custodian.user.email],
                    html_message=html_message,
                    fail_silently=True,
                )
            except Exception:
                pass

            reminded_count += 1

    return f"Sent {reminded_count} retention reminders"


@shared_task
def send_urgent_document_reminders():
    """
    Send reminders for urgent/high priority documents that haven't been actioned
    within 24 hours. Checks documents that are still 'pending' or 'in_transit'
    and were uploaded more than 24 hours ago.
    """
    from notifications.utils import create_notification
    from .models import Document

    cutoff = timezone.now() - timezone.timedelta(hours=24)
    urgent_docs = Document.objects.filter(
        priority__in=('urgent', 'high'),
        status__in=('pending', 'in_transit'),
        uploaded_at__lte=cutoff,
    ).select_related('file', 'uploaded_by')

    reminded = 0
    for doc in urgent_docs:
        file_obj = doc.file
        # Notify the current custodian
        if file_obj.current_location and file_obj.current_location.user:
            create_notification(
                user=file_obj.current_location.user,
                message=f"URGENT REMINDER: Document '{doc.title or 'Untitled'}' (Priority: {dict(Document.PRIORITY_CHOICES).get(doc.priority, doc.priority)}) in file {file_obj.file_number} requires action.",
                obj=file_obj,
                link=file_obj.get_absolute_url(),
            )
            reminded += 1

    return f"Sent {reminded} urgent document reminders"
