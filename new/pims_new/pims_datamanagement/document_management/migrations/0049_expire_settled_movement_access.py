# Backfill for the inbox/sent access-closure fix: movements that were already
# approved/forwarded/rejected keep granting access via is_active_access until
# they carry an expiry, and their dispatch-time auto-grants stay valid.
# Expire both so settled items stop opening contents from inbox/sent lists.
# Files with a pending movement in flight are left alone; real,
# human-approved access requests are never touched.

from django.db import migrations
from django.utils import timezone


def expire_settled_access(apps, schema_editor):
    FileMovement = apps.get_model("document_management", "FileMovement")
    FileAccessRequest = apps.get_model("document_management", "FileAccessRequest")
    now = timezone.now()
    FileMovement.objects.filter(
        status__in=["approved", "forwarded", "rejected"], expires_at__isnull=True
    ).update(expires_at=now)
    pending_files = FileMovement.objects.filter(status="pending").values("file_id")
    FileAccessRequest.objects.filter(status="approved", reason__startswith="Auto-granted").exclude(
        file_id__in=pending_files
    ).update(status="expired")


class Migration(migrations.Migration):

    dependencies = [
        ("document_management", "0048_remove_approvalstep_chain_and_more"),
    ]

    operations = [
        migrations.RunPython(expire_settled_access, reverse_code=migrations.RunPython.noop),
    ]
