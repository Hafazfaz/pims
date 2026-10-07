"""Expire approved FileAccessRequests whose holder no longer has custody.

Approved grants are custody-tied: a grant is valid exactly as long as its
holder is the file's current custodian (approving a request transfers
custody to the requester). Legacy rows approved before that rule existed
are reconciled here so no stale grant outlives a custody change.
"""
from django.db import migrations


def expire_grants_without_custody(apps, schema_editor):
    FileAccessRequest = apps.get_model("document_management", "FileAccessRequest")

    grants = (
        FileAccessRequest.objects.filter(status="approved")
        .select_related("file")
        .select_related("requested_by__staff")
    )
    for grant in grants:
        try:
            holder_staff_id = grant.requested_by.staff_id
        except Exception:  # requester has no staff profile
            holder_staff_id = None
        custodian_id = grant.file.current_location_id
        if custodian_id is None or custodian_id != holder_staff_id:
            grant.status = "expired"
            grant.save(update_fields=["status"])


class Migration(migrations.Migration):
    dependencies = [
        ("document_management", "0054_filemovement_transit_alert_first_sent_at_and_more"),
    ]

    operations = [
        migrations.RunPython(expire_grants_without_custody, migrations.RunPython.noop),
    ]
