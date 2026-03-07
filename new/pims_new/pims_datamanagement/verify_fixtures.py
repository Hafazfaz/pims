import os
import django

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pims_datamanagement.settings")
django.setup()

from document_management.models import Document, File, FileAccessRequest  # noqa: E402
from organization.models import Department, Designation, Staff, Unit  # noqa: E402
from user_management.models import CustomUser  # noqa: E402
from audit_log.models import AuditLogEntry  # noqa: E402
from notifications.models import Notification  # noqa: E402

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
        print("\n[SUCCESS] All verification assertions passed!")
    except AssertionError as e:
        print(f"\n[FAILURE] Verification failed: {e}")

if __name__ == "__main__":
    verify_fixtures()
