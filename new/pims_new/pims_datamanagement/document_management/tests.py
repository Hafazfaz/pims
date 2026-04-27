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

    def test_file_close_blocked_by_active_chain(self):
        f = File.objects.create(
            title="CHAIN BLOCK TEST", file_type="personal",
            owner=self.staff, current_location=self.registry_staff,
            created_by=self.registry_user, status="active"
        )
        doc = Document.objects.create(file=f, uploaded_by=self.registry_user, title="Doc")
        ApprovalChain.objects.create(file=f, document=doc, created_by=self.registry_user, status="active")
        r = self.client.post(reverse("document_management:file_close", kwargs={"pk": f.pk}))
        f.refresh_from_db()
        self.assertEqual(f.status, "active")  # not closed

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


class LeaveRequestChainTest(TestCase):
    """
    End-to-end simulation: Leave request document dispatched via chain.
    Flow: Unit Manager → HOD
    Scenario:
      1. Staff submits leave request document
      2. Chain applied: Unit Manager → HOD
      3. HOD rejects → file returns to Unit Manager
      4. Unit Manager re-approves (addresses HOD comment)
      5. Goes back to HOD → HOD approves → file returns to registry
    """

    def setUp(self):
        self.dept = Department.objects.create(name="Finance", code="FIN")
        self.unit = Unit.objects.create(name="Accounts Unit", department=self.dept)

        # Registry
        reg_user = make_user("registry_user", "Registry")
        reg_desig, _ = Designation.objects.get_or_create(name="Registry Officer", defaults={"level": 1})
        self.registry = Staff.objects.create(user=reg_user, designation=reg_desig, department=self.dept)

        # Staff (file owner)
        staff_user = make_user("john_staff", "Staff")
        staff_desig, _ = Designation.objects.get_or_create(name="Officer", defaults={"level": 5})
        self.staff = Staff.objects.create(user=staff_user, designation=staff_desig, department=self.dept, unit=self.unit)

        # Unit Manager
        um_user = make_user("unit_mgr", "Staff")
        um_desig, _ = Designation.objects.get_or_create(name="Unit Manager", defaults={"level": 3})
        self.unit_manager = Staff.objects.create(user=um_user, designation=um_desig, department=self.dept, unit=self.unit)
        self.unit.head = self.unit_manager
        self.unit.save()

        # HOD
        hod_user = make_user("hod_user", "Staff")
        hod_desig, _ = Designation.objects.get_or_create(name="Head of Department", defaults={"level": 2})
        self.hod = Staff.objects.create(user=hod_user, designation=hod_desig, department=self.dept)
        self.dept.head = self.hod
        self.dept.save()

        # Signature for unit manager and HOD (required for step action)
        from organization.models import StaffSignature
        from django.core.files.base import ContentFile
        sig_content = ContentFile(b"fake-sig", name="sig.png")
        self.um_sig = StaffSignature.objects.create(staff=self.unit_manager, image=sig_content, is_active=True, is_verified=True)
        self.hod_sig = StaffSignature.objects.create(staff=self.hod, image=sig_content, is_active=True, is_verified=True)

        # Create and activate file owned by staff, currently at unit manager
        self.file = File.objects.create(
            title="LEAVE REQUEST FILE",
            file_type="personal",
            owner=self.staff,
            department=self.dept,
            status="active",
            current_location=self.unit_manager,
            created_by=staff_user,
        )

        # Leave request document
        self.doc = Document.objects.create(
            file=self.file,
            uploaded_by=staff_user,
            title="Annual Leave Request 2026",
            minute_content="I request 10 days annual leave from May 1.",
        )

    def _apply_chain(self):
        """Create chain: Step 1 = Unit Manager, Step 2 = HOD."""
        chain = ApprovalChain.objects.create(
            document=self.doc,
            file=self.file,
            created_by=self.unit_manager.user,
            status='active',
            current_step=1,
        )
        self.step1 = ApprovalStep.objects.create(chain=chain, approver=self.unit_manager, order=1)
        self.step2 = ApprovalStep.objects.create(chain=chain, approver=self.hod, order=2)
        self.chain = chain
        # File dispatched to unit manager (step 1)
        self.file.current_location = self.unit_manager
        self.file.save()
        return chain

    def test_full_chain_approve_flow(self):
        """Happy path: Unit Manager approves → HOD approves → file to registry."""
        chain = self._apply_chain()

        # Step 1: Unit Manager approves
        self.step1.status = 'approved'
        self.step1.signature = self.um_sig
        self.step1.save()
        chain.advance()

        chain.refresh_from_db()
        self.file.refresh_from_db()
        self.assertEqual(chain.current_step, 2)
        self.assertEqual(self.file.current_location, self.hod)

        # Step 2: HOD approves
        self.step2.status = 'approved'
        self.step2.signature = self.hod_sig
        self.step2.save()
        chain.advance()

        chain.refresh_from_db()
        self.file.refresh_from_db()
        self.assertEqual(chain.status, 'closed')
        self.assertEqual(self.file.current_location, self.registry)

    def test_hod_rejects_then_unit_manager_resubmits(self):
        """
        HOD rejects at step 2 → file back to Unit Manager.
        Unit Manager re-approves → back to HOD → HOD approves → registry.
        """
        chain = self._apply_chain()

        # Step 1: Unit Manager approves
        self.step1.status = 'approved'
        self.step1.signature = self.um_sig
        self.step1.save()
        chain.advance()

        chain.refresh_from_db()
        self.assertEqual(chain.current_step, 2)

        # Step 2: HOD rejects
        self.step2.note = "Please revise — dates conflict with project deadline."
        self.step2.save()
        chain.reject_to_previous(from_order=2)

        chain.refresh_from_db()
        self.file.refresh_from_db()
        self.step1.refresh_from_db()
        # File back to unit manager
        self.assertEqual(self.file.current_location, self.unit_manager)
        self.assertEqual(chain.current_step, 1)
        self.assertEqual(self.step1.status, 'pending')

        # Unit Manager addresses comment and re-approves
        self.step1.status = 'approved'
        self.step1.note = "Revised dates: May 15–25 to avoid conflict."
        self.step1.signature = self.um_sig
        self.step1.save()
        chain.advance()

        chain.refresh_from_db()
        self.file.refresh_from_db()
        self.assertEqual(chain.current_step, 2)
        self.assertEqual(self.file.current_location, self.hod)

        # HOD approves
        self.step2.status = 'approved'
        self.step2.signature = self.hod_sig
        self.step2.save()
        chain.advance()

        chain.refresh_from_db()
        self.file.refresh_from_db()
        self.assertEqual(chain.status, 'closed')
        self.assertEqual(self.file.current_location, self.registry)

    def test_file_is_readonly_during_active_chain(self):
        """File should report is_in_active_chain=True while chain is active."""
        self._apply_chain()
        self.assertTrue(self.file.is_in_active_chain)

    def test_file_not_readonly_after_chain_closes(self):
        """After chain completes, is_in_active_chain should be False."""
        chain = self._apply_chain()
        self.step1.status = 'approved'
        self.step1.save()
        chain.advance()
        self.step2.status = 'approved'
        self.step2.save()
        chain.advance()
        self.file.refresh_from_db()
        self.assertFalse(self.file.is_in_active_chain)


