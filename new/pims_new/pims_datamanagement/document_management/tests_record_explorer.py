"""Record explorer scoping: heads browse the staff under them, nothing else."""
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse
from organization.models import Department, Designation, Staff, Unit
from user_management.models import CustomUser

from document_management.models import File


def make_user(username, group_name=None, is_superuser=False):
    u = CustomUser.objects.create_user(username=username, password="Test1234!")
    u.is_superuser = is_superuser
    u.save()
    if group_name:
        g, _ = Group.objects.get_or_create(name=group_name)
        u.groups.add(g)
    return u


def make_staff(user, designation_name="Officer", dept=None, unit=None):
    desig, _ = Designation.objects.get_or_create(name=designation_name, defaults={"level": 5})
    return Staff.objects.create(user=user, designation=desig, department=dept, unit=unit)


class RecordExplorerScopeTest(TestCase):
    """One explorer, three widths: organisation, department, unit."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Cardiology", code="CAR")
        self.other_dept = Department.objects.create(name="Surgery", code="SUR")

        self.hod_user = make_user("exp_hod", "Staff")
        self.hod = make_staff(self.hod_user, "Head of Department", self.dept)
        self.dept.head = self.hod
        self.dept.save()

        self.member_user = make_user("exp_member", "Staff")
        self.member = make_staff(self.member_user, "Officer", self.dept)

        self.um_user = make_user("exp_um", "Staff")
        self.unit_manager = make_staff(self.um_user, "Head of Unit", self.dept)
        self.unit = Unit.objects.create(name="Cath Lab", department=self.dept, head=self.unit_manager)

        self.unit_member_user = make_user("exp_unit_member", "Staff")
        self.unit_member = make_staff(self.unit_member_user, "Officer", self.dept, unit=self.unit)

        self.outsider_user = make_user("exp_outsider", "Staff")
        self.outsider = make_staff(self.outsider_user, "Officer", self.other_dept)

        self.exec_user = make_user("exp_exec", "Staff")
        self.exec_staff = make_staff(self.exec_user, "Officer", self.dept)
        self.exec_user.user_permissions.add(
            Permission.objects.get(codename="can_executive", content_type__app_label="user_management")
        )

        self.creator = make_user("exp_creator", "Staff")

        self.policy_own = File.objects.create(
            title="CARDIOLOGY POLICY",
            file_type="policy",
            department=self.dept,
            created_by=self.creator,
        )
        self.policy_other = File.objects.create(
            title="SURGERY POLICY",
            file_type="policy",
            department=self.other_dept,
            created_by=self.creator,
        )
        self.file_member = File.objects.create(
            title="MEMBER FILE",
            file_type="personal",
            owner=self.member,
            department=self.dept,
            created_by=self.creator,
        )
        self.file_unit_member = File.objects.create(
            title="UNIT MEMBER FILE",
            file_type="personal",
            owner=self.unit_member,
            department=self.dept,
            created_by=self.creator,
        )
        self.file_unit_manager = File.objects.create(
            title="UNIT MANAGER FILE",
            file_type="personal",
            owner=self.unit_manager,
            department=self.dept,
            created_by=self.creator,
        )
        self.file_hod = File.objects.create(
            title="HOD FILE",
            file_type="personal",
            owner=self.hod,
            department=self.dept,
            created_by=self.creator,
        )
        self.file_outsider = File.objects.create(
            title="OUTSIDER FILE",
            file_type="personal",
            owner=self.outsider,
            department=self.other_dept,
            created_by=self.creator,
        )

        self.url = reverse("document_management:record_explorer")

    def _titles(self, response):
        return {f.title for f in response.context["files"]}

    def test_hod_sees_whole_department_and_nothing_else(self):
        self.client.login(username="exp_hod", password="Test1234!")
        titles = self._titles(self.client.get(self.url))
        self.assertEqual(
            titles,
            {"CARDIOLOGY POLICY", "MEMBER FILE", "UNIT MEMBER FILE", "UNIT MANAGER FILE"},
        )

    def test_hod_own_file_is_not_listed(self):
        self.client.login(username="exp_hod", password="Test1234!")
        self.assertNotIn("HOD FILE", self._titles(self.client.get(self.url)))

    def test_unit_head_sees_only_their_units_files(self):
        self.client.login(username="exp_um", password="Test1234!")
        titles = self._titles(self.client.get(self.url))
        self.assertEqual(titles, {"UNIT MEMBER FILE"})
        self.assertNotIn("UNIT MANAGER FILE", titles)
        self.assertNotIn("MEMBER FILE", titles)

    def test_executive_sees_every_file(self):
        self.client.login(username="exp_exec", password="Test1234!")
        titles = self._titles(self.client.get(self.url))
        self.assertEqual(
            titles,
            {
                "CARDIOLOGY POLICY",
                "SURGERY POLICY",
                "MEMBER FILE",
                "UNIT MEMBER FILE",
                "UNIT MANAGER FILE",
                "HOD FILE",
                "OUTSIDER FILE",
            },
        )

    def test_regular_staff_cannot_open_the_explorer(self):
        self.client.login(username="exp_member", password="Test1234!")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("document_management:my_files"))

    def test_sidebar_links_hod_to_their_department_files(self):
        self.client.login(username="exp_hod", password="Test1234!")
        response = self.client.get(self.url)
        self.assertContains(response, "Department Files")
        self.assertEqual(response.context["nav_active"], "explorer")

    def test_sidebar_links_unit_head_to_their_unit_files(self):
        self.client.login(username="exp_um", password="Test1234!")
        response = self.client.get(self.url)
        self.assertContains(response, "Unit Files")
        self.assertEqual(response.context["nav_active"], "explorer")

    def test_staff_dropdown_lists_the_staff_under_the_head(self):
        self.client.login(username="exp_hod", password="Test1234!")
        options = list(self.client.get(self.url).context["staff_options"])
        self.assertEqual({s.pk for s in options}, {self.member.pk, self.unit_manager.pk, self.unit_member.pk})
        self.assertEqual({s.active_file_count for s in options}, {1})

        self.client.logout()
        self.client.login(username="exp_um", password="Test1234!")
        options = list(self.client.get(self.url).context["staff_options"])
        self.assertEqual([s.pk for s in options], [self.unit_member.pk])

    def test_staff_filter_narrows_the_list_to_one_member(self):
        self.client.login(username="exp_hod", password="Test1234!")
        response = self.client.get(self.url, {"staff": self.unit_member.pk})
        self.assertEqual(self._titles(response), {"UNIT MEMBER FILE"})
        self.assertEqual(response.context["selected_staff"], self.unit_member.pk)

    def test_staff_filter_cannot_reach_outside_the_scope(self):
        self.client.login(username="exp_hod", password="Test1234!")
        response = self.client.get(self.url, {"staff": self.outsider.pk})
        self.assertEqual(response.context["selected_staff"], "")
        self.assertNotIn("OUTSIDER FILE", self._titles(response))
        self.assertIn("MEMBER FILE", self._titles(response))

    def test_file_detail_is_scoped_too(self):
        self.client.login(username="exp_hod", password="Test1234!")
        outside = self.client.get(self.url, {"file_pk": self.file_outsider.pk})
        self.assertNotIn("selected_file", outside.context)

        inside = self.client.get(self.url, {"file_pk": self.file_member.pk})
        self.assertEqual(inside.context["selected_file"].pk, self.file_member.pk)
