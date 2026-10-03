"""Tests for tracking standalone urgent documents from the urgent inbox."""
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from organization.models import Department, Designation, Staff
from user_management.models import CustomUser

from document_management.models import Document, File, FileMovement


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


class UrgentDocumentTrackingTest(TestCase):
    """Urgent inbox rows must open the document they belong to."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="IT", code="IT")

        self.creator = make_user("urgent_creator", "Staff")
        self.creator_staff = make_staff(self.creator, "Officer", self.dept)

        self.viewer = make_user("urgent_viewer", "Staff")
        self.viewer_staff = make_staff(self.viewer, "Officer", self.dept)

        self.standalone = Document.objects.create(
            file=None,
            uploaded_by=self.creator,
            title="Urgent Doc",
            priority="urgent",
            status="pending",
            minute_content="Report to the board immediately.",
        )

    def test_urgent_inbox_links_standalone_document(self):
        """Both the title and the action cell link to the tracking page."""
        self.client.force_login(self.viewer)
        url = reverse("document_management:inbox") + "?mode=urgent"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        track_url = reverse("document_management:urgent_document_detail", kwargs={"pk": self.standalone.pk})
        self.assertContains(response, track_url)

    def test_tracking_page_renders(self):
        """Any staff member can open the tracking page and read the content."""
        self.client.force_login(self.viewer)
        url = reverse("document_management:urgent_document_detail", kwargs={"pk": self.standalone.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Urgent Doc")
        self.assertContains(response, "Report to the board immediately.")
        self.assertContains(response, "Activity trail")

    def test_tracking_page_renders_for_anonymous_redirects_to_login(self):
        url = reverse("document_management:urgent_document_detail", kwargs={"pk": self.standalone.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_file_backed_document_redirects_to_document_detail(self):
        """Documents inside a file keep their existing detail page."""
        file_obj = File.objects.create(
            title="PRIORITY FILE",
            file_type="personal",
            owner=self.creator_staff,
            department=self.dept,
            current_location=self.creator_staff,
            created_by=self.creator,
            status="active",
        )
        doc = Document.objects.create(
            file=file_obj, uploaded_by=self.creator, title="Filed Doc", priority="urgent"
        )
        self.client.force_login(self.viewer)
        url = reverse("document_management:urgent_document_detail", kwargs={"pk": doc.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("document_management:document_detail", kwargs={"pk": doc.pk}), response.url
        )

    def test_file_backed_row_links_to_its_own_movement(self):
        """A row links to a movement carrying that document, not the file's first."""
        file_obj = File.objects.create(
            title="MOVEMENT FILE",
            file_type="personal",
            owner=self.creator_staff,
            department=self.dept,
            current_location=self.creator_staff,
            created_by=self.creator,
            status="active",
        )
        other_doc = Document.objects.create(
            file=file_obj, uploaded_by=self.creator, title="Other Doc", priority="normal"
        )
        urgent_in_file = Document.objects.create(
            file=file_obj, uploaded_by=self.creator, title="Filed Urgent", priority="urgent"
        )
        # Older movement for another document, newer one for the urgent doc.
        FileMovement.objects.create(
            file=file_obj,
            document=other_doc,
            sent_by=self.creator,
            sent_to=self.viewer_staff,
            action="sent",
            status="pending",
        )
        movement = FileMovement.objects.create(
            file=file_obj,
            document=urgent_in_file,
            sent_by=self.creator,
            sent_to=self.viewer_staff,
            action="sent",
            status="pending",
        )

        self.client.force_login(self.viewer)
        response = self.client.get(reverse("document_management:inbox") + "?mode=urgent")
        self.assertEqual(response.status_code, 200)
        expected = reverse("document_management:inbox_document_detail", kwargs={"pk": movement.pk})
        self.assertContains(response, expected)

    def test_standalone_without_movement_is_not_linked_to_a_movement(self):
        """Standalone documents never fall back to a movement link."""
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("document_management:inbox") + "?mode=urgent")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, reverse("document_management:inbox_document_detail", kwargs={"pk": 999})
        )
