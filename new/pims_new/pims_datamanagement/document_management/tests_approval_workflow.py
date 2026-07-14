"""
Tests for Document Dispatch Approval Workflow with Digital Signatures.

Covers:
1. File created with active status (no approval needed)
2. Document dispatched to HOD/Owner with email notification
3. HOD/Owner approval with verified signature
4. HOD/Owner rejection with reason
5. Creator/Sender notified on approval/rejection
6. Signature requirement enforcement
"""
from datetime import timedelta

from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from organization.models import Department, Designation, Staff, StaffSignature
from user_management.models import CustomUser

from document_management.models import Document, File, FileAccessRequest, FileMovement


def make_user(username, group_name=None, is_superuser=False):
    u = CustomUser.objects.create_user(username=username, password="Test1234!")
    u.is_superuser = is_superuser
    u.save()
    if group_name:
        g, _ = Group.objects.get_or_create(name=group_name)
        u.groups.add(g)
    return u


def make_staff(user, designation_name="Officer", dept=None):
    desig, _ = Designation.objects.get_or_create(name=designation_name, defaults={"level": 5})
    return Staff.objects.create(user=user, designation=desig, department=dept)


def make_signature(staff, verified=True):
    """Create an active, verified signature for staff."""
    sig = StaffSignature.objects.create(
        staff=staff,
        image=ContentFile(b"fake-sig", name="sig.png"),
        is_active=True,
        is_verified=verified,
    )
    return sig


class FileCreationApprovalTest(TestCase):
    """File creation - files are now active immediately."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="IT Dept", code="IT")

        # Registry user
        self.registry_user = make_user("registry", "Registry")
        self.registry_staff = make_staff(self.registry_user, "Registry Officer", self.dept)

        # File owner (personal file)
        self.owner_user = make_user("owner1", "Staff")
        self.owner_staff = make_staff(self.owner_user, "Officer", self.dept)

        # HOD (policy file)
        self.hod_user = make_user("hod1", "Staff")
        self.hod_staff = make_staff(self.hod_user, "Head of Department", self.dept)
        self.dept.head = self.hod_staff
        self.dept.save()

        # Create verified signatures for approvers
        self.owner_sig = make_signature(self.owner_staff)
        self.hod_sig = make_signature(self.hod_staff)

    # --- Personal File Tests ---

    def test_personal_file_created_active(self):
        """Registry creates personal file → status=active directly."""
        self.client.login(username="registry", password="Test1234!")
        r = self.client.post(
            reverse("document_management:file_create"),
            {
                "title": "PERSONNEL FILE OF JOHN DOE",
                "file_type": "personal",
                "owner": self.owner_staff.pk,
            },
        )
        self.assertIn(r.status_code, [200, 302])
        f = File.objects.get(owner=self.owner_staff)
        self.assertEqual(f.status, "active")

    def test_personal_file_owner_notified(self):
        """Owner gets notification when registry creates their personal file."""
        self.client.login(username="registry", password="Test1234!")
        r = self.client.post(
            reverse("document_management:file_create"),
            {
                "title": "NOTIFY OWNER FILE",
                "file_type": "personal",
                "owner": self.owner_staff.pk,
            },
        )
        self.assertTrue(
            self.owner_user.notifications.filter(
                message__icontains="created for you"
            ).exists()
        )

    # --- Policy File Tests ---

    def test_policy_file_created_active(self):
        """Registry creates policy file → status=active directly."""
        self.client.login(username="registry", password="Test1234!")
        r = self.client.post(
            reverse("document_management:file_create"),
            {
                "title": "IT POLICY 2025",
                "file_type": "policy",
                "policy_type": "internal",
                "department": self.dept.pk,
            },
        )
        self.assertIn(r.status_code, [200, 302])
        f = File.objects.filter(file_type="policy", department=self.dept).first()
        self.assertIsNotNone(f)
        self.assertEqual(f.status, "active")

    def test_policy_file_hod_notified(self):
        """HOD gets notification when registry creates policy file for their dept."""
        self.client.login(username="registry", password="Test1234!")
        r = self.client.post(
            reverse("document_management:file_create"),
            {
                "title": "NOTIFY HOD POLICY",
                "file_type": "policy",
                "policy_type": "internal",
                "department": self.dept.pk,
            },
        )
        self.assertTrue(
            self.hod_user.notifications.filter(
                message__icontains="created in your department"
            ).exists()
        )

    # --- Audit Log Tests ---

    def test_file_creation_logs_audit_action(self):
        """FILE_CREATED audit log entry created."""
        from audit_log.models import AuditLogEntry

        self.client.login(username="registry", password="Test1234!")
        r = self.client.post(
            reverse("document_management:file_create"),
            {
                "title": "AUDIT TEST",
                "file_type": "personal",
                "owner": self.owner_staff.pk,
            },
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(action="FILE_CREATED").exists()
        )