class DocumentStatusTest(TestCase):
    """Tests for document status transitions: pending → in_transit → approved/rejected."""

    def setUp(self):
        self.dept = Department.objects.create(name="Ops", code="OPS")
        reg_user = make_user("reg_vs", "Registry")
        reg_desig, _ = Designation.objects.get_or_create(name="Registry Officer", defaults={"level": 1})
        self.registry = Staff.objects.create(user=reg_user, designation=reg_desig, department=self.dept)

        owner_user = make_user("owner_vs", "Staff")
        desig, _ = Designation.objects.get_or_create(name="Officer", defaults={"level": 5})
        self.owner = Staff.objects.create(user=owner_user, designation=desig, department=self.dept)

        approver_user = make_user("approver_vs", "Staff")
        self.approver = Staff.objects.create(user=approver_user, designation=desig, department=self.dept)

        from organization.models import StaffSignature
        from django.core.files.base import ContentFile
        sig = ContentFile(b"fake", name="sig.png")
        self.sig = StaffSignature.objects.create(staff=self.approver, image=sig, is_active=True, is_verified=True)

        self.file = File.objects.create(
            title="STATUS TEST FILE", file_type="personal",
            owner=self.owner, current_location=self.registry,
            created_by=owner_user, status="active",
        )
        self.doc = Document.objects.create(
            file=self.file, uploaded_by=owner_user,
            title="Policy Draft", minute_content="Initial draft.",
        )

    def _make_chain(self, doc):
        chain = ApprovalChain.objects.create(
            document=doc, file=self.file,
            created_by=self.owner.user, status='active', current_step=1,
        )
        step = ApprovalStep.objects.create(chain=chain, approver=self.approver, order=1)
        return chain, step

    def test_new_document_is_pending(self):
        self.assertEqual(self.doc.status, 'pending')

    def test_dispatch_sets_in_transit(self):
        self.doc.status = 'in_transit'
        self.doc.save()
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'in_transit')

    def test_all_approve_sets_approved(self):
        chain, step = self._make_chain(self.doc)
        step.status = 'approved'
        step.signature = self.sig
        step.save()
        chain.advance()
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'approved')

    def test_reject_at_step1_sets_rejected(self):
        chain, _ = self._make_chain(self.doc)
        chain.reject_to_previous(from_order=1)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'rejected')

    def test_multiple_chains_per_document(self):
        """A document can have multiple chain runs (e.g. rejected then re-dispatched)."""
        chain1, _ = self._make_chain(self.doc)
        chain1.reject_to_previous(from_order=1)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'rejected')

        chain2, step2 = self._make_chain(self.doc)
        self.doc.status = 'in_transit'
        self.doc.save()
        step2.status = 'approved'
        step2.signature = self.sig
        step2.save()
        chain2.advance()

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'approved')
        self.assertEqual(self.doc.approval_chains.count(), 2)

    def test_chain_reference_file(self):
        """Chain can optionally reference other documents from the same file."""
        other_doc = Document.objects.create(
            file=self.file, uploaded_by=self.owner.user,
            title="Supporting Doc", minute_content="Supporting content.",
        )
        chain, _ = self._make_chain(self.doc)
        chain.reference_documents.set([other_doc])
        self.assertIn(other_doc, chain.reference_documents.all())

    def test_chain_reference_file_is_optional(self):
        """Chain can be dispatched without reference documents."""
        chain, _ = self._make_chain(self.doc)
        self.assertEqual(chain.reference_documents.count(), 0)


