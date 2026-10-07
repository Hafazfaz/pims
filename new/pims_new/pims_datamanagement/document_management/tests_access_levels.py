"""
Tests for the access-level restriction: Read-Write is the only level offered
to normal staff, while Read-Only remains reserved for supervisor roles.
"""
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from organization.models import Department, Designation, Staff
from user_management.models import CustomUser

from document_management.models import File, FileAccessRequest


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


class AccessLevelPermissionTest(TestCase):
    """Group-level permission matrix for Read-Only vs Read & Write."""

    def test_staff_group_has_both_access_levels(self):
        perms = set(
            Group.objects.get(name="Staff").permissions.values_list("codename", flat=True)
        )
        self.assertIn("can_request_file_access", perms)
        self.assertIn("can_request_file_access_rw", perms)

    def test_supervisor_group_has_both_levels(self):
        perms = set(
            Group.objects.get(name="Supervisor").permissions.values_list("codename", flat=True)
        )
        self.assertIn("can_request_file_access_rw", perms)
        self.assertIn("can_request_file_access", perms)

    def test_staff_user_effective_permissions(self):
        user = make_user("perm_staff", "Staff")
        self.assertTrue(user.has_perm("user_management.can_request_file_access"))
        self.assertTrue(user.has_perm("user_management.can_request_file_access_rw"))


class AccessRequestLevelTest(TestCase):
    """End-to-end request + approval rules for each access level."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Legal", code="LEG")

        self.reg_user = make_user("reg_lvl", "Registry")
        self.registry = make_staff(self.reg_user, "Registry Officer", self.dept)

        self.staff_user = make_user("staff_lvl", "Staff")
        self.staff = make_staff(self.staff_user, "Officer", self.dept)

        self.sup_user = make_user("sup_lvl", "Staff")
        self.supervisor = make_staff(self.sup_user, "Officer", self.dept)
        self.supervisor.is_supervisor = True
        self.supervisor.save()

        self.file = File.objects.create(
            title="ACCESS LEVEL FILE",
            file_type="policy",
            owner=self.staff,
            department=self.dept,
            current_location=self.registry,
            created_by=self.reg_user,
            status="active",
        )
        # Supervisors only see files they own/custody, so their own file is
        # needed for the view-level assertions.
        self.sup_file = File.objects.create(
            title="SUPERVISOR ACCESS FILE",
            file_type="policy",
            owner=self.supervisor,
            department=self.dept,
            current_location=self.registry,
            created_by=self.reg_user,
            status="active",
        )

    def _post_request(self, user, access_type=None, password="Test1234!", file_obj=None):
        file_obj = file_obj or self.file
        self.client.login(username=user.username, password=password)
        payload = {"action": "request_access", "reason": "Need access for review"}
        if access_type is not None:
            payload["access_type"] = access_type
        return self.client.post(
            reverse("document_management:file_detail", kwargs={"pk": file_obj.pk}),
            payload,
        )

    def test_staff_cannot_request_read_only(self):
        self._post_request(self.staff_user, "read_only")

        self.assertFalse(FileAccessRequest.objects.filter(requested_by=self.staff_user).exists())

    def test_staff_can_request_read_write(self):
        self._post_request(self.staff_user, "read_write")

        req = FileAccessRequest.objects.get(requested_by=self.staff_user)
        self.assertEqual(req.access_type, "read_write")

    def test_staff_default_is_read_write_when_field_missing(self):
        self._post_request(self.staff_user, None)

        req = FileAccessRequest.objects.get(requested_by=self.staff_user)
        self.assertEqual(req.access_type, "read_write")

    def test_supervisor_can_request_read_only(self):
        self._post_request(self.sup_user, "read_only", file_obj=self.sup_file)

        req = FileAccessRequest.objects.get(requested_by=self.sup_user)
        self.assertEqual(req.access_type, "read_only")

    def test_supervisor_can_request_read_write(self):
        self._post_request(self.sup_user, "read_write", file_obj=self.sup_file)

        req = FileAccessRequest.objects.get(requested_by=self.sup_user)
        self.assertEqual(req.access_type, "read_write")

    def test_context_hides_read_only_from_staff(self):
        self.client.login(username="staff_lvl", password="Test1234!")
        resp = self.client.get(
            reverse("document_management:file_detail", kwargs={"pk": self.file.pk})
        )

        self.assertFalse(resp.context["can_request_ro_access"])
        self.assertTrue(resp.context["can_request_rw_access"])
        self.assertTrue(resp.context["can_request_access"])

    def test_context_shows_both_levels_to_supervisor(self):
        self.client.login(username="sup_lvl", password="Test1234!")
        resp = self.client.get(
            reverse("document_management:file_detail", kwargs={"pk": self.sup_file.pk})
        )

        self.assertTrue(resp.context["can_request_ro_access"])
        self.assertTrue(resp.context["can_request_rw_access"])

    def test_staff_template_has_no_read_only_option(self):
        self.client.login(username="staff_lvl", password="Test1234!")
        resp = self.client.get(
            reverse("document_management:file_detail", kwargs={"pk": self.file.pk})
        )

        self.assertNotContains(resp, 'value="read_only"')
        self.assertContains(resp, 'value="read_write"')

    def test_supervisor_template_keeps_read_only_option(self):
        self.client.login(username="sup_lvl", password="Test1234!")
        resp = self.client.get(
            reverse("document_management:file_detail", kwargs={"pk": self.sup_file.pk})
        )

        self.assertContains(resp, 'value="read_only"')

    def test_registry_cannot_approve_read_only_for_non_supervisor(self):
        req = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.staff_user,
            reason="Need read only",
            access_type="read_only",
            status="pending",
        )
        self.client.login(username="reg_lvl", password="Test1234!")
        self.client.post(
            reverse("document_management:access_request_approve", kwargs={"pk": req.pk})
        )

        req.refresh_from_db()
        self.assertEqual(req.status, "pending")

    def test_registry_approves_read_only_for_supervisor(self):
        req = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.sup_user,
            reason="Need read only",
            access_type="read_only",
            status="pending",
        )
        self.client.login(username="reg_lvl", password="Test1234!")
        self.client.post(
            reverse("document_management:access_request_approve", kwargs={"pk": req.pk})
        )

        req.refresh_from_db()
        self.assertEqual(req.status, "approved")

    def test_registry_approves_read_write_for_staff(self):
        req = FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.staff_user,
            reason="Need read write",
            access_type="read_write",
            status="pending",
        )
        self.client.login(username="reg_lvl", password="Test1234!")
        self.client.post(
            reverse("document_management:access_request_approve", kwargs={"pk": req.pk})
        )

        req.refresh_from_db()
        self.assertEqual(req.status, "approved")
