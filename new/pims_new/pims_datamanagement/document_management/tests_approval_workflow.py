"""
Tests for File Creation Approval Workflow with Digital Signatures.

Covers:
1. File created with pending_approval status
2. Owner/HOD approval with verified signature
3. Owner/HOD rejection with reason
4. Registry notified on approval
5. Creator notified on approval/rejection
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

from document_management.models import Document, File, FileAccessRequest


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
    """File creation approval workflow tests."""

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

    def test_personal_file_created_pending_approval(self):
        """Registry creates personal file → status=pending_approval."""
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
        self.assertEqual(f.status, "pending_approval")

    def test_personal_file_owner_approves_with_signature(self):
        """Owner approves personal file with verified signature → status=pending_activation."""
        # Create file in pending_approval
        f = File.objects.create(
            title="PERSONNEL FILE OF JANE DOE",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        r = self.client.post(approval_url, {"action": "approve"})

        f.refresh_from_db()
        self.assertEqual(f.status, "pending_activation")
        self.assertEqual(f.current_location, self.owner_staff)

    def test_personal_file_owner_rejects_with_reason(self):
        """Owner rejects personal file with reason → status=inactive."""
        f = File.objects.create(
            title="REJECT TEST FILE",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        r = self.client.post(approval_url, {"action": "reject", "rejection_reason": "Missing documents"})

        f.refresh_from_db()
        self.assertEqual(f.status, "inactive")

    def test_personal_file_reject_requires_reason(self):
        """Rejection without reason fails."""
        f = File.objects.create(
            title="REJECT NO REASON",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        r = self.client.post(approval_url, {"action": "reject", "rejection_reason": ""})

        f.refresh_from_db()
        self.assertEqual(f.status, "pending_approval")  # unchanged

    def test_personal_file_approval_requires_verified_signature(self):
        """Owner without verified signature cannot approve."""
        # Remove verified signature
        self.owner_sig.is_verified = False
        self.owner_sig.save()

        f = File.objects.create(
            title="NO SIG FILE",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        r = self.client.post(approval_url, {"action": "approve"})

        f.refresh_from_db()
        self.assertEqual(f.status, "pending_approval")  # unchanged

    def test_non_owner_cannot_approve_personal_file(self):
        """Another staff cannot approve personal file."""
        other_user = make_user("other_staff", "Staff")
        other_staff = make_staff(other_user, "Officer", self.dept)
        make_signature(other_staff)

        f = File.objects.create(
            title="OTHER FILE",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="other_staff", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        r = self.client.post(approval_url, {"action": "approve"})

        f.refresh_from_db()
        self.assertEqual(f.status, "pending_approval")

    # --- Policy File Tests ---

    def test_policy_file_created_pending_approval(self):
        """Registry creates policy file → status=pending_approval."""
        self.client.login(username="registry", password="Test1234!")
        r = self.client.post(
            reverse("document_management:file_create"),
            {
                "title": "IT POLICY 2025",
                "file_type": "policy",
                "department": self.dept.pk,
            },
        )
        self.assertIn(r.status_code, [200, 302])
        f = File.objects.filter(file_type="policy", department=self.dept).first()
        self.assertEqual(f.status, "pending_approval")

    def test_policy_file_hod_approves_with_signature(self):
        """HOD approves policy file with verified signature → status=pending_activation."""
        f = File.objects.create(
            title="HR POLICY",
            file_type="policy",
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="hod1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        r = self.client.post(approval_url, {"action": "approve"})

        f.refresh_from_db()
        self.assertEqual(f.status, "pending_activation")
        self.assertEqual(f.current_location, self.hod_staff)

    def test_policy_file_hod_rejects_with_reason(self):
        """HOD rejects policy file with reason → status=inactive."""
        f = File.objects.create(
            title="POLICY REJECT",
            file_type="policy",
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="hod1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        r = self.client.post(approval_url, {"action": "reject", "rejection_reason": "Needs revision"})

        f.refresh_from_db()
        self.assertEqual(f.status, "inactive")

    def test_non_hod_cannot_approve_policy_file(self):
        """Non-HOD staff cannot approve policy file."""
        f = File.objects.create(
            title="POLICY FILE",
            file_type="policy",
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")  # regular officer
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        r = self.client.post(approval_url, {"action": "approve"})

        f.refresh_from_db()
        self.assertEqual(f.status, "pending_approval")

    # --- Notification Tests ---

    def test_approval_notifies_registry(self):
        """Registry receives notification when file is approved."""
        f = File.objects.create(
            title="NOTIFY REGISTRY",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        self.client.post(approval_url, {"action": "approve"})

        # Check registry has notification
        self.assertTrue(
            self.registry_user.notifications.filter(
                message__icontains="approved", link__icontains=f.file_number
            ).exists()
        )

    def test_approval_notifies_creator(self):
        """File creator receives notification on approval."""
        f = File.objects.create(
            title="NOTIFY CREATOR",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        self.client.post(approval_url, {"action": "approve"})

        # Check creator has notification
        self.assertTrue(
            self.registry_user.notifications.filter(
                message__icontains="approved", link__icontains=f.file_number
            ).exists()
        )

    def test_rejection_notifies_creator(self):
        """File creator receives notification on rejection with reason."""
        f = File.objects.create(
            title="REJECT NOTIFY",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        self.client.post(approval_url, {"action": "reject", "rejection_reason": "Incomplete"})

        self.assertTrue(
            self.registry_user.notifications.filter(
                message__icontains="rejected",
            ).filter(
                message__icontains="Incomplete",
            ).exists()
        )

    # --- Status Transition Tests ---

    def test_file_status_pending_approval_to_pending_activation_to_active(self):
        """Full lifecycle: pending_approval → pending_activation → active (by registry)."""
        f = File.objects.create(
            title="LIFECYCLE FILE",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        # Owner approves
        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        self.client.post(approval_url, {"action": "approve"})

        f.refresh_from_db()
        self.assertEqual(f.status, "pending_activation")
        self.assertEqual(f.current_location, self.owner_staff)

        # Registry activates
        self.client.login(username="registry", password="Test1234!")
        self.client.post(reverse("document_management:file_approve_activation", kwargs={"pk": f.pk}))

        f.refresh_from_db()
        self.assertEqual(f.status, "active")

    def test_approval_logs_audit_action(self):
        """FILE_CREATION_APPROVED audit log entry created."""
        from audit_log.models import AuditLogEntry

        f = File.objects.create(
            title="AUDIT TEST",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        self.client.post(approval_url, {"action": "approve"})

        self.assertTrue(
            AuditLogEntry.objects.filter(
                action="FILE_CREATION_APPROVED", object_id=f.pk
            ).exists()
        )

    def test_rejection_logs_audit_action(self):
        """FILE_CREATION_REJECTED audit log entry created."""
        from audit_log.models import AuditLogEntry

        f = File.objects.create(
            title="REJECT AUDIT",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        self.client.post(approval_url, {"action": "reject", "rejection_reason": "Test reason"})

        self.assertTrue(
            AuditLogEntry.objects.filter(
                action="FILE_CREATION_REJECTED", object_id=f.pk
            ).exists()
        )

    def test_approval_page_shows_signature_preview(self):
        """Approval page displays approver's verified signature."""
        f = File.objects.create(
            title="SIG PREVIEW",
            file_type="personal",
            owner=self.owner_staff,
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="pending_approval",
        )

        self.client.login(username="owner1", password="Test1234!")
        approval_url = reverse("document_management:file_approve_creation", kwargs={"pk": f.pk})
        r = self.client.get(approval_url)

        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Your Verified Signature")

    def test_file_creation_notifies_owner(self):
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

    def test_file_creation_notifies_hod_for_policy(self):
        """HOD gets notification when registry creates policy file for their dept."""
        self.client.login(username="registry", password="Test1234!")
        r = self.client.post(
            reverse("document_management:file_create"),
            {
                "title": "NOTIFY HOD POLICY",
                "file_type": "policy",
                "department": self.dept.pk,
            },
        )

        self.assertTrue(
            self.hod_user.notifications.filter(
                message__icontains="created in your department"
            ).exists()
        )