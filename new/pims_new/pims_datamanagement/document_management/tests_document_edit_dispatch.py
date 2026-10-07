"""Tests for in-place document editing and the dispatch action row."""
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import NoReverseMatch, reverse
from organization.models import Department, Designation, Staff
from user_management.models import CustomUser

from document_management.models import Document, File, FileAccessRequest


def make_user(username, group_name=None):
    u = CustomUser.objects.create_user(username=username, password="Test1234!")
    if group_name:
        g, _ = Group.objects.get_or_create(name=group_name)
        u.groups.add(g)
    return u


def make_staff(user, designation_name="Officer", dept=None):
    desig, _ = Designation.objects.get_or_create(name=designation_name, defaults={"level": 5})
    return Staff.objects.create(user=user, designation=desig, department=dept)


class DocumentEditViewTest(TestCase):
    """Edit saves onto the same row — no child 'version' documents."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="IT", code="IT")

        self.owner_user = make_user("edit_owner")
        self.owner = make_staff(self.owner_user, "Officer", self.dept)

        self.stranger_user = make_user("edit_stranger")
        self.stranger = make_staff(self.stranger_user, "Officer", self.dept)

        self.file = File.objects.create(
            title="EDIT FILE",
            file_type="personal",
            owner=self.owner,
            department=self.dept,
            current_location=self.owner,
            created_by=self.owner_user,
            status="active",
        )
        self.doc = Document.objects.create(
            file=self.file,
            uploaded_by=self.owner_user,
            title="Original title",
            minute_content="Original content",
            priority="urgent",
            status="approved",
        )

    def test_edit_updates_document_in_place(self):
        """Same primary key, no new row, status untouched."""
        self.client.force_login(self.owner_user)
        url = reverse("document_management:document_edit", kwargs={"pk": self.doc.pk})
        response = self.client.post(
            url, {"title": "Updated title", "minute_content": "Updated content"}
        )
        self.assertEqual(response.status_code, 302)

        self.doc.refresh_from_db()
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(self.doc.title, "Updated title")
        self.assertEqual(self.doc.minute_content, "Updated content")
        # Editing must not reset an approved document back to pending.
        self.assertEqual(self.doc.status, "approved")

    def test_edit_allows_clearing_content(self):
        self.client.force_login(self.owner_user)
        url = reverse("document_management:document_edit", kwargs={"pk": self.doc.pk})
        self.client.post(url, {"title": "Original title", "minute_content": ""})
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.minute_content, "")

    def test_edit_blocked_for_unrelated_staff(self):
        self.client.force_login(self.stranger_user)
        url = reverse("document_management:document_edit", kwargs={"pk": self.doc.pk})
        response = self.client.post(url, {"title": "Hacked title"})
        self.assertEqual(response.status_code, 302)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.title, "Original title")

    def test_old_new_version_url_is_gone(self):
        with self.assertRaises(NoReverseMatch):
            reverse("document_management:document_new_version", kwargs={"pk": self.doc.pk})


class DocumentShareActionRowTest(TestCase):
    """Document detail offers document sharing by email only: the Send File
    option, its modal, and the file-level Share button are gone."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="OPS", code="OPS")

        self.owner_user = make_user("disp_owner")
        self.owner = make_staff(self.owner_user, "Officer", self.dept)

        self.hod_user = make_user("disp_hod")
        self.hod = make_staff(self.hod_user, "Head of Department", self.dept)

        self.file = File.objects.create(
            title="DISPATCH FILE",
            file_type="personal",
            owner=self.owner,
            department=self.dept,
            current_location=self.hod,
            created_by=self.owner_user,
            status="active",
        )
        self.doc = Document.objects.create(
            file=self.file,
            uploaded_by=self.owner_user,
            title="Shareable Doc",
            minute_content="Body of the document",
            status="pending",
        )
        # Document detail now requires an approved access request for personal
        # files; give the HOD viewer one so the page renders.
        FileAccessRequest.objects.create(
            file=self.file,
            requested_by=self.hod_user,
            access_type="read_only",
            status="approved",
            reason="Test access",
        )

    def _url(self):
        return reverse("document_management:document_detail", kwargs={"pk": self.doc.pk})

    def _get(self, user=None):
        self.client.force_login(user or self.hod_user)
        return self.client.get(self._url())

    def _grant_share_permission(self):
        from django.contrib.auth.models import Permission

        perm = Permission.objects.get(codename="can_share_documents")
        self.hod_user.user_permissions.add(perm)
        # Fresh instance so the permission cache on the old one isn't reused.
        self.hod_user = CustomUser.objects.get(pk=self.hod_user.pk)

    def _add_signature(self):
        import base64

        from django.core.files.uploadedfile import SimpleUploadedFile
        from organization.models import StaffSignature

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        StaffSignature.objects.create(
            staff=self.hod,
            image=SimpleUploadedFile("sig.png", png, content_type="image/png"),
            is_active=True,
            is_verified=True,
        )

    def test_send_file_option_removed(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Send File")
        self.assertNotContains(response, "Dispatch not allowed")
        self.assertNotIn("can_send_file", response.context)
        self.assertNotIn("send_file_form", response.context)
        self.assertNotIn("dispatch_blocked_reason", response.context)

    def test_post_no_longer_dispatches_files(self):
        """POSTing the old send-file payload hits no handler anymore (405)."""
        self.client.force_login(self.hod_user)
        response = self.client.post(
            self._url(),
            {"recipient": self.owner_user.pk, "note": "please review"},
        )
        self.assertEqual(response.status_code, 405)
        from document_management.models import FileMovement

        self.assertFalse(FileMovement.objects.filter(file=self.file).exists())

    def test_share_button_hidden_without_permission(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_share_document"])
        # Neither the button nor the modal form is rendered.
        self.assertNotContains(response, "showShareModal = true")
        self.assertNotContains(response, "recipient_email")

    def test_share_button_shows_with_permission(self):
        self._grant_share_permission()
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "showShareModal = true")
        self.assertContains(response, "/share-email/")

    def test_share_email_sends_document(self):
        from django.core import mail

        from document_management.models import EmailLog

        self._grant_share_permission()
        self._add_signature()
        self.client.force_login(self.hod_user)
        response = self.client.post(
            reverse("document_management:document_share_email", kwargs={"pk": self.doc.pk}),
            {
                "recipient_email": "someone@example.com",
                "subject": "Please review",
                "message": "See attached document",
                "include_signature": "on",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["someone@example.com"])
        self.assertEqual(sent.subject, "Please review")
        self.assertIn(self.file.file_number, sent.body)
        self.assertIn("See attached document", sent.body)
        # PDF of the document is attached alongside the original file.
        self.assertTrue(sent.attachments)
        self.assertTrue(
            EmailLog.objects.filter(
                recipient_email="someone@example.com", status="sent"
            ).exists()
        )

    def test_share_email_denied_without_permission(self):
        from django.core import mail

        self._add_signature()
        self.client.force_login(self.hod_user)
        response = self.client.post(
            reverse("document_management:document_share_email", kwargs={"pk": self.doc.pk}),
            {"recipient_email": "someone@example.com", "message": "hi"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_file_detail_has_no_share_button(self):
        """Files are never shared — only individual documents are."""
        self.client.force_login(self.hod_user)
        response = self.client.get(
            reverse("document_management:file_detail", kwargs={"pk": self.file.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "showShareModal = true")
        self.assertNotContains(response, 'name="recipient_email"')

    def test_approved_document_shows_approved_chip(self):
        self.doc.status = "approved"
        self.doc.save(update_fields=["status"])
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "\u2713 Approved")
