"""
Creates a minimal set of test users for chain approval testing:
  - 1 Registry officer
  - 1 HOD (set as dept head)
  - 1 Unit Manager (set as unit head)
  - 2 regular staff
Each gets a personal file with some documents.
Password for all: password123
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = "Seed test users for chain approval testing"

    def handle(self, *args, **kwargs):
        from django.contrib.auth import get_user_model
        from organization.models import Department, Unit, Designation, Staff
        from document_management.models import File, Document

        User = get_user_model()

        # Groups
        registry_group, _ = Group.objects.get_or_create(name="Registry")
        staff_group, _ = Group.objects.get_or_create(name="Staff")

        # Org structure — reuse existing or create minimal
        dept, _ = Department.objects.get_or_create(name="Test Department", defaults={"code": "TST"})
        unit, _ = Unit.objects.get_or_create(name="Test Unit", defaults={"department": dept})
        
        desig_officer, _ = Designation.objects.get_or_create(name="Officer", defaults={"level": 8})
        desig_um, _ = Designation.objects.get_or_create(name="Unit Manager", defaults={"level": 6})
        desig_hod, _ = Designation.objects.get_or_create(name="Head of Department", defaults={"level": 4})
        desig_registry, _ = Designation.objects.get_or_create(name="Registry Officer", defaults={"level": 7})

        users_data = [
            ("test_registry", "Registry", "Test",    registry_group, dept, unit,  desig_registry, "registry"),
            ("test_hod",      "HOD",      "Test",    staff_group,    dept, None,  desig_hod,      "hod"),
            ("test_um",       "UnitMgr",  "Test",    staff_group,    dept, unit,  desig_um,       "unit_manager"),
            ("test_staff1",   "Staff",    "One",     staff_group,    dept, unit,  desig_officer,  "staff"),
            ("test_staff2",   "Staff",    "Two",     staff_group,    dept, unit,  desig_officer,  "staff"),
        ]

        registry_staff = None
        created_staff = []

        for username, first, last, group, d, u, desig, role in users_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "email": f"{username}@test.com"}
            )
            if created:
                user.set_password("password123")
                user.save()
            user.groups.add(group)

            staff, _ = Staff.objects.get_or_create(
                user=user,
                defaults={"department": d, "unit": u, "designation": desig}
            )

            if role == "registry":
                registry_staff = staff
            elif role == "hod":
                dept.head = staff
                dept.save()
            elif role == "unit_manager":
                unit.head = staff
                unit.save()

            created_staff.append((staff, role))
            self.stdout.write(f"  {'Created' if created else 'Exists'}: {username} ({role})")

        # Personal files + documents for each non-registry staff
        for staff, role in created_staff:
            if role == "registry":
                continue
            file_obj, f_created = File.objects.get_or_create(
                file_type="personal",
                owner=staff,
                defaults={
                    "title": f"PERSONNEL RECORD - {staff.user.get_full_name().upper()}",
                    "department": dept,
                    "status": "active",
                    "current_location": staff,
                    "created_by": registry_staff.user if registry_staff else staff.user,
                }
            )
            if f_created:
                Document.objects.create(
                    file=file_obj,
                    uploaded_by=registry_staff.user if registry_staff else staff.user,
                    title="Employment Letter",
                    minute_content="Welcome to the organisation.",
                )
                self.stdout.write(f"    + File & document for {staff.user.username}")

        self.stdout.write(self.style.SUCCESS("\nDone. All passwords: password123"))
