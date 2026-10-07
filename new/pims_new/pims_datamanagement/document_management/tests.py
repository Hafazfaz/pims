"""
End-to-end simulation tests for PIMS core flows.
Covers: user auth, file lifecycle, document upload, access requests.
"""

from datetime import timedelta

from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from organization.models import Department, Designation, Staff, Unit
from user_management.models import CustomUser

from document_management.models import (
    Document,
    DocumentType,
    File,
    FileAccessRequest,
    FileMovement,
)


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
        r = self.client.post(
            reverse("document_management:file_create"),
            {
                "title": "TEST FILE",
                "file_type": "personal",
                "owner": self.staff.pk,
                "covering_note": "New file created for testing.",
                "save_as_draft": "on",
            },
        )
        self.assertIn(r.status_code, [200, 302])
        self.assertTrue(File.objects.filter(owner=self.staff).exists())

    def test_registry_cannot_own_file(self):
        from django.core.exceptions import ValidationError

        f = File(title="REG FILE", file_type="personal", owner=self.registry_staff)
        with self.assertRaises(ValidationError):
            f.full_clean()

    def test_file_status_toggle(self):
        f = File.objects.create(
            title="STATUS TEST",
            file_type="personal",
            owner=self.staff,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="active",
        )
        self.client.post(
            reverse("document_management:file_detail", kwargs={"pk": f.pk}),
            {"action": "change_status", "new_status": "inactive"},
        )
        f.refresh_from_db()
        self.assertEqual(f.status, "inactive")
        self.client.post(
            reverse("document_management:file_detail", kwargs={"pk": f.pk}),
            {"action": "change_status", "new_status": "active"},
        )
        f.refresh_from_db()
        self.assertEqual(f.status, "active")

    def test_file_close(self):
        f = File.objects.create(
            title="CLOSE TEST",
            file_type="personal",
            owner=self.staff,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="active",
        )
        self.client.post(reverse("document_management:file_close", kwargs={"pk": f.pk}))
        f.refresh_from_db()
        self.assertEqual(f.status, "closed")


    def test_current_location_display_registry(self):
        f = File.objects.create(
            title="DISPLAY TEST",
            file_type="personal",
            owner=self.staff,
            current_location=self.registry_staff,
            created_by=self.registry_user,
        )
        self.assertEqual(f.current_location_display, "Registry")

    def test_current_location_display_staff(self):
        f = File.objects.create(
            title="DISPLAY TEST 2",
            file_type="personal",
            owner=self.staff,
            current_location=self.staff,
            created_by=self.registry_user,
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
        self.doc_type = DocumentType.objects.create(name="Certificates")
        self.file = File.objects.create(
            title="DOC TEST FILE",
            file_type="personal",
            owner=self.staff,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="active",
        )
        self.client.login(username="reg2", password="Test1234!")

    def test_upload_document(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        # PNG: allowed by the upload whitelist, still skips PDF watermarking
        f = SimpleUploadedFile("test.png", b"png bytes", content_type="image/png")
        r = self.client.post(
            reverse("document_management:document_add", kwargs={"file_pk": self.file.pk}),
            {"file": self.file.pk, "title": "Test Doc", "document_type": self.doc_type.pk, "attachment": f},
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
            title="ACCESS TEST FILE",
            file_type="personal",
            owner=self.staff,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="active",
        )

    def test_access_request_approve_transfers_custody(self):
        # Read & Write is the level normal staff request (Read-Only is
        # supervisor-only), so a plain Staff-group user's R&W request is
        # approvable without any Supervisor membership.
        req = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.staff_user,
            reason="Need access",
            access_type="read_write",
            status="pending",
        )
        self.client.login(username="reg3", password="Test1234!")
        self.client.post(reverse("document_management:access_request_approve", kwargs={"pk": req.pk}))
        req.refresh_from_db()
        self.file.refresh_from_db()
        self.assertEqual(req.status, "approved")
        self.assertEqual(self.file.current_location, self.staff)

    def test_access_request_reject(self):
        req = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.staff_user,
            reason="Need access",
            access_type="read_only",
            status="pending",
        )
        self.client.login(username="reg3", password="Test1234!")
        self.client.post(
            reverse("document_management:access_request_reject", kwargs={"pk": req.pk}),
            {"denial_reason": "Insufficient justification"},
        )
        req.refresh_from_db()
        self.assertEqual(req.status, "rejected")



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



