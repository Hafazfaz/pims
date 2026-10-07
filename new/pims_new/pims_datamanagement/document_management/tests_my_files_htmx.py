"""My Records search over htmx: Enter updates the panel in place, never the page.

The search form and its input both hx-get the my_files URL; the view answers
HX requests with ``_my_files_panel.html`` (root ``#my-files-list``), so the
swap must be outerHTML onto that id — a boosted/bodiless swap re-renders the
whole page, and an innerHTML swap nests a duplicate wrapper on every keystroke.
"""
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from organization.models import Department, Designation, Staff
from user_management.models import CustomUser

from document_management.models import Document, File


def make_user(username, group_name=None):
    u = CustomUser.objects.create_user(username=username, password="Test1234!")
    if group_name:
        g, _ = Group.objects.get_or_create(name=group_name)
        u.groups.add(g)
    return u


def make_staff(user, designation_name="Officer", dept=None):
    desig, _ = Designation.objects.get_or_create(name=designation_name, defaults={"level": 5})
    return Staff.objects.create(user=user, designation=desig, department=dept)


class MyFilesSearchHtmxTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Records", code="REC")
        self.user = make_user("search_user", "Staff")
        self.staff = make_staff(self.user, "Officer", self.dept)
        self.file = File.objects.create(
            title="PERSONNEL FILE",
            file_type="personal",
            owner=self.staff,
            department=self.dept,
            current_location=self.staff,
            created_by=self.user,
            status="active",
        )
        Document.objects.create(
            file=self.file, uploaded_by=self.user, title="Leave Application"
        )
        self.url = reverse("document_management:my_files")
        self.client.force_login(self.user)

    def test_hx_search_returns_panel_only(self):
        """HX search responses carry just #my-files-list — the header card
        (search form, View My History) must never ride along, or swapping it
        in would duplicate the page chrome."""
        response = self.client.get(self.url, {"q": "Leave"}, headers={"HX-Request": "true"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('id="my-files-list"', content)
        self.assertNotIn("View My History", content)

    def test_plain_search_renders_full_page(self):
        response = self.client.get(self.url, {"q": "Leave"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="my-files-list"')
        self.assertContains(response, "View My History")

    def test_search_form_swaps_outerhtml_onto_panel(self):
        """Enter submits the form (hx-get, no hx-boost) and the swap replaces
        #my-files-list instead of dumping the panel into <body> or nesting a
        duplicate wrapper inside it."""
        response = self.client.get(self.url)
        self.assertContains(response, 'hx-target="#my-files-list"')
        self.assertContains(response, 'hx-swap="outerHTML"')
        self.assertContains(response, f'hx-get="{reverse("document_management:my_files")}"')
        # The boosted full-page swap that broke Enter must be gone from the
        # search form. This fixture has one file, so the only hx-boost in the
        # app (the pagination wrapper) isn't rendered here.
        self.assertNotContains(response, "hx-boost")
