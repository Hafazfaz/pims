"""
Tests for the 48-hour transit alert task: senders are notified when a
dispatched file is still in transit after 48 hours, then reminded daily.
"""
from datetime import timedelta

from django.contrib.auth.models import Group
from django.core import mail
from django.test import Client, TestCase
from django.utils import timezone
from organization.models import Department, Designation, Staff
from user_management.models import CustomUser

from document_management.models import File, FileMovement
from document_management.tasks import check_transit_alerts


def make_user(username, group_name=None, is_superuser=False):
    u = CustomUser.objects.create_user(username=username, password="Test1234!")
    u.email = f"{username}@example.com"
    u.is_superuser = is_superuser
    u.save()
    if group_name:
        g, _ = Group.objects.get_or_create(name=group_name)
        u.groups.add(g)
    return u


def make_staff(user, designation_name="Officer", dept=None):
    desig, _ = Designation.objects.get_or_create(name=designation_name, defaults={"level": 5})
    return Staff.objects.create(user=user, designation=desig, department=dept)


class TransitAlertTest(TestCase):
    """48h transit alerts for senders of pending dispatches."""

    def setUp(self):
        self.client = Client()
        self.dept = Department.objects.create(name="Records", code="REC")

        self.reg_user = make_user("reg_transit", "Registry")
        self.registry = make_staff(self.reg_user, "Registry Officer", self.dept)

        self.sender_user = make_user("sender_transit", "Supervisor")
        self.sender = make_staff(self.sender_user, "Officer", self.dept)

        self.recipient_user = make_user("recipient_transit", "Staff")
        self.recipient = make_staff(self.recipient_user, "Officer", self.dept)

        self.file = File.objects.create(
            title="TRANSIT ALERT FILE",
            file_type="policy",
            owner=self.sender,
            department=self.dept,
            current_location=self.recipient,
            created_by=self.reg_user,
            status="in_transit",
        )
        self.movement = FileMovement.objects.create(
            file=self.file,
            sent_by=self.sender_user,
            from_location=self.sender,
            sent_to=self.recipient,
            note="Please review",
            action="sent",
            status="pending",
        )

    def _age_movement(self, hours):
        FileMovement.objects.filter(pk=self.movement.pk).update(
            moved_at=timezone.now() - timedelta(hours=hours)
        )
        self.movement.refresh_from_db()

    def _sender_alerts(self):
        return self.sender_user.notifications.filter(message__icontains="TRANSIT ALERT")

    def test_task_exists(self):
        self.assertTrue(callable(check_transit_alerts))

    def test_alert_sent_after_48_hours(self):
        self._age_movement(49)

        result = check_transit_alerts()

        alerts = self._sender_alerts()
        self.assertEqual(alerts.count(), 1)
        self.assertIn(self.file.file_number, alerts.first().message)
        self.assertIn("49 hour", alerts.first().message)
        self.movement.refresh_from_db()
        self.assertIsNotNone(self.movement.transit_alert_first_sent_at)
        self.assertIsNotNone(self.movement.transit_alert_last_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.file.file_number, mail.outbox[0].subject)
        self.assertEqual(result, "Sent 1 transit alerts")

    def test_no_alert_within_48_hours(self):
        self._age_movement(24)

        result = check_transit_alerts()

        self.assertEqual(self._sender_alerts().count(), 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(result, "Sent 0 transit alerts")

    def test_alert_only_sent_once_until_followup_due(self):
        self._age_movement(49)

        check_transit_alerts()
        check_transit_alerts()

        self.assertEqual(self._sender_alerts().count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_daily_followup_after_first_alert(self):
        self._age_movement(49)
        check_transit_alerts()

        # Pretend the first alert went out more than 24 hours ago.
        FileMovement.objects.filter(pk=self.movement.pk).update(
            transit_alert_first_sent_at=timezone.now() - timedelta(hours=49),
            transit_alert_last_sent_at=timezone.now() - timedelta(hours=25),
        )

        check_transit_alerts()

        self.assertEqual(self._sender_alerts().count(), 2)
        self.assertEqual(len(mail.outbox), 2)

    def test_no_alert_once_file_leaves_transit(self):
        self._age_movement(49)
        self.file.status = "active"
        self.file.save(update_fields=["status"])

        check_transit_alerts()

        self.assertEqual(self._sender_alerts().count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_no_alert_for_closed_or_recalled_movement(self):
        self._age_movement(49)
        FileMovement.objects.filter(pk=self.movement.pk).update(action="recalled")

        check_transit_alerts()
        self.assertEqual(self._sender_alerts().count(), 0)

        FileMovement.objects.filter(pk=self.movement.pk).update(
            action="sent", closed_at=timezone.now()
        )
        check_transit_alerts()
        self.assertEqual(self._sender_alerts().count(), 0)

    def test_recipient_is_not_notified(self):
        self._age_movement(49)

        check_transit_alerts()

        self.assertFalse(self.recipient_user.notifications.exists())

    def test_forwarded_movement_is_not_alerted(self):
        self._age_movement(49)
        FileMovement.objects.filter(pk=self.movement.pk).update(status="forwarded")

        check_transit_alerts()

        self.assertEqual(self._sender_alerts().count(), 0)

    def test_is_stuck_in_transit_property(self):
        self._age_movement(49)
        self.movement.refresh_from_db()
        self.assertTrue(self.movement.is_stuck_in_transit)

        self._age_movement(10)
        self.movement.refresh_from_db()
        self.assertFalse(self.movement.is_stuck_in_transit)
