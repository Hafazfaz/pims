"""Outgoing Files Tracking must show folders that are still in transit.

Dispatching a file sets ``File.status = "in_transit"``. The outgoing
tracking (and its Recall action) is derived on the fly from the file's
existing status + current custodian — no extra model to keep in sync.
"""
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse
from organization.models import Department, Designation, Staff
from user_management.models import CustomUser

from document_management.models import File


def make_user(username, group_name=None):
    u = CustomUser.objects.create_user(username=username, password="Test1234!")
    if group_name:
        g, _ = Group.objects.get_or_create(name=group_name)
        u.groups.add(g)
    return u


def make_staff(user, designation_name="Officer", dept=None):
    desig, _ = Designation.objects.get_or_create(name=designation_name, defaults={"level": 5})
    return Staff.objects.create(user=user, designation=desig, department=dept)


class OutgoingInTransitTest(TestCase):
    """In-transit folders appear in Outgoing Files Tracking with actions."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="IT", code="IT")

        self.registry_user = make_user("out_registry", "Registry")
        self.registry_staff = make_staff(self.registry_user, "Registry Officer", self.dept)

        self.holder_user = make_user("out_holder", "Staff")
        self.holder_staff = make_staff(self.holder_user, "Officer", self.dept)

        # Dispatched: sitting with a member of staff, file still in transit.
        self.in_transit = File.objects.create(
            title="IN TRANSIT FILE",
            file_type="personal",
            owner=self.holder_staff,
            department=self.dept,
            current_location=self.holder_staff,
            created_by=self.registry_user,
            status="in_transit",
        )
        # Receipt acknowledged: settled with its holder, so recall applies.
        self.settled = File.objects.create(
            title="SETTLED FILE",
            file_type="policy",
            department=self.dept,
            current_location=self.holder_staff,
            created_by=self.registry_user,
            status="active",
        )
        # In transit by status but already back with Registry — not outgoing.
        self.with_registry = File.objects.create(
            title="BACK WITH REGISTRY FILE",
            file_type="policy",
            department=self.dept,
            current_location=self.registry_staff,
            created_by=self.registry_user,
            status="in_transit",
        )

        self.client.force_login(self.registry_user)
        # FileRecallView is gated by the view_file permission.
        view_file = Permission.objects.filter(codename="view_file").first()
        if view_file:
            self.registry_user.user_permissions.add(view_file)
        self.list_url = reverse("document_management:staff_folder_list")

    def test_in_transit_file_is_listed_but_not_recallable(self):
        """Tracked with a row, but recall waits until receipt is acknowledged."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.in_transit.file_number)
        self.assertContains(response, "In Transit")
        self.assertContains(response, "Awaiting Receipt")
        self.assertNotContains(
            response,
            reverse("document_management:file_recall", kwargs={"pk": self.in_transit.pk}),
        )

    def test_settled_file_offers_recall(self):
        response = self.client.get(self.list_url)
        self.assertContains(
            response,
            reverse("document_management:file_recall", kwargs={"pk": self.settled.pk}),
        )

    def test_in_transit_file_back_with_registry_is_not_outgoing(self):
        response = self.client.get(self.list_url)
        outgoing = response.context["outgoing_files"]
        self.assertNotIn(self.with_registry, [item["file"] for item in outgoing])
        # The recall action is only rendered for rows that are actually out.
        self.assertNotContains(
            response,
            reverse("document_management:file_recall", kwargs={"pk": self.with_registry.pk}),
        )

    def test_outgoing_count_includes_in_transit(self):
        response = self.client.get(self.list_url)
        files_out = [item["file"] for item in response.context["outgoing_files"]]
        self.assertIn(self.in_transit, files_out)
        self.assertGreaterEqual(response.context["outgoing_files_count"], 1)

    def test_dashboard_counts_in_transit_as_outgoing(self):
        response = self.client.get(reverse("document_management:registry"))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.context["outgoing_files_count"], 1)
        self.assertGreaterEqual(response.context["total_files_count"], 1)

    def test_in_transit_file_cannot_be_recalled(self):
        response = self.client.post(
            reverse("document_management:file_recall", kwargs={"pk": self.in_transit.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.in_transit.refresh_from_db()
        self.assertEqual(self.in_transit.status, "in_transit")
        self.assertEqual(self.in_transit.current_location, self.holder_staff)
        # Still listed as out — it never left the holder's custody.
        outgoing = self.client.get(self.list_url).context["outgoing_files"]
        self.assertIn(self.in_transit, [item["file"] for item in outgoing])

    def test_recalling_settled_file_restores_active_custody(self):
        response = self.client.post(
            reverse("document_management:file_recall", kwargs={"pk": self.settled.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.settled.refresh_from_db()
        self.assertEqual(self.settled.status, "active")
        self.assertEqual(self.settled.current_location, self.registry_staff)
        # Settled with Registry, so it drops out of the outgoing list.
        outgoing = self.client.get(self.list_url).context["outgoing_files"]
        self.assertNotIn(self.settled, [item["file"] for item in outgoing])
