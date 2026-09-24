"""Repair files stuck in 'in_transit' after completed approval chains.

Before this fix, ApprovalChain.advance()/reject_to_previous() moved custody
without updating File.status, so files returned to Registry (or to the sender)
kept status='in_transit' forever. Flip those rows back to 'active':

- status is 'in_transit', AND
- current holder is Registry staff, AND
- the file has no active approval chain.
"""

from django.db import migrations
from django.db.models import Q


def fix_stuck_files(apps, schema_editor):
    File = apps.get_model("document_management", "File")
    Staff = apps.get_model("organization", "Staff")

    registry_ids = set(
        Staff.objects.filter(
            Q(designation__name__icontains="registry") | Q(user__groups__name__iexact="Registry")
        ).values_list("pk", flat=True)
    )
    if not registry_ids:
        return

    stuck = (
        File.objects.filter(status="in_transit", current_location_id__in=registry_ids)
        .exclude(documents__approval_chains__status="active")
        .distinct()
    )
    stuck.update(status="active")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_management", "0045_grant_view_staff_documents"),
    ]

    operations = [
        migrations.RunPython(fix_stuck_files, noop),
    ]
