"""Inbox actions over htmx: the panel swaps in place, no page reload."""
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


class InboxHtmxActionTest(TestCase):
    """Approve/reject from the inbox: htmx gets the panel, plain posts redirect."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="IT", code="IT")

        self.sender = make_user("htmx_sender", "Staff")
        self.sender_staff = make_staff(self.sender, "Officer", self.dept)

        self.hod_user = make_user("htmx_hod", "Staff")
        self.hod_staff = make_staff(self.hod_user, "Head of Department", self.dept)
        self.dept.head = self.hod_staff
        self.dept.save()

        # The final approver the HOD's approval routes to (Medical Director
        # designation carries user_management.can_approve_document).
        self.approver_user = make_user("htmx_approver", "Staff")
        self.approver_user.first_name = "Final"
        self.approver_user.last_name = "Approver"
        self.approver_user.save()
        self.approver_staff = make_staff(self.approver_user, "Medical Director", self.dept)

        self.doc = Document.objects.create(
            uploaded_by=self.sender,
            title="HTMX DOC",
            priority="urgent",
            status="pending",
            minute_content="Please approve.",
        )
        self.file = File.objects.create(
            title="HTMX FILE",
            file_type="personal",
            owner=self.sender_staff,
            department=self.dept,
            current_location=self.hod_staff,
            created_by=self.sender,
            status="active",
        )
        self.doc.file = self.file
        self.doc.save(update_fields=["file"])
        self.movement = FileMovement.objects.create(
            file=self.file,
            document=self.doc,
            sent_by=self.sender,
            from_location=self.sender_staff,
            sent_to=self.hod_staff,
            action="sent",
            status="pending",
        )
        self.inbox_url = reverse("document_management:inbox")
        self.action_url = reverse(
            "document_management:document_action", kwargs={"pk": self.movement.pk}
        )
        self.client.force_login(self.hod_user)

    def _hx_post(self, url, data, current_url="http://testserver/inbox/"):
        return self.client.post(
            url,
            data,
            headers={
                "HX-Request": "true",
                "HX-Current-URL": current_url,
            },
        )

    def test_htmx_approve_renders_panel_without_redirect(self):
        response = self._hx_post(
            self.action_url,
            {"action": "approve", "note": "Routing for final approval", "recipient_staff_id": self.approver_staff.pk},
            f"{self.inbox_url}?tab=untreated",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Location", response)
        self.assertNotIn("HX-Redirect", response)
        # The fragment is the panel: tabs + flash message drawn in place.
        self.assertContains(response, "Untreated")
        # The HOD's approval is recorded and the document is routed to the
        # approver for the final decision — it does not settle it here.
        self.assertContains(response, "Approved — sent to Final Approver for final approval.")
        self.movement.refresh_from_db()
        self.assertEqual(self.movement.status, "approved")

    def test_approve_without_note_is_refused(self):
        """Approve-and-route carries a note — nothing moves without one."""
        response = self._hx_post(
            self.action_url,
            {"action": "approve", "recipient_staff_id": self.approver_staff.pk},
            f"{self.inbox_url}?tab=untreated",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add a note explaining your approval")
        self.movement.refresh_from_db()
        self.assertEqual(self.movement.status, "pending")

    def test_htmx_reject_renders_panel_without_redirect(self):
        response = self._hx_post(
            self.action_url,
            {"action": "reject", "note": "Wrong annexure"},
            f"{self.inbox_url}?tab=untreated&filter=all",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Redirect", response)
        # The fragment is the panel (tabs + flash message), swapped in place.
        self.assertContains(response, "Untreated")
        self.movement.refresh_from_db()
        self.assertEqual(self.movement.status, "rejected")

    def test_plain_post_still_redirects(self):
        response = self.client.post(
            self.action_url, {"action": "approve", "note": "Routing for final approval", "recipient_staff_id": self.approver_staff.pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.inbox_url)
        self.movement.refresh_from_db()
        self.assertEqual(self.movement.status, "approved")

    def test_htmx_action_from_another_page_gets_hx_redirect(self):
        response = self._hx_post(
            self.action_url,
            {"action": "approve", "note": "Routing for final approval", "recipient_staff_id": self.approver_staff.pk},
            current_url="http://testserver/my-files/",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["HX-Redirect"].endswith(self.inbox_url))

    def test_inbox_get_renders_panel_container(self):
        response = self.client.get(self.inbox_url, headers={"HX-Request": "true"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="inbox-panel"')
        self.assertContains(response, "HTMX DOC")

    def test_inbox_row_has_no_inline_action_buttons(self):
        """Decisions moved to the detail page: the row only links to it."""
        response = self.client.get(self.inbox_url)
        self.assertContains(response, "View Doc")
        self.assertContains(
            response,
            reverse("document_management:inbox_document_detail", kwargs={"pk": self.movement.pk}),
        )
        # No inline approve/reject posts hit the action endpoint from the list.
        self.assertNotContains(response, self.action_url)
