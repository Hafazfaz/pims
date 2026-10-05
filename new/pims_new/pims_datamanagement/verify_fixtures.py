import os

import django

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pims_datamanagement.settings")
django.setup()

from audit_log.models import AuditLogEntry  # noqa: E402
from django.contrib.auth.models import Group, Permission  # noqa: E402
from django.db.models import Q  # noqa: E402
from document_management.models import Document, File, FileAccessRequest  # noqa: E402
from notifications.models import Notification  # noqa: E402
from organization.models import Department, Designation, Staff, Unit  # noqa: E402
from user_management.models import CustomUser  # noqa: E402


def verify_fixtures():
    print("--- Verifying Fixtures ---")

    counts = {
        "Users": CustomUser.objects.count(),
        "Departments": Department.objects.count(),
        "Units": Unit.objects.count(),
        "Designations": Designation.objects.count(),
        "Staff": Staff.objects.count(),
        "Files": File.objects.count(),
        "Documents": Document.objects.count(),
        "AccessRequests": FileAccessRequest.objects.count(),
        "AuditLogs": AuditLogEntry.objects.count(),
        "Notifications": Notification.objects.count(),
    }

    print("\n--- Object Counts ---")
    for model, count in counts.items():
        print(f"{model}: {count}")

    # Assertions
    try:
        assert counts["Departments"] >= 5, "Too few departments"
        assert counts["Users"] >= 20, "Too few users"
        assert counts["Files"] >= 50, "Too few files"
        assert counts["Documents"] >= 50, "Too few documents"
        assert counts["AuditLogs"] >= 50, "Too few audit logs"

        # Nursing Services structure seeded by the fixtures.
        nursing = Department.objects.filter(code="NUR").first()
        assert nursing is not None, "Nursing Services department (NUR) missing"
        assert nursing.name == "Nursing Services", "Unexpected NUR department name"
        assert nursing.head_id, "Nursing Services department has no head"
        assert Designation.objects.filter(name="Head of Nursing Services").exists(), (
            "Head of Nursing Services designation missing"
        )
        head_designation = Designation.objects.get(name="Head of Nursing Services")
        assert nursing.head.designation_id == head_designation.id, (
            "Nursing Services head does not hold the Head of Nursing Services designation"
        )

        # can_approve_document is person-based: Medical Directors only,
        # never a group grant.
        approve_perm = Permission.objects.filter(
            codename="can_approve_document", content_type__app_label="user_management"
        ).first()
        assert approve_perm is not None, "can_approve_document permission missing"
        assert not Group.objects.filter(permissions=approve_perm).exists(), (
            "A group still carries can_approve_document"
        )
        approvers = CustomUser.objects.filter(
            Q(user_permissions=approve_perm) | Q(groups__permissions=approve_perm)
        ).distinct()
        for holder in approvers:
            if holder.is_superuser:
                continue
            holder_staff = getattr(holder, "staff", None)
            assert holder_staff is not None and holder_staff.designation_id, (
                f"{holder.username} holds can_approve_document without a Staff designation"
            )
            assert holder_staff.designation.name == "Medical Director", (
                f"{holder.username} holds can_approve_document without the Medical Director designation"
            )
        assert approvers.filter(username="medical_director").exists(), (
            "The Medical Director fixture account cannot approve documents"
        )

        print("\n[SUCCESS] All verification assertions passed!")
    except AssertionError as e:
        print(f"\n[FAILURE] Verification failed: {e}")


if __name__ == "__main__":
    verify_fixtures()