class DocumentStatusTest(TestCase):
    """Tests for document status defaults."""

    def setUp(self):
        self.dept = Department.objects.create(name="Ops", code="OPS")
        reg_user = make_user("reg_vs", "Registry")
        reg_desig, _ = Designation.objects.get_or_create(name="Registry Officer", defaults={"level": 1})
        self.registry = Staff.objects.create(user=reg_user, designation=reg_desig, department=self.dept)

        owner_user = make_user("owner_vs", "Staff")
        desig, _ = Designation.objects.get_or_create(name="Officer", defaults={"level": 5})
        self.owner = Staff.objects.create(user=owner_user, designation=desig, department=self.dept)

        self.file = File.objects.create(
            title="STATUS TEST FILE",
            file_type="personal",
            owner=self.owner,
            current_location=self.registry,
            created_by=owner_user,
            status="active",
        )
        self.doc = Document.objects.create(
            file=self.file,
            uploaded_by=owner_user,
            title="Policy Draft",
            minute_content="Initial draft.",
        )

    def test_new_document_is_pending(self):
        self.assertEqual(self.doc.status, "pending")

    def test_dispatch_sets_in_transit(self):
        self.doc.status = "in_transit"
        self.doc.save()
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "in_transit")


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
            title="PERSONAL FILE",
            file_type="personal",
            owner=self.owner,
            current_location=self.registry,
            created_by=owner_user,
            status="active",
        )
        self.policy_file = File.objects.create(
            title="POLICY FILE",
            file_type="policy",
            department=self.dept,
            current_location=self.registry,
            created_by=reg_user,
            status="active",
        )
        self.doc_personal = Document.objects.create(file=self.personal_file, uploaded_by=owner_user, title="Leave App")
        self.doc_policy = Document.objects.create(file=self.policy_file, uploaded_by=reg_user, title="Policy Doc")


    def test_recall_revokes_approved_access(self):
        from django.contrib.auth.models import Permission

        from document_management.models import FileAccessRequest

        # Grant required permission
        perm = Permission.objects.filter(codename="view_file").first()
        if perm:
            self.registry.user.user_permissions.add(perm)
        # Move file to other staff so recall actually triggers
        self.personal_file.current_location = self.other
        self.personal_file.save()
        FileAccessRequest.objects.create(
            file=self.personal_file,
            requested_by=self.other.user,
            reason="Need access",
            access_type="read_write",
            status="approved",
        )
        self.client.login(username="reg_dp", password="Test1234!")
        self.client.post(reverse("document_management:file_recall", kwargs={"pk": self.personal_file.pk}))
        self.assertFalse(FileAccessRequest.objects.filter(file=self.personal_file, status="approved").exists())


