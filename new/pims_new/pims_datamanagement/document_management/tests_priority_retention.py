"""
Tests for Priority System and Urgent Document Notifications.
"""
from datetime import timedelta

from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from organization.models import Department, Designation, Staff
from user_management.models import CustomUser

from document_management.models import Document, File


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


class PriorityNotificationTest(TestCase):
    """Tests for document priority levels and urgent reminders."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="IT", code="IT")

        # Registry
        self.reg_user = make_user("reg_pri", "Registry")
        self.reg_staff = make_staff(self.reg_user, "Registry Officer", self.dept)

        # Staff users
        self.staff_user = make_user("staff_pri", "Staff")
        self.staff = make_staff(self.staff_user, "Officer", self.dept)

        self.other_user = make_user("staff_pri2", "Staff")
        self.other_staff = make_staff(self.other_user, "Officer", self.dept)

        # Create active file
        self.file = File.objects.create(
            title="PRIORITY TEST FILE",
            file_type="personal",
            owner=self.staff,
            department=self.dept,
            current_location=self.staff,
            created_by=self.reg_user,
            status="active",
        )

    def test_document_default_priority_normal(self):
        """New document defaults to normal priority."""
        doc = Document.objects.create(
            file=self.file, uploaded_by=self.reg_user, title="Normal Doc"
        )
        self.assertEqual(doc.priority, "normal")

    def test_document_can_set_urgent_priority(self):
        """Document can be created with urgent priority."""
        doc = Document.objects.create(
            file=self.file, uploaded_by=self.reg_user, title="Urgent Doc", priority="urgent"
        )
        self.assertEqual(doc.priority, "urgent")

    def test_document_can_set_high_priority(self):
        """Document can be created with high priority."""
        doc = Document.objects.create(
            file=self.file, uploaded_by=self.reg_user, title="High Doc", priority="high"
        )
        self.assertEqual(doc.priority, "high")

    def test_priority_choices(self):
        """Priority field has correct choices."""
        from document_management.models import Document

        choices = dict(Document.PRIORITY_CHOICES)
        self.assertEqual(choices["normal"], "Normal")
        self.assertEqual(choices["high"], "High Priority")
        self.assertEqual(choices["urgent"], "Urgent")

    def test_urgent_document_reminder_task_exists(self):
        """Celery task for urgent reminders is importable."""
        from document_management.tasks import send_urgent_document_reminders

        self.assertTrue(callable(send_urgent_document_reminders))

    def test_retention_reminder_task_exists(self):
        """Celery task for 48hr retention reminders is importable."""
        from document_management.tasks import send_file_retention_reminders

        self.assertTrue(callable(send_file_retention_reminders))

    def test_file_overdue_check(self):
        """File.is_overdue() returns True after 48 hours."""
        # File created 3 days ago
        self.file.created_at = timezone.now() - timedelta(days=3)
        self.file.save()

        self.assertTrue(self.file.is_overdue(threshold_days=2))

    def test_file_not_overdue_within_48hrs(self):
        """File.is_overdue() returns False within 48 hours."""
        self.assertFalse(self.file.is_overdue(threshold_days=2))

    def test_file_custody_duration(self):
        """File.get_custody_duration() returns days at current location."""
        self.file.created_at = timezone.now() - timedelta(days=5)
        self.file.save()

        duration = self.file.get_custody_duration()
        self.assertEqual(duration, 5)

    def test_urgent_documents_notify_custodian(self):
        """Urgent documents trigger notification to current custodian after 24hrs."""
        from document_management.tasks import send_urgent_document_reminders

        # Create urgent doc older than 24hrs
        doc = Document.objects.create(
            file=self.file,
            uploaded_by=self.reg_user,
            title="URGENT REMINDER DOC",
            priority="urgent",
            uploaded_at=timezone.now() - timedelta(hours=25),
            status="pending",
        )

        # Run task
        result = send_urgent_document_reminders()

        # Check notification sent to custodian
        self.assertTrue(
            self.staff_user.notifications.filter(
                message__icontains="URGENT REMINDER",
            ).filter(
                message__icontains="URGENT REMINDER DOC",
            ).exists()
        )

    def test_high_priority_documents_notify_custodian(self):
        """High priority documents also trigger 24hr reminder."""
        from document_management.tasks import send_urgent_document_reminders

        doc = Document.objects.create(
            file=self.file,
            uploaded_by=self.reg_user,
            title="HIGH REMINDER DOC",
            priority="high",
            uploaded_at=timezone.now() - timedelta(hours=25),
            status="pending",
        )

        send_urgent_document_reminders()

        self.assertTrue(
            self.staff_user.notifications.filter(
                message__icontains="HIGH REMINDER DOC",
            ).exists()
        )

    def test_normal_priority_no_reminder(self):
        """Normal priority documents do not trigger urgent reminders."""
        from document_management.tasks import send_urgent_document_reminders

        doc = Document.objects.create(
            file=self.file,
            uploaded_by=self.reg_user,
            title="NORMAL DOC",
            priority="normal",
            uploaded_at=timezone.now() - timedelta(hours=25),
            status="pending",
        )

        result = send_urgent_document_reminders()

        self.assertFalse(
            self.staff_user.notifications.filter(
                message__icontains="NORMAL DOC",
            ).exists()
        )

    def test_retention_reminder_notifies_custodian(self):
        """48hr retention reminder notifies file custodian."""
        from document_management.tasks import send_file_retention_reminders

        # File at staff location for 3 days
        self.file.created_at = timezone.now() - timedelta(days=3)
        self.file.status = "active"
        self.file.current_location = self.staff
        self.file.save()

        # Exclude registry
        from organization.models import Staff as StaffModel
        from django.db.models import Q
        registry_staff = StaffModel.objects.filter(
            Q(designation__name__icontains="registry") | Q(user__groups__name__iexact="Registry")
        ).first()

        result = send_file_retention_reminders()

        self.assertTrue(
            self.staff_user.notifications.filter(
                message__icontains="REMINDER",
            ).filter(
                message__icontains=self.file.file_number,
            ).exists()
        )

    def test_registry_excluded_from_retention_reminders(self):
        """Registry staff do not receive retention reminders."""
        from document_management.tasks import send_file_retention_reminders

        # File at registry
        self.file.created_at = timezone.now() - timedelta(days=3)
        self.file.current_location = self.reg_staff
        self.file.save()

        result = send_file_retention_reminders()

        self.assertFalse(
            self.reg_user.notifications.filter(
                message__icontains=self.file.file_number
            ).exists()
        )


from django.test import TestCase


class FileCreationApprovalModelTest(TestCase):
    """Model-level tests for file creation approval."""

    def setUp(self):
        self.dept = Department.objects.create(name="Test Dept", code="TST")
        reg_user = make_user("reg_mod", "Registry")
        self.reg_staff = make_staff(reg_user, "Registry Officer", self.dept)

        owner_user = make_user("owner_mod", "Staff")
        self.owner = make_staff(owner_user, "Officer", self.dept)

    def test_default_file_status_pending_approval(self):
        """New files default to pending_approval status."""
        f = File.objects.create(
            title="DEFAULT STATUS",
            file_type="personal",
            owner=self.owner,
            department=self.dept,
            current_location=self.reg_staff,
            created_by=reg_user,
        )
        self.assertEqual(f.status, "pending_approval")

    def test_rejected_status_available(self):
        """File can have rejected status."""
        f = File.objects.create(
            title="REJECTED FILE",
            file_type="personal",
            owner=self.owner,
            department=self.dept,
            current_location=self.reg_staff,
            created_by=reg_user,
            status="rejected",
        )
        self.assertEqual(f.status, "rejected")
        self.assertIn(("rejected", "Rejected"), File._meta.get_field("status").choices)