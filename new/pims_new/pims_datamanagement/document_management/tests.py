"""
End-to-end simulation tests for PIMS core flows.
Covers: user auth, file lifecycle, document upload, access requests, approval chains.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import Group
from user_management.models import CustomUser
from organization.models import Staff, Department, Designation, Unit
from document_management.models import File, Document, FileAccessRequest, ApprovalChain, ApprovalStep


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


class AuthFlowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user("teststaff", "Staff")
        make_staff(self.user)

    def test_login_success(self):
        r = self.client.post(reverse("user_management:login"), {"username": "teststaff", "password": "Test1234!"})
        self.assertIn(r.status_code, [200, 302])

    def test_login_wrong_password(self):
        r = self.client.post(reverse("user_management:login"), {"username": "teststaff", "password": "wrong"})
        self.assertEqual(r.status_code, 200)  # stays on login page

    def test_dashboard_requires_login(self):
        r = self.client.get(reverse("home"))
        self.assertEqual(r.status_code, 302)  # redirect to login


class FileLifecycleTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="IT Dept", code="IT")
        self.registry_user = make_user("registry", "Registry")
        self.registry_staff = make_staff(self.registry_user, "Registry Officer")
        self.staff_user = make_user("staffuser", "Staff")
        self.staff = make_staff(self.staff_user, "Officer", self.dept)
        self.client.login(username="registry", password="Test1234!")

    def test_create_file(self):
        r = self.client.post(reverse("document_management:file_create"), {
            "title": "TEST FILE",
            "file_type": "personal",
            "owner": self.staff.pk,
        })
        self.assertIn(r.status_code, [200, 302])
        self.assertTrue(File.objects.filter(owner=self.staff).exists())

    def test_registry_cannot_own_file(self):
        from django.core.exceptions import ValidationError
        f = File(title="REG FILE", file_type="personal", owner=self.registry_staff)
        with self.assertRaises(ValidationError):
            f.full_clean()

    def test_file_activation(self):
        f = File.objects.create(
            title="ACTIVATION TEST", file_type="personal",
            owner=self.staff, current_location=self.registry_staff,
            created_by=self.registry_user
        )
        r = self.client.post(reverse("document_management:file_approve_activation", kwargs={"pk": f.pk}))
        f.refresh_from_db()
        self.assertEqual(f.status, "active")

    def test_file_close(self):
        f = File.objects.create(
            title="CLOSE TEST", file_type="personal",
            owner=self.staff, current_location=self.registry_staff,
            created_by=self.registry_user, status="active"
        )
        r = self.client.post(reverse("document_management:file_close", kwargs={"pk": f.pk}))
        f.refresh_from_db()
        self.assertEqual(f.status, "closed")

    def test_current_location_display_registry(self):
        f = File.objects.create(
            title="DISPLAY TEST", file_type="personal",
            owner=self.staff, current_location=self.registry_staff,
            created_by=self.registry_user
        )
        self.assertEqual(f.current_location_display, "Registry")

    def test_current_location_display_staff(self):
        f = File.objects.create(
            title="DISPLAY TEST 2", file_type="personal",
            owner=self.staff, current_location=self.staff,
            created_by=self.registry_user
        )
        self.assertNotEqual(f.current_location_display, "Registry")


class DocumentUploadTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="HR", code="HR")
        self.registry_user = make_user("reg2", "Registry")
        self.registry_staff = make_staff(self.registry_user, "Registry Officer")
        self.staff_user = make_user("staff2", "Staff")
        self.staff = make_staff(self.staff_user, "Officer", self.dept)
        self.file = File.objects.create(
            title="DOC TEST FILE", file_type="personal",
            owner=self.staff, current_location=self.registry_staff,
            created_by=self.registry_user, status="active"
        )
        self.client.login(username="reg2", password="Test1234!")

    def test_upload_document(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        # Use a non-PDF to avoid watermark processing
        f = SimpleUploadedFile("test.txt", b"plain text content", content_type="text/plain")
        r = self.client.post(
            reverse("document_management:document_add", kwargs={"file_pk": self.file.pk}),
            {"file": self.file.pk, "title": "Test Doc", "attachment": f}
        )
        self.assertIn(r.status_code, [200, 302])
        self.assertTrue(Document.objects.filter(file=self.file).exists())


class AccessRequestTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Finance", code="FIN")
        self.registry_user = make_user("reg3", "Registry")
        self.registry_staff = make_staff(self.registry_user, "Registry Officer")
        self.staff_user = make_user("staff3", "Staff")
        self.staff = make_staff(self.staff_user, "Officer", self.dept)
        self.file = File.objects.create(
            title="ACCESS TEST FILE", file_type="personal",
            owner=self.staff, current_location=self.registry_staff,
            created_by=self.registry_user, status="active"
        )

    def test_access_request_approve_transfers_custody(self):
        req = FileAccessRequest.objects.create(
            file=self.file, requested_by=self.staff_user,
            reason="Need access", access_type="read_write", status="pending"
        )
        self.client.login(username="reg3", password="Test1234!")
        self.client.post(reverse("document_management:access_request_approve", kwargs={"pk": req.pk}))
        req.refresh_from_db()
        self.file.refresh_from_db()
        self.assertEqual(req.status, "approved")
        self.assertEqual(self.file.current_location, self.staff)

    def test_access_request_reject(self):
        req = FileAccessRequest.objects.create(
            file=self.file, requested_by=self.staff_user,
            reason="Need access", access_type="read_only", status="pending"
        )
        self.client.login(username="reg3", password="Test1234!")
        self.client.post(
            reverse("document_management:access_request_reject", kwargs={"pk": req.pk}),
            {"denial_reason": "Insufficient justification"}
        )
        req.refresh_from_db()
        self.assertEqual(req.status, "rejected")


class ApprovalChainTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Admin", code="ADM")
        self.registry_user = make_user("reg4", "Registry")
        self.registry_staff = make_staff(self.registry_user, "Registry Officer")
        self.owner_user = make_user("owner1", "Staff")
        self.owner_staff = make_staff(self.owner_user, "Officer", self.dept)
        self.approver_user = make_user("approver1", "Staff")
        self.approver_staff = make_staff(self.approver_user, "HOD", self.dept)
        self.file = File.objects.create(
            title="CHAIN TEST FILE", file_type="personal",
            owner=self.owner_staff, current_location=self.registry_staff,
            created_by=self.owner_user, status="active"
        )
        self.client.login(username="owner1", password="Test1234!")

    def test_create_chain(self):
        r = self.client.post(
            reverse("document_management:chain_create", kwargs={"file_pk": self.file.pk}),
            {"approvers": [self.approver_staff.pk]}
        )
        self.assertTrue(ApprovalChain.objects.filter(file=self.file).exists())
        chain = ApprovalChain.objects.get(file=self.file)
        self.assertEqual(chain.status, "draft")
        self.assertEqual(chain.steps.count(), 1)

    def test_start_chain(self):
        chain = ApprovalChain.objects.create(file=self.file, created_by=self.owner_user, status="draft")
        ApprovalStep.objects.create(chain=chain, approver=self.approver_staff, order=1)
        r = self.client.post(reverse("document_management:chain_start", kwargs={"file_pk": self.file.pk}))
        chain.refresh_from_db()
        self.assertEqual(chain.status, "active")

    def test_approve_step(self):
        from organization.models import StaffSignature
        from django.core.files.uploadedfile import SimpleUploadedFile
        chain = ApprovalChain.objects.create(file=self.file, created_by=self.owner_user, status="active", current_step=1)
        step = ApprovalStep.objects.create(chain=chain, approver=self.approver_staff, order=1)
        # Approver needs an active signature
        sig_file = SimpleUploadedFile("sig.png", b"fake-image", content_type="image/png")
        StaffSignature.objects.create(staff=self.approver_staff, image=sig_file, is_active=True, is_verified=True)
        self.client.login(username="approver1", password="Test1234!")
        self.client.post(
            reverse("document_management:step_action", kwargs={"step_pk": step.pk}),
            {"action": "approve"}
        )
        step.refresh_from_db()
        self.assertEqual(step.status, "approved")


class StaffFolderHubTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Legal", code="LEG")
        self.registry_user = make_user("reg5", "Registry")
        self.registry_staff = make_staff(self.registry_user, "Registry Officer")
        self.staff_user = make_user("staff5", "Staff")
        self.staff = make_staff(self.staff_user, "Officer", self.dept)
        self.client.login(username="reg5", password="Test1234!")

    def test_registry_staff_hub_returns_404(self):
        r = self.client.get(reverse("document_management:staff_folder_hub", kwargs={"pk": self.registry_staff.pk}))
        self.assertEqual(r.status_code, 404)

    def test_staff_hub_accessible(self):
        r = self.client.get(reverse("document_management:staff_folder_hub", kwargs={"pk": self.staff.pk}))
        self.assertEqual(r.status_code, 200)
