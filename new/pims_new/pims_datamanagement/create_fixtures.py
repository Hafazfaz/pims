import json
import os

import django
from django.contrib.auth.hashers import make_password

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pims_datamanagement.settings")
django.setup()


from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from document_management.models import Document, File
from organization.models import Department, Designation, Staff, Unit
from user_management.models import CustomUser


def create_fixtures():
    # --- Permission Retrieval ---
    # Get ContentTypes
    customuser_ct = ContentType.objects.get_for_model(CustomUser)
    department_ct = ContentType.objects.get_for_model(Department)
    unit_ct = ContentType.objects.get_for_model(Unit)
    designation_ct = ContentType.objects.get_for_model(Designation)
    staff_ct = ContentType.objects.get_for_model(Staff)
    file_ct = ContentType.objects.get_for_model(File)
    document_ct = ContentType.objects.get_for_model(Document)

    # Helper to get permissions for a model
    def get_perms_for_model(ct, actions=["add", "change", "delete", "view"]):
        perms = []
        for action in actions:
            codename = f"{action}_{ct.model}"
            try:
                perm = Permission.objects.get(content_type=ct, codename=codename)
                perms.append(perm)  # Return perm object, not just pk
            except Permission.DoesNotExist:
                print(f"Warning: Permission '{codename}' not found. Skipping.")
        return perms

    # Standard permissions
    customuser_perms_objs = get_perms_for_model(customuser_ct)
    department_perms_objs = get_perms_for_model(department_ct)
    unit_perms_objs = get_perms_for_model(unit_ct)
    designation_perms_objs = get_perms_for_model(designation_ct)
    staff_perms_objs = get_perms_for_model(staff_ct)
    file_perms_objs = get_perms_for_model(file_ct)
    document_perms_objs = get_perms_for_model(document_ct)

    # Custom permissions (defined in models.py)
    custom_file_perms_objs = []
    custom_document_perms_objs = []

    try:
        custom_file_perms_objs.append(
            Permission.objects.get(content_type=file_ct, codename="activate_file")
        )
    except Permission.DoesNotExist:
        print("Warning: Permission 'activate_file' not found. Skipping.")
    try:
        custom_file_perms_objs.append(
            Permission.objects.get(content_type=file_ct, codename="create_file")
        )
    except Permission.DoesNotExist:
        print("Warning: Permission 'create_file' not found. Skipping.")
    try:
        custom_file_perms_objs.append(
            Permission.objects.get(content_type=file_ct, codename="send_file")
        )
    except Permission.DoesNotExist:
        print("Warning: Permission 'send_file' not found. Skipping.")

    try:
        custom_document_perms_objs.append(
            Permission.objects.get(content_type=document_ct, codename="add_minute")
        )
    except Permission.DoesNotExist:
        print("Warning: Permission 'add_minute' not found. Skipping.")
    try:
        custom_document_perms_objs.append(
            Permission.objects.get(content_type=document_ct, codename="add_attachment")
        )
    except Permission.DoesNotExist:
        print("Warning: Permission 'add_attachment' not found. Skipping.")

    # --- Handle Groups (get_or_create) ---
    registry_group_obj, created = Group.objects.get_or_create(
        pk=1, defaults={"name": "Registry"}
    )
    if created:
        print(f"Created Group: {registry_group_obj.name}")
    else:
        print(f"Using existing Group: {registry_group_obj.name}")

    staff_group_obj, created = Group.objects.get_or_create(
        pk=2, defaults={"name": "Staff"}
    )
    if created:
        print(f"Created Group: {staff_group_obj.name}")
    else:
        print(f"Using existing Group: {staff_group_obj.name}")

    # Assign permissions to groups
    registry_group_obj.permissions.set(
        list(
            set(
                customuser_perms_objs
                + department_perms_objs
                + unit_perms_objs
                + designation_perms_objs
                + staff_perms_objs
                + file_perms_objs
                + document_perms_objs
                + custom_file_perms_objs
                + custom_document_perms_objs
            )
        )
    )
    print(f"Assigned permissions to {registry_group_obj.name} group.")

    staff_group_obj.permissions.set(
        list(
            set(
                customuser_perms_objs
                + department_perms_objs
                + unit_perms_objs
                + designation_perms_objs
                + staff_perms_objs
                + file_perms_objs
                + document_perms_objs
                + custom_file_perms_objs
                + custom_document_perms_objs
            )
        )
    )
    print(f"Assigned permissions to {staff_group_obj.name} group.")

    # --- Handle Users (get_or_create) ---
    users_to_create = [
        {
            "pk": 1,
            "username": "admin",
            "is_superuser": True,
            "is_staff": True,
            "first_name": "Admin",
            "last_name": "User",
            "email": "admin@example.com",
            "must_change_password": False,
            "groups": [],
        },
        {
            "pk": 2,
            "username": "registry_user",
            "is_superuser": False,
            "is_staff": True,
            "first_name": "Registry",
            "last_name": "User",
            "email": "registry@example.com",
            "must_change_password": False,
            "groups": [registry_group_obj],
        },
        {
            "pk": 3,
            "username": "staff_user1",
            "is_superuser": False,
            "is_staff": True,
            "first_name": "Staff",
            "last_name": "One",
            "email": "staff1@example.com",
            "must_change_password": True,
            "groups": [staff_group_obj],
        },
        {
            "pk": 4,
            "username": "staff_user2",
            "is_superuser": False,
            "is_staff": True,
            "first_name": "Staff",
            "last_name": "Two",
            "email": "staff2@example.com",
            "must_change_password": False,
            "groups": [staff_group_obj],
        },
        {
            "pk": 5,
            "username": "hod_user",
            "is_superuser": False,
            "is_staff": True,
            "first_name": "Head",
            "last_name": "Of Department",
            "email": "hod@example.com",
            "must_change_password": False,
            "groups": [staff_group_obj],
        },
        {
            "pk": 6,
            "username": "manager_user",
            "is_superuser": False,
            "is_staff": True,
            "first_name": "Unit",
            "last_name": "Manager",
            "email": "manager@example.com",
            "must_change_password": False,
            "groups": [staff_group_obj],
        },
        {
            "pk": 7,
            "username": "staff_user3",
            "is_superuser": False,
            "is_staff": True,
            "first_name": "Staff",
            "last_name": "Three",
            "email": "staff3@example.com",
            "must_change_password": False,
            "groups": [staff_group_obj],
        },
    ]

    user_objs = {}
    for user_data in users_to_create:
        pk = user_data.pop("pk")
        groups = user_data.pop("groups")
        user_obj, created = CustomUser.objects.get_or_create(
            pk=pk,
            defaults={
                "password": make_password("password123"),
                "is_active": True,
                **user_data,
            },
        )
        if created:
            print(f"Created User: {user_obj.username}")
        else:
            print(f"Using existing User: {user_obj.username}")
        user_obj.groups.set(groups)
        user_objs[user_obj.username] = user_obj

    # --- Generate JSON for other models ---
    fixtures = []

    # Departments
    hr_dept_obj, created = Department.objects.get_or_create(
        pk=1, defaults={"name": "Human Resources", "code": "HR"}
    )
    if created:
        print(f"Created Department: {hr_dept_obj.name}")
    else:
        print(f"Using existing Department: {hr_dept_obj.name}")

    it_dept_obj, created = Department.objects.get_or_create(
        pk=2, defaults={"name": "Information Technology", "code": "IT"}
    )
    if created:
        print(f"Created Department: {it_dept_obj.name}")
    else:
        print(f"Using existing Department: {it_dept_obj.name}")

    # Designations
    director_des_obj, created = Designation.objects.get_or_create(
        pk=1, defaults={"name": "Director", "level": 1}
    )
    if created:
        print(f"Created Designation: {director_des_obj.name}")
    else:
        print(f"Using existing Designation: {director_des_obj.name}")

    manager_des_obj, created = Designation.objects.get_or_create(
        pk=2, defaults={"name": "Manager", "level": 2}
    )
    if created:
        print(f"Created Designation: {manager_des_obj.name}")
    else:
        print(f"Using existing Designation: {manager_des_obj.name}")

    officer_des_obj, created = Designation.objects.get_or_create(
        pk=3, defaults={"name": "Officer", "level": 3}
    )
    if created:
        print(f"Created Designation: {officer_des_obj.name}")
    else:
        print(f"Using existing Designation: {officer_des_obj.name}")

    # Units
    payroll_unit_obj, created = Unit.objects.get_or_create(
        pk=1, defaults={"name": "Payroll", "department": hr_dept_obj}
    )
    if created:
        print(f"Created Unit: {payroll_unit_obj.name}")
    else:
        print(f"Using existing Unit: {payroll_unit_obj.name}")

    network_unit_obj, created = Unit.objects.get_or_create(
        pk=2, defaults={"name": "Networking", "department": it_dept_obj}
    )
    if created:
        print(f"Created Unit: {network_unit_obj.name}")
    else:
        print(f"Using existing Unit: {network_unit_obj.name}")

    # Staff
    registry_staff_obj, created = Staff.objects.get_or_create(
        pk=1,
        defaults={
            "user": user_objs["registry_user"],
            "designation": officer_des_obj,
            "department": hr_dept_obj,
            "unit": payroll_unit_obj,
        },
    )
    if created:
        print(f"Created Staff: {registry_staff_obj.user.username}")
    else:
        print(f"Using existing Staff: {registry_staff_obj.user.username}")

    staff1_staff_obj, created = Staff.objects.get_or_create(
        pk=2,
        defaults={
            "user": user_objs["staff_user1"],
            "designation": officer_des_obj,
            "department": it_dept_obj,
            "unit": network_unit_obj,
        },
    )
    if created:
        print(f"Created Staff: {staff1_staff_obj.user.username}")
    else:
        print(f"Using existing Staff: {staff1_staff_obj.user.username}")

    staff2_staff_obj, created = Staff.objects.get_or_create(
        pk=3,
        defaults={
            "user": user_objs["staff_user2"],
            "designation": officer_des_obj,
            "department": it_dept_obj,
            "unit": network_unit_obj,
        },
    )
    if created:
        print(f"Created Staff: {staff2_staff_obj.user.username}")
    else:
        print(f"Using existing Staff: {staff2_staff_obj.user.username}")

    hod_staff_obj, created = Staff.objects.get_or_create(
        pk=4,
        defaults={
            "user": user_objs["hod_user"],
            "designation": director_des_obj,
            "department": hr_dept_obj,
            "unit": None,
        },
    )
    if created:
        print(f"Created Staff: {hod_staff_obj.user.username}")
    else:
        print(f"Using existing Staff: {hod_staff_obj.user.username}")

    manager_staff_obj, created = Staff.objects.get_or_create(
        pk=5,
        defaults={
            "user": user_objs["manager_user"],
            "designation": manager_des_obj,
            "department": it_dept_obj,
            "unit": network_unit_obj,
        },
    )
    if created:
        print(f"Created Staff: {manager_staff_obj.user.username}")
    else:
        print(f"Using existing Staff: {manager_staff_obj.user.username}")

    staff3_staff_obj, created = Staff.objects.get_or_create(
        pk=6,
        defaults={
            "user": user_objs["staff_user3"],
            "designation": officer_des_obj,
            "department": hr_dept_obj,
            "unit": payroll_unit_obj,
        },
    )
    if created:
        print(f"Created Staff: {staff3_staff_obj.user.username}")
    else:
        print(f"Using existing Staff: {staff3_staff_obj.user.username}")

    # Update Department and Unit Heads
    hr_dept_obj.head = hod_staff_obj
    hr_dept_obj.save()
    network_unit_obj.head = manager_staff_obj
    network_unit_obj.save()

    # Files (JSON generation)
    file1 = {
        "model": "document_management.file",
        "pk": 1,
        "fields": {
            "title": "INACTIVE TEST FILE",
            "file_number": "FMCAB/2025/PS/0001",
            "file_type": "personal",
            "department": it_dept_obj.pk,
            "status": "inactive",
            "owner": user_objs["staff_user1"].pk,
            "current_location": user_objs["staff_user1"].pk,
            "created_at": timezone.now().isoformat(),
        },
    }
    file2 = {
        "model": "document_management.file",
        "pk": 2,
        "fields": {
            "title": "PENDING ACTIVATION TEST FILE",
            "file_number": "FMCAB/2025/IT/0001",
            "file_type": "policy",
            "department": it_dept_obj.pk,
            "status": "pending_activation",
            "owner": user_objs["staff_user1"].pk,
            "current_location": user_objs["registry_user"].pk,
            "created_at": timezone.now().isoformat(),
        },
    }
    file3 = {
        "model": "document_management.file",
        "pk": 3,
        "fields": {
            "title": "ACTIVE FILE IN MOTION",
            "file_number": "FMCAB/2025/IT/0002",
            "file_type": "policy",
            "department": it_dept_obj.pk,
            "status": "active",
            "owner": user_objs["staff_user1"].pk,
            "current_location": user_objs["staff_user2"].pk,
            "created_at": timezone.now().isoformat(),
        },
    }
    fixtures.extend([file1, file2, file3])

    # Demo Document (JSON generation)
    demo_document = {
        "model": "document_management.document",
        "pk": 1,
        "fields": {
            "file": file1["pk"],
            "uploaded_by": user_objs["staff_user1"].pk,
            "uploaded_at": timezone.now().isoformat(),
            "minute_content": "This is a demo minute for the inactive test file.",
            "attachment": None,
        },
    }
    fixtures.append(demo_document)

    with open("pims_datamanagement/fixtures/initial_data.json", "w") as f:
        json.dump(fixtures, f, indent=4)


if __name__ == "__main__":
    create_fixtures()