class DispatchPermissionTest(TestCase):
    """Personal files: owner only. Policy files: HOD only. Recall revokes access."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Finance", code="FIN")

        reg_user = make_user("reg_dp", "Registry")
        desig_reg, _ = Designation.objects.get_or_create(name="Registry Officer", defaults={"level": 1})
        self.registry = Staff.objects.create(user=reg_user, designation=desig_reg, department=self.dept)

        owner_user = make_user("owner_dp", "Staff")
        desig, _ = Designation.objects.get_or_create(name="Officer", defaults={"level": 5})
        self.owner = Staff.objects.create(user=owner_user, designation=desig, department=self.dept)

        other_user = make_user("other_dp", "Staff")
        self.other = Staff.objects.create(user=other_user, designation=desig, department=self.dept)

        hod_user = make_user("hod_dp", "Staff")
        hod_desig, _ = Designation.objects.get_or_create(name="Head of Department", defaults={"level": 2})
        self.hod = Staff.objects.create(user=hod_user, designation=hod_desig, department=self.dept)
        self.dept.head = self.hod
        self.dept.save()

        self.personal_file = File.objects.create(
            title="PERSONAL FILE", file_type="personal",
            owner=self.owner, current_location=self.registry,
            created_by=owner_user, status="active",
        )
        self.policy_file = File.objects.create(
            title="POLICY FILE", file_type="policy",
            department=self.dept, current_location=self.registry,
            created_by=reg_user, status="active",
        )
        from document_management.models import ChainTemplate, ChainTemplateStep
        self.tmpl = ChainTemplate.objects.create(name="Test Chain", created_by=reg_user, is_active=True)
        ChainTemplateStep.objects.create(template=self.tmpl, order=1, role_type='specific_person', staff=self.hod)

        self.doc_personal = Document.objects.create(file=self.personal_file, uploaded_by=owner_user, title="Leave App")
        self.doc_policy = Document.objects.create(file=self.policy_file, uploaded_by=reg_user, title="Policy Doc")

    def _dispatch(self, user, file_obj, doc):
        self.client.login(username=user.username, password="Test1234!")
        return self.client.post(
            reverse("document_management:chain_apply_template", kwargs={"file_pk": file_obj.pk}),
            {"template_id": self.tmpl.pk, "document_id": doc.pk}
        )

    def test_owner_can_dispatch_personal_file(self):
        r = self._dispatch(self.owner.user, self.personal_file, self.doc_personal)
        from document_management.models import ApprovalChain
        self.assertTrue(ApprovalChain.objects.filter(document=self.doc_personal).exists())

    def test_non_owner_cannot_dispatch_personal_file(self):
        r = self._dispatch(self.other.user, self.personal_file, self.doc_personal)
        from document_management.models import ApprovalChain
        self.assertFalse(ApprovalChain.objects.filter(document=self.doc_personal).exists())

    def test_hod_can_dispatch_policy_file(self):
        r = self._dispatch(self.hod.user, self.policy_file, self.doc_policy)
        from document_management.models import ApprovalChain
        self.assertTrue(ApprovalChain.objects.filter(document=self.doc_policy).exists())

    def test_non_hod_cannot_dispatch_policy_file(self):
        r = self._dispatch(self.owner.user, self.policy_file, self.doc_policy)
        from document_management.models import ApprovalChain
        self.assertFalse(ApprovalChain.objects.filter(document=self.doc_policy).exists())

    def test_recall_revokes_approved_access(self):
        from document_management.models import FileAccessRequest
        from django.contrib.auth.models import Permission
        # Grant required permission
        perm = Permission.objects.filter(codename='view_file').first()
        if perm:
            self.registry.user.user_permissions.add(perm)
        # Move file to other staff so recall actually triggers
        self.personal_file.current_location = self.other
        self.personal_file.save()
        FileAccessRequest.objects.create(
            file=self.personal_file, requested_by=self.other.user,
            reason="Need access", access_type='read_write', status='approved'
        )
        self.client.login(username="reg_dp", password="Test1234!")
        self.client.post(reverse("document_management:file_recall", kwargs={"pk": self.personal_file.pk}))
        self.assertFalse(
            FileAccessRequest.objects.filter(file=self.personal_file, status='approved').exists()
        )
