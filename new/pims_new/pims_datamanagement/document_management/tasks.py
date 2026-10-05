import contextlib

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone


@shared_task
def send_file_retention_reminders():
    """
    Check all files where the current custodian has had the file >48 hours.
    Send email + in-app notification reminders.
    """
    from notifications.utils import create_notification
    from organization.models import Staff

    from .models import File

    # Find registry staff to exclude
    registry_ids = Staff.objects.filter(
        Q(designation__name__icontains="registry") | Q(user__groups__name__iexact="Registry")
    ).values_list("id", flat=True)

    # Files with a non-registry current custodian
    files = File.objects.filter(
        status__in=("active", "in_transit"),
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
                message=(
                    f"REMINDER: File {file_obj.file_number} — "
                    f"{file_obj.title} has been with you for {duration} day(s). "
                    f"Please action and forward."
                ),
                obj=file_obj,
                link=file_obj.get_absolute_url(),
            )

            # Send email notification
            subject = f"PIMS Reminder: File {file_obj.file_number} - Action Required"
            email_context = {
                "user": custodian.user,
                "file": file_obj,
                "duration_days": duration,
                "site_name": "PIMS",
                "file_url": f"{settings.BASE_URL}{file_obj.get_absolute_url()}",
            }
            html_message = render_to_string("emails/file_retention_reminder.html", email_context)
            text_message = render_to_string("emails/file_retention_reminder.txt", email_context)

            with contextlib.suppress(Exception):
                send_mail(
                    subject=subject,
                    message=text_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[custodian.user.email],
                    html_message=html_message,
                    fail_silently=True,
                )

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
        priority__in=("urgent", "high"),
        status__in=("pending", "in_transit"),
        uploaded_at__lte=cutoff,
    ).select_related("file", "uploaded_by")

    reminded = 0
    for doc in urgent_docs:
        file_obj = doc.file
        # Notify the current custodian
        if file_obj.current_location and file_obj.current_location.user:
            create_notification(
                user=file_obj.current_location.user,
                message=(
                    f"URGENT REMINDER: Document '{doc.title or 'Untitled'}' "
                    f"(Priority: {dict(Document.PRIORITY_CHOICES).get(doc.priority, doc.priority)}) "
                    f"in file {file_obj.file_number} requires action."
                ),
                obj=file_obj,
                link=file_obj.get_absolute_url(),
            )
            reminded += 1

    return f"Sent {reminded} urgent document reminders"


TRANSIT_ALERT_HOURS = 48
TRANSIT_FOLLOWUP_HOURS = 24


@shared_task
def check_transit_alerts():
    """
    Alert senders when a dispatched file has been sitting in transit for more
    than 48 hours and has not been acknowledged/actioned yet.

    The first alert fires once when a movement crosses 48h in transit; after
    that a follow-up is sent every 24 hours until the file leaves transit
    (receipt acknowledged, approved, rejected, recalled or movement closed).
    """
    from notifications.utils import create_notification

    from .models import FileMovement

    now = timezone.now()
    cutoff = now - timezone.timedelta(hours=TRANSIT_ALERT_HOURS)

    movements = (
        FileMovement.objects.filter(
            action="sent",
            status="pending",
            closed_at__isnull=True,
            file__status="in_transit",
            moved_at__lte=cutoff,
            sent_by__isnull=False,
            sent_by__is_active=True,
        )
        .select_related("file", "sent_by", "sent_to__user")
        .order_by("moved_at")
    )

    alerted = 0
    for movement in movements:
        first_sent = movement.transit_alert_first_sent_at
        last_sent = movement.transit_alert_last_sent_at

        if first_sent is None:
            due = True  # first crossing of the 48h threshold
        elif last_sent is None:
            due = True
        else:
            due = last_sent <= now - timezone.timedelta(hours=TRANSIT_FOLLOWUP_HOURS)

        if not due:
            continue

        # Claim the alert slot BEFORE sending so a concurrent beat run cannot
        # deliver the same alert twice.
        claim = FileMovement.objects.filter(pk=movement.pk)
        if first_sent is None:
            claim = claim.filter(transit_alert_first_sent_at__isnull=True)
            values = {
                "transit_alert_first_sent_at": now,
                "transit_alert_last_sent_at": now,
            }
        else:
            claim = claim.filter(
                Q(transit_alert_last_sent_at__isnull=True)
                | Q(
                    transit_alert_last_sent_at__lte=(
                        now - timezone.timedelta(hours=TRANSIT_FOLLOWUP_HOURS)
                    )
                )
            )
            values = {"transit_alert_last_sent_at": now}

        if not claim.update(**values):
            continue

        file_obj = movement.file
        hours_in_transit = max(1, int((now - movement.moved_at).total_seconds() // 3600))
        recipient = ""
        if movement.sent_to and movement.sent_to.user:
            recipient = (
                movement.sent_to.user.get_full_name()
                or movement.sent_to.user.username
            )

        message = (
            f"TRANSIT ALERT: File {file_obj.file_number} — {file_obj.title} has been "
            f"in transit for {hours_in_transit} hour(s)"
            + (f" awaiting {recipient}" if recipient else "")
            + ". Please follow up to confirm receipt."
        )

        create_notification(
            user=movement.sent_by,
            message=message,
            obj=file_obj,
            link=file_obj.get_absolute_url(),
            send_email=True,
            email_template="emails/transit_alert.html",
            email_subject=(
                f"PIMS: File {file_obj.file_number} still in transit "
                f"({hours_in_transit}h)"
            ),
            email_context={
                "file": file_obj,
                "recipient": recipient,
                "hours_in_transit": hours_in_transit,
                "file_url": f"{settings.BASE_URL}{file_obj.get_absolute_url()}",
            },
        )

        alerted += 1

    return f"Sent {alerted} transit alerts"

