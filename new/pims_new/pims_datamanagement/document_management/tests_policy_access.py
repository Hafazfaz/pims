"""
Policy files must be grant-based like personal files: the file-page banner
must not show Full Access Granted unless the viewer holds an approved
FileAccessRequest or an active FileMovement.
"""
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

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


class PolicyFileAccessBannerTest(TestCase):
    """Full Access banner is grant-based for policy files, same as personal."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Finance", code="FIN")

        # Registry creates and holds custody
        self.reg_user = make_user("reg_pol", "Registry")
        self.registry = make_staff(self.reg_user, "Registry Officer", self.dept)

        # HOD of the department (owner-equivalent of a policy file)
        self.hod_user = make_user("hod_pol", "HOD/HOU")
        self.hod = make_staff(self.hod_user, "Head of Department", self.dept)
        self.dept.head = self.hod
        self.dept.save()

        # Unrelated staff in another department
        self.other_dept = Department.objects.create(name="HR", code="HR")
        self.other_user = make_user("other_pol", "Staff")
        self.other_staff = make_staff(self.other_user, "Officer", self.other_dept)

        # Policy file at rest with Registry, no owner
        self.policy_file = File.objects.create(
            title="POLICY ACCESS FILE",
            file_type="policy",
            department=self.dept,
            current_location=self.registry,
            created_by=self.reg_user,
            status="active",
        )

    def _fetch(self, user):
        self.client.force_login(user)
        return self.client.get(
            reverse("document_management:file_detail", args=[self.policy_file.pk])
        )

    def test_hod_without_request_sees_no_full_access_banner(self):
        resp = self._fetch(self.hod_user)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["has_approved_access"])
        self.assertFalse(resp.context["has_rw_access"])
        self.assertNotContains(resp, "Full Admin Access Granted")
        self.assertNotContains(resp, "Read-Only Access Granted")

    def test_hod_with_approved_request_sees_banner(self):
        FileAccessRequest.objects.create(
            file=self.policy_file,
            requested_by=self.hod_user,
            reason="Need it",
            status="approved",
            access_type="read_write",
            approved_at=timezone.now(),
        )
        # Approving transfers custody to the requester (FileAccessRequestApproveView),
        # and a grant only counts while its holder has custody.
        self.policy_file.current_location = self.hod
        self.policy_file.save(update_fields=["current_location"])
        resp = self._fetch(self.hod_user)
        self.assertTrue(resp.context["has_approved_access"])
        self.assertTrue(resp.context["has_rw_access"])
        self.assertContains(resp, "Full Admin Access Granted")

    def test_registry_still_has_full_access(self):
        resp = self._fetch(self.reg_user)
        self.assertTrue(resp.context["has_approved_access"])
        self.assertTrue(resp.context["has_rw_access"])

    def test_unrelated_staff_cannot_open_policy_file(self):
        resp = self._fetch(self.other_user)
        # Either blocked at has_permission (404/redirect) or no banner
        if resp.status_code == 200:
            self.assertFalse(resp.context.get("has_approved_access", False))
            self.assertNotContains(resp, "Full Admin Access Granted")