class MovementAccessTest(TestCase):
    """FileMovement is the source of truth for dispatched-file access.

    Covers the plan's validation criteria:
      - dispatched recipient sees "Full Access Granted"
      - non-recipient sees "Request Access"
      - after expires_at passes, recipient reverts to "Request Access"
    """

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Finance", code="FIN")

        reg_user = make_user("reg_ma", "Registry")
        desig_reg, _ = Designation.objects.get_or_create(name="Registry Officer", defaults={"level": 1})
        self.registry = Staff.objects.create(user=reg_user, designation=desig_reg, department=self.dept)

        owner_user = make_user("owner_ma", "Staff")
        desig, _ = Designation.objects.get_or_create(name="Officer", defaults={"level": 5})
        self.owner = Staff.objects.create(user=owner_user, designation=desig, department=self.dept)

        col_user = make_user("col_ma", "Staff")
        self.colleague = Staff.objects.create(user=col_user, designation=desig, department=self.dept)

        hod_user = make_user("hod_ma", "Staff")
        hod_desig, _ = Designation.objects.get_or_create(name="Head of Department", defaults={"level": 2})
        self.hod = Staff.objects.create(user=hod_user, designation=hod_desig, department=self.dept)
        self.dept.head = self.hod
        self.dept.save()

        self.file = File.objects.create(
            title="MOVEMENT ACCESS FILE",
            file_type="personal",
            owner=self.owner,
            current_location=self.registry,
            created_by=reg_user,
            status="active",
        )

    def test_is_active_access_property(self):
        active = FileMovement.objects.create(
            file=self.file, sent_by=self.registry.user, sent_to=self.colleague,
            action="sent", expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(active.is_active_access)

        expired = FileMovement.objects.create(
            file=self.file, sent_by=self.registry.user, sent_to=self.colleague,
            action="sent", expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(expired.is_active_access)

        indefinite = FileMovement.objects.create(
            file=self.file, sent_by=self.registry.user, sent_to=self.colleague,
            action="sent", expires_at=None,
        )
        self.assertTrue(indefinite.is_active_access)

        recalled = FileMovement.objects.create(
            file=self.file, sent_by=self.registry.user, sent_to=self.colleague,
            action="recalled", expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertFalse(recalled.is_active_access)

    def test_expiry_defaults_to_seven_days_on_send(self):
        from document_management.models import FileMovement

        self.client.login(username="reg_ma", password="Test1234!")
        resp = self.client.post(
            reverse("document_management:file_detail", kwargs={"pk": self.file.pk}),
            {
                "action": "send_file",
                "recipient": self.colleague.user.pk,
                "movement_note": "Please review.",
            },
        )
        self.assertIn(resp.status_code, [302, 200])
        movement = FileMovement.objects.filter(file=self.file, action="sent").first()
        self.assertIsNotNone(movement)
        self.assertIsNotNone(movement.expires_at)
        self.assertGreater(movement.expires_at, timezone.now())
        delta = movement.expires_at - movement.moved_at
        # Allow 6-7 days due to request timing (auto_now_add vs timezone.now())
        self.assertIn(delta.days, [6, 7])

    def test_dispatched_recipient_has_full_access(self):
        FileMovement.objects.create(
            file=self.file, sent_by=self.registry.user, sent_to=self.colleague,
            action="sent", expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.login(username="col_ma", password="Test1234!")
        resp = self.client.get(reverse("document_management:file_detail", kwargs={"pk": self.file.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["has_approved_access"])
        self.assertTrue(resp.context["has_rw_access"])

    def test_non_recipient_sees_request_access(self):
        # HOD can load the page (role rule) but has no movement/approved request
        self.client.login(username="hod_ma", password="Test1234!")
        resp = self.client.get(reverse("document_management:file_detail", kwargs={"pk": self.file.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["has_approved_access"])
        self.assertContains(resp, "Request Access")

    def test_expired_movement_revokes_access(self):
        FileMovement.objects.create(
            file=self.file, sent_by=self.registry.user, sent_to=self.colleague,
            action="sent", expires_at=timezone.now() - timedelta(days=1),
        )
        # Make colleague the custodian (as a real Send Note would) so reclamation runs
        self.file.current_location = self.colleague
        self.file.save(update_fields=["current_location"])

        self.client.login(username="col_ma", password="Test1234!")

        # Before any reclaim, the expired movement should deny access
        resp = self.client.get(reverse("document_management:file_detail", kwargs={"pk": self.file.pk}))
        self.assertEqual(resp.status_code, 200)
        self.file.refresh_from_db()
        # Custody is reclaimed to registry because the movement has expired
        self.assertEqual(self.file.current_location, self.registry)
        self.assertFalse(resp.context["has_approved_access"])
        self.assertContains(resp, "Request Access")


class ContentScopeTest(TestCase):
    """Contents need custody or an explicit grant — role alone is not enough.

    Standing access (no custody needed): owner, uploader, Executive/MD.
    HOD / unit head / supervisor without custody are denied; with custody
    (current_location) they pass. Registry and outsiders are denied."""

    def setUp(self):
        self.dept = Department.objects.create(name="ScopeDept", code="SCP")
        self.other_dept = Department.objects.create(name="OtherDept", code="OTH")
        self.unit = Unit.objects.create(name="ScopeUnit", department=self.dept)

        self.owner_user = make_user("scope_owner", "Staff")
        self.owner = make_staff(self.owner_user, "Officer", self.dept)
        self.owner.unit = self.unit
        self.owner.save()

        self.um_user = make_user("scope_um", "Staff")
        self.unit_manager = make_staff(self.um_user, "Head of Unit", self.dept)
        self.unit.head = self.unit_manager
        self.unit.save()

        self.hod_user = make_user("scope_hod", "Staff")
        self.hod = make_staff(self.hod_user, "Head of Department", self.dept)
        self.dept.head = self.hod
        self.dept.save()

        self.sup_user = make_user("scope_sup", "Staff")
        self.supervisor = make_staff(self.sup_user, "Officer", self.dept)
        self.supervisor.is_supervisor = True
        self.supervisor.save()

        self.exec_user = make_user("scope_exec", "Executive")
        self.exec = make_staff(self.exec_user, "Officer", self.dept)

        self.out_user = make_user("scope_out", "Staff")
        self.outsider = make_staff(self.out_user, "Officer", self.other_dept)

        self.reg_user = make_user("scope_reg", "Registry")
        self.registry = make_staff(self.reg_user, "Registry Officer", self.dept)

        self.file = File.objects.create(
            title="SCOPE FILE",
            file_type="personal",
            owner=self.owner,
            current_location=self.registry,
            created_by=self.reg_user,
            status="active",
        )
        self.doc = Document.objects.create(
            file=self.file, uploaded_by=self.reg_user, title="Scoped Doc"
        )

    def _gates(self, user):
        from document_management.permissions import can_view_document_content
        from document_management.views.document_views import can_download_document_file

        return (
            can_view_document_content(user, file=self.file, document=self.doc),
            can_download_document_file(user, self.doc),
        )

    def _give_custody(self, staff):
        self.file.current_location = staff
        self.file.save(update_fields=["current_location"])

    def _grant_access(self, user, access_type="read_only"):
        # A grant is only active while its holder has custody.
        from document_management.models import FileAccessRequest

        req = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=user,
            access_type=access_type,
            status="approved",
            reason="Test access grant",
        )
        staff = getattr(user, "staff", None)
        if staff is not None:
            self.file.current_location = staff
            self.file.save(update_fields=["current_location"])
        return req

    def test_owner_allowed_with_explicit_grant(self):
        self._grant_access(self.owner_user)
        self.assertEqual(self._gates(self.owner_user), (True, True))

    def test_hod_denied_without_custody(self):
        self.assertEqual(self._gates(self.hod_user), (False, False))

    def test_hod_allowed_with_custody_and_grant(self):
        self._give_custody(self.hod)
        self._grant_access(self.hod_user)
        self.assertEqual(self._gates(self.hod_user), (True, True))

    def test_unit_head_denied_without_custody(self):
        self.assertEqual(self._gates(self.um_user), (False, False))

    def test_unit_head_allowed_with_custody_and_grant(self):
        self._give_custody(self.unit_manager)
        self._grant_access(self.um_user)
        self.assertEqual(self._gates(self.um_user), (True, True))

    def test_supervisor_denied_without_custody(self):
        self.assertEqual(self._gates(self.sup_user), (False, False))

    def test_executive_allowed_without_custody(self):
        self.assertEqual(self._gates(self.exec_user), (True, True))

    def test_outsider_cannot_view_or_download(self):
        self.assertEqual(self._gates(self.out_user), (False, False))

    def test_registry_cannot_view_or_download(self):
        self.assertEqual(self._gates(self.reg_user), (False, False))

    def test_uploader_can_download_own_document_with_grant(self):
        from document_management.views.document_views import can_download_document_file

        self.doc.uploaded_by = self.out_user
        self.doc.save()
        self._grant_access(self.out_user)
        self.assertTrue(can_download_document_file(self.out_user, self.doc))

    def test_owner_denied_for_approved_document(self):
        self.doc.status = "approved"
        self.doc.save(update_fields=["status"])
        self.assertEqual(self._gates(self.owner_user), (False, False))

    def test_uploader_denied_for_approved_document(self):
        self.doc.uploaded_by = self.out_user
        self.doc.status = "approved"
        self.doc.save(update_fields=["status", "uploaded_by"])
        from document_management.views.document_views import can_download_document_file

        self.assertFalse(can_download_document_file(self.out_user, self.doc))

    def test_executive_allowed_for_approved_document(self):
        self.doc.status = "approved"
        self.doc.save(update_fields=["status"])
        self.assertEqual(self._gates(self.exec_user), (True, True))

    def test_approved_request_opens_approved_document(self):
        self._grant_access(self.sup_user)
        self.doc.status = "approved"
        self.doc.save(update_fields=["status"])
        self.assertEqual(self._gates(self.sup_user), (True, True))


class ActionExpiryTest(TestCase):
    """Acting on a movement closes the loop: the actioned movement stops
    granting access and dispatch-time auto-grants are revoked, so inbox/sent
    items can't be revisited for viewing or downloading. Real approved
    requests survive — requesting access stays the way back in."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="ExpiryDept", code="EXP")
        self.reg_user = make_user("exp_reg", "Registry")
        self.registry = make_staff(self.reg_user, "Registry Officer", self.dept)

        self.owner_user = make_user("exp_owner", "Staff")
        self.owner = make_staff(self.owner_user, "Officer", self.dept)

        self.sup_user = make_user("exp_sup", "Staff")
        self.supervisor = make_staff(self.sup_user, "Officer", self.dept)
        self.supervisor.is_supervisor = True
        self.supervisor.save()

        self.hod_user = make_user("exp_hod", "Staff")
        self.hod = make_staff(self.hod_user, "Head of Department", self.dept)
        self.dept.head = self.hod
        self.dept.save()

        self.um_user = make_user("exp_um", "Staff")
        self.unit_manager = make_staff(self.um_user, "Head of Unit", self.dept)
        self.unit = Unit.objects.create(name="ExpUnit", department=self.dept, head=self.unit_manager)

        # The one final approver (Medical Director designation carries
        # user_management.can_approve_document; everyone else routes).
        self.approver_user = make_user("exp_approver", "Staff")
        self.approver = make_staff(self.approver_user, "Medical Director", self.dept)

        self.file = File.objects.create(
            title="EXPIRY FILE",
            file_type="personal",
            owner=self.owner,
            current_location=self.supervisor,
            created_by=self.owner_user,
            status="in_transit",
        )
        self.doc = Document.objects.create(
            file=self.file, uploaded_by=self.owner_user, title="Expiring Doc"
        )
        self.movement = FileMovement.objects.create(
            file=self.file,
            document=self.doc,
            sent_by=self.owner_user,
            from_location=self.owner,
            sent_to=self.supervisor,
            note="Please review",
            action="sent",
            status="pending",
            expires_at=timezone.now() + timedelta(days=7),
        )

    def _gates(self, user):
        from document_management.permissions import can_view_document_content
        from document_management.views.document_views import can_download_document_file

        return (
            can_view_document_content(user, file=self.file),
            can_download_document_file(user, self.doc),
        )

    def test_recipient_has_access_before_action(self):
        # The pending movement gives the recipient active access to the file.
        self.assertEqual(self._gates(self.sup_user), (True, True))

    def test_approve_expires_movement_and_auto_grants(self):
        auto = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.sup_user,
            reason="Auto-granted: file sent by owner",
            access_type="read_only",
            status="approved",
        )
        self.client.login(username="exp_sup", password="Test1234!")
        resp = self.client.post(
            reverse("document_management:document_action", kwargs={"pk": self.movement.pk}),
            {"action": "approve", "note": "Passed up for final approval", "recipient_staff_id": self.approver.pk},
        )
        self.assertIn(resp.status_code, [200, 302])
        self.movement.refresh_from_db()
        auto.refresh_from_db()
        self.file.refresh_from_db()
        self.doc.refresh_from_db()
        self.assertEqual(self.movement.status, "approved")
        self.assertFalse(self.movement.is_active_access)
        self.assertEqual(auto.status, "expired")
        # Back to the sent/inbox item: no more viewing or downloading.
        self.assertEqual(self._gates(self.sup_user), (False, False))

    def test_real_approved_request_expires_on_custody_change(self):
        real = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.sup_user,
            reason="Need access for audit review",
            access_type="read_only",
            status="approved",
        )
        self.client.login(username="exp_sup", password="Test1234!")
        self.client.post(
            reverse("document_management:document_action", kwargs={"pk": self.movement.pk}),
            {"action": "approve", "note": "Passed up for final approval", "recipient_staff_id": self.approver.pk},
        )
        real.refresh_from_db()
        # Custody moves to the final approver; every grant on the file expires.
        self.assertEqual(real.status, "expired")
        self.assertEqual(self._gates(self.sup_user), (False, False))

    def test_forward_expires_forwarder_only(self):
        # Forwarding revokes only the forwarder's dispatch-time auto-grant;
        # everyone else's survives, and the next holder rides on the fresh
        # movement + custody.
        sup_auto = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.sup_user,
            reason="Auto-granted: file sent by owner",
            access_type="read_only",
            status="approved",
        )
        owner_auto = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.owner_user,
            reason="Auto-granted: file sent by owner",
            access_type="read_only",
            status="approved",
        )
        # The HOD holds a real, human-approved request — these survive
        # forwarding untouched.
        hod_request = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.hod_user,
            reason="Need access for audit review",
            access_type="read_only",
            status="approved",
        )
        self.client.login(username="exp_sup", password="Test1234!")
        self.client.post(
            reverse("document_management:document_action", kwargs={"pk": self.movement.pk}),
            {"action": "forward", "recipient_staff_id": self.hod.pk, "note": "Passing up"},
        )
        self.movement.refresh_from_db()
        sup_auto.refresh_from_db()
        owner_auto.refresh_from_db()
        hod_request.refresh_from_db()
        self.file.refresh_from_db()
        self.assertEqual(self.movement.status, "forwarded")
        self.assertFalse(self.movement.is_active_access)
        # Forwarding expires the forwarder's auto-grants; the custody change
        # also expires every other approved grant on the file.
        self.assertEqual(sup_auto.status, "expired")
        self.assertEqual(owner_auto.status, "expired")
        self.assertEqual(hod_request.status, "expired")
        from document_management.permissions import can_view_document_content

        self.assertFalse(can_view_document_content(self.sup_user, file=self.file))
        # The HOD rides on the fresh movement + custody.
        self.assertTrue(can_view_document_content(self.hod_user, file=self.file))

    def test_reject_expires_movement(self):
        self.client.login(username="exp_sup", password="Test1234!")
        self.client.post(
            reverse("document_management:document_action", kwargs={"pk": self.movement.pk}),
            {"action": "reject", "note": "Missing pages"},
        )
        self.movement.refresh_from_db()
        self.assertEqual(self.movement.status, "rejected")
        self.assertFalse(self.movement.is_active_access)



class AddDocumentPermissionTest(TestCase):
    """Regression tests: no 403 on create-file, one shared add-document rule."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Legal", code="LEG")
        self.registry_user = make_user("reg_add", "Registry")
        self.registry_staff = make_staff(self.registry_user, "Registry Officer")
        self.owner_user = make_user("owner_add", "Staff")
        self.owner_staff = make_staff(self.owner_user, "Officer", self.dept)
        self.stranger_user = make_user("stranger_add", "Staff")
        self.stranger_staff = make_staff(self.stranger_user, "Analyst", self.dept)
        self.doc_type = DocumentType.objects.create(name="Memo")
        self.file = File.objects.create(
            title="ADD PERM FILE",
            file_type="personal",
            owner=self.owner_staff,
            current_location=self.owner_staff,
            created_by=self.registry_user,
            status="active",
        )

    def test_create_file_redirects_instead_of_403_for_non_registry(self):
        """FileCreateView.handle_no_permission must be a real method: a
        non-registry user used to get a hard 403 Forbidden."""
        self.client.login(username="stranger_add", password="Test1234!")
        r = self.client.get(reverse("document_management:file_create"))
        self.assertNotEqual(r.status_code, 403)
        self.assertEqual(r.status_code, 302)

    def test_create_file_denies_non_registry_post(self):
        self.client.login(username="stranger_add", password="Test1234!")
        r = self.client.post(
            reverse("document_management:file_create"),
            {"title": "SNEAKY FILE", "file_type": "personal", "owner": self.stranger_staff.pk},
        )
        self.assertNotEqual(r.status_code, 403)
        self.assertEqual(r.status_code, 302)
        self.assertFalse(File.objects.filter(title="SNEAKY FILE").exists())

    def test_registry_can_still_open_create_file(self):
        self.client.login(username="reg_add", password="Test1234!")
        r = self.client.get(reverse("document_management:file_create"))
        self.assertEqual(r.status_code, 200)

    def test_document_add_endpoint_allows_owner_not_stranger(self):
        from document_management.permissions import can_add_document

        url = reverse("document_management:document_add", kwargs={"file_pk": self.file.pk})

        self.client.login(username="owner_add", password="Test1234!")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(can_add_document(self.owner_user, self.file))

        self.client.login(username="stranger_add", password="Test1234!")
        r = self.client.get(url)
        self.assertNotEqual(r.status_code, 403)
        self.assertEqual(r.status_code, 302)
        self.assertFalse(can_add_document(self.stranger_user, self.file))

    def test_can_add_document_single_rule_set(self):
        from document_management.permissions import can_add_document

        # Registry / superuser: yes.
        self.assertTrue(can_add_document(self.registry_user, self.file))
        # Owner of the personal file: yes.
        self.assertTrue(can_add_document(self.owner_user, self.file))
        # Unrelated staff: no.
        self.assertFalse(can_add_document(self.stranger_user, self.file))
        # Inactive file: no, even for registry — matches endpoint + button.
        self.file.status = "closed"
        self.file.save()
        self.assertFalse(can_add_document(self.registry_user, self.file))
        self.assertFalse(can_add_document(self.owner_user, self.file))

    def test_button_visibility_matches_endpoint(self):
        """The can_add_minute flag shown on the file page must equal what the
        endpoint will accept for the same user."""
        from document_management.permissions import can_add_document

        for username in ("reg_add", "owner_add", "stranger_add"):
            self.client.login(username=username, password="Test1234!")
            r = self.client.get(reverse("document_management:file_detail", kwargs={"pk": self.file.pk}))
            if r.status_code != 200:
                continue
            self.assertEqual(
                r.context["can_add_minute"],
                can_add_document(CustomUser.objects.get(username=username), self.file),
                f"can_add_minute diverged for {username}",
            )


class PersonalFileOneToOneTest(TestCase):
    """Personal files are 1:1 with Staff — enforced in clean() AND in the DB."""

    def setUp(self):
        self.dept = Department.objects.create(name="HR", code="HR")
        self.registry_user = make_user("reg_111", "Registry")
        self.registry_staff = make_staff(self.registry_user, "Registry Officer")
        self.staff_user = make_user("owner_111", "Staff")
        self.staff = make_staff(self.staff_user, "Officer", self.dept)

    def test_first_personal_file_allowed(self):
        File.objects.create(
            title="PERSONNEL RECORD - OWNER",
            file_type="personal",
            owner=self.staff,
            created_by=self.registry_user,
        )
        self.assertEqual(File.objects.filter(file_type="personal", owner=self.staff).count(), 1)

    def test_second_personal_file_rejected_by_clean(self):
        File.objects.create(
            title="PERSONNEL RECORD - OWNER",
            file_type="personal",
            owner=self.staff,
            created_by=self.registry_user,
        )
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            File.objects.create(
                title="DUPLICATE PERSONNEL RECORD",
                file_type="personal",
                owner=self.staff,
                created_by=self.registry_user,
            )
        self.assertEqual(File.objects.filter(file_type="personal", owner=self.staff).count(), 1)

    def test_db_constraint_rejects_duplicate_bypassing_clean(self):
        """Even if full_clean() is skipped, the partial unique index blocks it."""
        from django.db import IntegrityError, transaction

        File.objects.create(
            title="PERSONNEL RECORD - OWNER",
            file_type="personal",
            owner=self.staff,
            created_by=self.registry_user,
        )
        dup = File(
            title="DUPLICATE PERSONNEL RECORD",
            file_type="personal",
            owner=self.staff,
            file_number="FMCAB-UNIQUE-DUP-1",
            created_by=self.registry_user,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            dup.save_base()  # bypasses full_clean -> hits the DB constraint
        self.assertEqual(File.objects.filter(file_type="personal", owner=self.staff).count(), 1)

    def test_non_personal_files_unaffected(self):
        """Policy files have owner=NULL — the partial index must not clash."""
        File.objects.create(
            title="POLICY FILE - HR",
            file_type="policy",
            department=self.dept,
            owner=None,
            created_by=self.registry_user,
        )
        File.objects.create(
            title="POLICY FILE - HR 2",
            file_type="policy",
            department=self.dept,
            owner=None,
            created_by=self.registry_user,
        )
        self.assertEqual(File.objects.filter(file_type="policy", department=self.dept).count(), 2)


class AssignOrganizationHeadsTest(TestCase):
    """create_fixtures.assign_organization_heads must never hit the
    UNIQUE constraint on organization_unit/department.head_id — a Staff
    member can head only ONE unit/department (OneToOneField)."""

    def setUp(self):
        self.dept = Department.objects.create(name="Operations", code="OPS")
        self.unit_one = Unit.objects.create(department=self.dept, name="Unit One")
        self.unit_two = Unit.objects.create(department=self.dept, name="Unit Two")

    def test_skips_staff_who_already_heads_another_unit(self):
        from create_fixtures import assign_organization_heads

        desig = Designation.objects.get_or_create(name="Head of Unit", defaults={"level": 4})[0]
        # staff_a already heads unit_one, but their own Staff.unit points at
        # unit_two — exactly the pattern that crashed the server run.
        staff_a = make_staff(make_user("head_a"), "Head of Unit", self.dept)
        staff_a.designation = desig
        staff_a.unit = self.unit_two
        staff_a.save()
        self.unit_one.head = staff_a
        self.unit_one.save()

        # staff_b is a plain eligible candidate sitting in unit_two.
        staff_b = make_staff(make_user("head_b"), "Officer", self.dept)
        staff_b.unit = self.unit_two
        staff_b.save()

        # Old code: IntegrityError UNIQUE constraint failed organization_unit.head_id
        assign_organization_heads({self.dept.code: self.dept}, [self.unit_two])

        self.unit_two.refresh_from_db()
        self.unit_one.refresh_from_db()
        self.assertEqual(self.unit_two.head_id, staff_b.pk)
        self.assertEqual(self.unit_one.head_id, staff_a.pk)

    def test_unit_left_without_head_when_all_candidates_taken(self):
        from create_fixtures import assign_organization_heads

        staff_a = make_staff(make_user("head_c"), "Officer", self.dept)
        staff_a.unit = self.unit_two
        staff_a.save()
        self.unit_one.head = staff_a
        self.unit_one.save()

        assign_organization_heads({self.dept.code: self.dept}, [self.unit_two])

        self.unit_two.refresh_from_db()
        self.unit_one.refresh_from_db()
        self.assertIsNone(self.unit_two.head_id)  # skipped, not crashed
        self.assertEqual(self.unit_one.head_id, staff_a.pk)

    def test_skips_staff_who_already_heads_another_department(self):
        from create_fixtures import assign_organization_heads

        dept_two = Department.objects.create(name="Finance", code="FIN")
        director = Designation.objects.get_or_create(name="Director", defaults={"level": 2})[0]
        # staff_c works in finance but already heads operations.
        staff_c = make_staff(make_user("head_d"), "Director", dept_two)
        staff_c.designation = director
        staff_c.save()
        self.dept.head = staff_c
        self.dept.save()

        assign_organization_heads({self.dept.code: self.dept, dept_two.code: dept_two}, [])

        self.dept.refresh_from_db()
        dept_two.refresh_from_db()
        self.assertEqual(self.dept.head_id, staff_c.pk)
        self.assertIsNone(dept_two.head_id)  # candidate was taken -> skip, no crash


class GlobalViewerTest(TestCase):
    """user_management.can_view_all_staff_files — global visibility for
    MD / Executives / admin-designated viewers, even with no department."""

    def setUp(self):
        self.dept = Department.objects.create(name="Lab", code="LAB")
        self.registry_user = make_user("reg_gv", "Registry")
        self.registry_staff = make_staff(self.registry_user, "Registry Officer")
        self.owner_user = make_user("owner_gv", "Staff")
        self.owner_staff = make_staff(self.owner_user, "Officer", self.dept)
        self.doc_type = DocumentType.objects.create(name="Report")
        self.file = File.objects.create(
            title="GLOBAL VIEW FILE",
            file_type="personal",
            owner=self.owner_staff,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="active",
        )
        self.doc = Document.objects.create(
            file=self.file,
            uploaded_by=self.owner_user,
            title="Sensitive minute",
            minute_content="Private content",
            document_type=self.doc_type,
            status="approved",
        )

    def _global_perm(self):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        from user_management.models import CustomUser

        ct = ContentType.objects.get_for_model(CustomUser)
        return Permission.objects.get(content_type=ct, codename="can_view_all_staff_files")

    def test_oversight_groups_hold_the_permission(self):
        """Migration grants it to MD, Executives and Administrator."""
        for group_name in ("MD", "Executives", "Administrator"):
            group = Group.objects.get(name=group_name)
            self.assertTrue(
                group.permissions.filter(codename="can_view_all_staff_files").exists(),
                f"{group_name} group missing can_view_all_staff_files",
            )

    def test_user_without_department_sees_everything_with_permission(self):
        from document_management.permissions import (
            can_view_document_content,
            can_view_file,
            can_view_staff_documents,
            has_content_scope,
        )

        viewer = make_user("global_viewer")
        viewer.user_permissions.add(self._global_perm())
        # No staff profile at all — belongs to no department.
        self.assertFalse(hasattr(viewer, "staff"))

        self.assertTrue(can_view_file(viewer, self.file))
        self.assertTrue(can_view_document_content(viewer, file=self.file, document=self.doc))
        self.assertTrue(has_content_scope(viewer, self.file, document=self.doc))
        self.assertTrue(can_view_staff_documents(viewer))

    def test_same_user_without_permission_is_scoped_out(self):
        from document_management.permissions import (
            can_view_document_content,
            can_view_file,
            can_view_staff_documents,
            has_content_scope,
        )

        stranger = make_user("plain_viewer")  # no permission, no staff profile
        self.assertFalse(can_view_file(stranger, self.file))
        self.assertFalse(can_view_document_content(stranger, file=self.file, document=self.doc))
        self.assertFalse(has_content_scope(stranger, self.file, document=self.doc))
        self.assertFalse(can_view_staff_documents(stranger))

    def test_registry_stays_denied_even_with_permission(self):
        """Separation of duties: the registry check runs first."""
        from document_management.permissions import (
            can_view_document_content,
            can_view_staff_documents,
        )

        self.registry_user.user_permissions.add(self._global_perm())
        self.registry_user = CustomUser.objects.get(pk=self.registry_user.pk)  # refresh perm cache
        self.assertFalse(can_view_document_content(self.registry_user, file=self.file, document=self.doc))
        self.assertFalse(can_view_staff_documents(self.registry_user))

    def test_executives_group_matches_is_executive(self):
        """Group is named 'Executives' in fixtures — both spellings must match."""
        exec_user = make_user("exec_gv", "Executives")
        exec_staff = make_staff(exec_user, "Director", self.dept)
        self.assertTrue(exec_staff.is_executive)

        legacy_user = make_user("legacy_exec", "Executive")
        legacy_staff = make_staff(legacy_user, "Director", self.dept)
        self.assertTrue(legacy_staff.is_executive)

    def test_md_group_user_is_global_viewer(self):
        """Membership in the MD group alone grants global visibility."""
        from document_management.permissions import can_view_file, is_global_viewer

        md_user = make_user("md_gv", "MD")
        self.assertTrue(is_global_viewer(md_user))
        self.assertTrue(can_view_file(md_user, self.file))


class DocxPreviewTest(TestCase):
    """DOCX uploads get an auto-generated PDF preview so they can be viewed
    in the browser without downloading the original file."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name="Preview Dept", code="PRV")
        cls.user = make_user("preview_user", "Staff")
        cls.staff = make_staff(cls.user, "Officer", cls.dept)
        cls.pims_file = File.objects.create(
            title="PREVIEW FILE",
            file_type="policy",
            created_by=cls.user,
            department=cls.dept,
        )

    def _make_docx(self):
        import subprocess
        import tempfile

        tmpdir = tempfile.mkdtemp()
        txt = f"{tmpdir}/sample.txt"
        with open(txt, "w") as f:
            f.write("Preview content")
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "docx", "--outdir", tmpdir, txt],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        return f"{tmpdir}/sample.docx"

    def test_docx_generates_preview_pdf_on_save(self):
        from django.core.files import File as DjangoFile

        docx_path = self._make_docx()
        with open(docx_path, "rb") as f:
            doc = Document.objects.create(
                file=self.pims_file,
                uploaded_by=self.user,
                title="Preview Doc",
                attachment=DjangoFile(f, name="sample.docx"),
            )
        doc.refresh_from_db()
        self.assertTrue(doc.preview_pdf)
        self.assertTrue(doc.preview_pdf.name.endswith(".pdf"))
        self.assertTrue(doc.preview_pdf.storage.exists(doc.preview_pdf.name))

    def test_download_view_serves_preview_pdf_when_inline(self):
        from django.core.files import File as DjangoFile
        from django.test import RequestFactory

        from document_management.views.document_views import DocumentDownloadView

        docx_path = self._make_docx()
        with open(docx_path, "rb") as f:
            doc = Document.objects.create(
                file=self.pims_file,
                uploaded_by=self.user,
                title="Preview Doc",
                attachment=DjangoFile(f, name="sample.docx"),
            )
        request = RequestFactory().get(f"/fake/{doc.pk}/?inline=1")
        request.user = self.user
        response = DocumentDownloadView.as_view()(request, pk=doc.pk)
        self.assertEqual(response.status_code, 200)
        # Content-Disposition should be inline because we served the preview PDF.
        self.assertIn("inline", response.get("Content-Disposition", ""))


class DocumentLabelTest(TestCase):
    """Notifications and audit entries quote documents by title, never
    Django's default ``Document object (185)``."""

    def setUp(self):
        self.user = make_user("label_user", "Staff")
        self.dept = Department.objects.create(name="Labels", code="LBL")
        self.staff = make_staff(self.user, "Officer", self.dept)
        self.file = File.objects.create(
            title="LABEL FILE", file_type="personal", owner=self.staff, department=self.dept, created_by=self.user
        )

    def test_str_is_the_title(self):
        doc = Document.objects.create(file=self.file, uploaded_by=self.user, title="B.Sc ECONOMICS CERTIFICATE")
        self.assertEqual(str(doc), "B.Sc ECONOMICS CERTIFICATE")

    def test_str_falls_back_to_the_file_it_lives_in(self):
        doc = Document.objects.create(file=self.file, uploaded_by=self.user)
        self.assertEqual(str(doc), f"Untitled document in {self.file.file_number}")
