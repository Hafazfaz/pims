import contextlib
import os
import random
from datetime import timedelta

import django

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pims_datamanagement.settings")
django.setup()

from audit_log.models import AuditLogEntry  # noqa: E402
from django.contrib.auth.models import Group, Permission  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.utils import timezone  # noqa: E402
from document_management.models import Document, File, FileAccessRequest  # noqa: E402
from notifications.models import Notification  # noqa: E402
from organization.models import Department, Designation, Staff, StaffSignature, Unit  # noqa: E402
from user_management.models import CustomUser  # noqa: E402

# --- Helpers ---

DEPARTMENTS_DATA = [
    {"name": "Human Resources", "code": "HR"},
    {"name": "Information Technology", "code": "IT"},
    {"name": "Finance", "code": "FIN"},
    {"name": "Operations", "code": "OPS"},
    {"name": "Legal", "code": "LEG"},
]

UNITS_DATA = {
    "HR": ["Payroll", "Recruitment", "Employee Relations"],
    "IT": ["Networking", "Development", "Support"],
    "FIN": ["Accounts", "Budgeting", "Audit"],
    "OPS": ["Logistics", "Maintenance"],
    "LEG": ["Compliance", "Contracts"],
}

DESIGNATIONS_DATA = [
    {"name": "Medical Director", "level": 1},
    {"name": "Director", "level": 1},
    {"name": "Director of Admin", "level": 1},
    {"name": "Director of Nursing", "level": 1},
    {"name": "Head of Clinical Service", "level": 2},
    {"name": "Head of Accounts", "level": 2},
    {"name": "Deputy Director", "level": 2},
    {"name": "Assistant Director", "level": 3},
    {"name": "Chief Officer", "level": 4},
    {"name": "Principal Officer", "level": 5},
    {"name": "Senior Officer", "level": 6},
    {"name": "Officer I", "level": 7},
    {"name": "Officer II", "level": 8},
]

# Default leadership accounts created by the fixture script.
# Each tuple: (username, first_name, last_name, designation_name, department_code, group_name)
DEFAULT_LEADERSHIP_USERS = [
    ("medical_director", "Medical", "Director", "Medical Director", "OPS", "Executives"),
    ("director_admin", "Director", "Admin", "Director of Admin", "OPS", "Executives"),
    ("director_nursing", "Director", "Nursing", "Director of Nursing", "HR", "Executives"),
    ("head_clinical", "Head", "Clinical Service", "Head of Clinical Service", "OPS", "Staff"),
    ("head_accounts", "Head", "Accounts", "Head of Accounts", "FIN", "Staff"),
]

FIRST_NAMES = [
    "James",
    "Mary",
    "John",
    "Patricia",
    "Robert",
    "Jennifer",
    "Michael",
    "Linda",
    "William",
    "Elizabeth",
    "David",
    "Barbara",
    "Richard",
    "Susan",
    "Joseph",
    "Jessica",
    "Thomas",
    "Sarah",
    "Charles",
    "Karen",
]
LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Hernandez",
    "Lopez",
    "Gonzalez",
    "Wilson",
    "Anderson",
    "Thomas",
    "Taylor",
    "Moore",
    "Jackson",
    "Martin",
]

FILE_TITLES = [
    "ANNUAL BUDGET REPORT",
    "STAFF RECRUITMENT 2025",
    "IT INFRASTRUCTURE UPGRADE",
    "SERVER MAINTENANCE LOGS",
    "LEGAL COMPLIANCE REVIEW",
    "OFFICE RENOVATION PLANS",
    "QUARTERLY FINANCIAL AUDIT",
    "EMPLOYEE TRAINING PROGRAM",
    "NEW POLICY IMPLEMENTATION",
    "VENDOR CONTRACTS 2025",
    "SECURITY PROTOCOLS UPDATE",
    "CLIENT FEEDBACK ANALYSIS",
    "PROJECT PHOENIX BLUEPRINT",
    "SOFTWARE LICENSE RENEWALS",
    "DISASTER RECOVERY PLAN",
]


def get_random_date(start_date=None, end_date=None):
    if not start_date:
        start_date = timezone.now() - timedelta(days=365)
    if not end_date:
        end_date = timezone.now()
    delta = end_date - start_date
    if delta.days <= 0:
        return start_date
    random_days = random.randrange(delta.days)
    return start_date + timedelta(days=random_days)


def assign_organization_heads(departments, units):
    """Fill in Department.head / Unit.head for rows that don't have one.

    Both ``head`` fields are OneToOneFields, so a Staff member can head at
    most ONE department and at most ONE unit. Real databases often contain
    staff whose ``Staff.unit`` differs from the unit they already head
    (e.g. set via the admin), so we explicitly skip anyone who already heads
    a department/unit instead of blindly picking the first candidate —
    otherwise this raises IntegrityError: UNIQUE constraint failed on
    organization_unit.head_id.
    """
    taken_dept_heads = set(Department.objects.exclude(head=None).values_list("head_id", flat=True))
    for dept in departments.values():
        if dept.head_id:
            taken_dept_heads.add(dept.head_id)
            continue
        head = (
            Staff.objects.filter(department=dept, designation__level__lte=3)
            .exclude(pk__in=taken_dept_heads)
            .order_by("pk")
            .first()
        )
        if head:
            dept.head = head
            dept.save()
            taken_dept_heads.add(head.pk)

    taken_unit_heads = set(Unit.objects.exclude(head=None).values_list("head_id", flat=True))
    for unit in units:
        if unit.head_id:
            taken_unit_heads.add(unit.head_id)
            continue
        head = (
            Staff.objects.filter(unit=unit, designation__level__lte=6)
            .exclude(pk__in=taken_unit_heads)
            .order_by("pk")
            .first()
        )
        if head:
            unit.head = head
            unit.save()
            taken_unit_heads.add(head.pk)
        else:
            print(f"  No eligible head available for unit {unit.name} (all candidates already head something)")


def create_fixtures():
    print("--- Starting Fixture Generation ---")

    # --- Groups & Permissions (Keep existing logic but optimized) ---
    print("Setting up Permissions and Groups...")

    # Define models for standard permissions
    models_perm = [
        CustomUser,
        Department,
        Unit,
        Designation,
        Staff,
        File,
        Document,
        FileAccessRequest,
        AuditLogEntry,
        Notification,
    ]

    perms_list = []
    for model in models_perm:
        ct = ContentType.objects.get_for_model(model)
        for action in ["add", "change", "delete", "view"]:
            codename = f"{action}_{model.__name__.lower()}"
            with contextlib.suppress(Permission.DoesNotExist):
                perms_list.append(Permission.objects.get(content_type=ct, codename=codename))

    # Custom perms
    custom_perms = [
        ("document_management", "file", "activate_file"),
        ("document_management", "file", "create_file"),
        ("document_management", "file", "send_file"),
        ("document_management", "file", "close_file"),
        ("document_management", "file", "archive_file"),
        ("document_management", "document", "add_minute"),
        ("document_management", "document", "add_attachment"),
        ("document_management", "document", "view_staff_documents"),
    ]

    for app, model, codename in custom_perms:
        try:
            ct = ContentType.objects.get(app_label=app, model=model)
            perms_list.append(Permission.objects.get(content_type=ct, codename=codename))
        except (ContentType.DoesNotExist, Permission.DoesNotExist):
            print(f"Warning: Permission {codename} not found")

    # Groups
    registry_group, _ = Group.objects.get_or_create(name="Registry")
    staff_group, _ = Group.objects.get_or_create(name="Staff")
    executives_group, _ = Group.objects.get_or_create(name="Executives")

    # Assign all gathered perms for simplicity in dev — EXCEPT view_staff_documents,
    # which Registry must never hold (Registry cannot see staff personnel documents,
    # not even titles/metadata).
    registry_perms = [p for p in perms_list if p.codename != "view_staff_documents"]
    registry_group.permissions.set(registry_perms)
    staff_group.permissions.set(perms_list)
    executives_group.permissions.set(perms_list)

    # --- Organization Structure ---
    print("Creating Organization Structure...")
    departments = {}
    for d_data in DEPARTMENTS_DATA:
        dept, _created = Department.objects.get_or_create(code=d_data["code"], defaults={"name": d_data["name"]})
        departments[d_data["code"]] = dept

    units = []
    for dept_code, unit_names in UNITS_DATA.items():
        dept = departments[dept_code]
        for u_name in unit_names:
            unit, _ = Unit.objects.get_or_create(department=dept, name=u_name)
            units.append(unit)

    designations = []
    for des_data in DESIGNATIONS_DATA:
        des, _ = Designation.objects.get_or_create(name=des_data["name"], defaults={"level": des_data["level"]})
        designations.append(des)

    # --- Users & Staff ---
    print("Creating Users and Staff...")
    users = []
    staff_members = []

    # Create Admin
    admin_user, _ = CustomUser.objects.get_or_create(
        username="admin",
        defaults={
            "is_superuser": True,
            "is_staff": True,
            "email": "admin@example.com",
            "first_name": "Super",
            "last_name": "Admin",
        },
    )
    admin_user.set_password("password123")
    admin_user.save()

    # Create users
    def create_user_staff(username, first, last, group, dept, unit, designation):
        user, created = CustomUser.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@example.com",
                "first_name": first,
                "last_name": last,
                "is_staff": (group.name == "Executives" or username == "admin"),
            },
        )
        if created:
            user.set_password("password123")
            user.save()

        user.groups.add(group)

        staff, _s_created = Staff.objects.get_or_create(
            user=user,
            defaults={
                "department": dept,
                "unit": unit,
                "designation": designation,
                "phone_number": f"555-{random.randint(1000, 9999)}",
            },
        )
        return user, staff

    reg_user, reg_staff = create_user_staff(
        "registry", "Registry", "Officer", registry_group, departments["HR"], units[0], designations[6]
    )
    staff_members.append(reg_staff)
    users.append(reg_user)

    # Create a signature for registry officer
    if not reg_staff.get_active_signature():
        StaffSignature.objects.create(
            staff=reg_staff,
            image="signatures/verified/registry_sig.png",  # Placeholder path
            is_active=True,
            is_verified=True,
        )

    # --- Default Leadership Users ---
    print("Creating Default Leadership Users...")
    designation_map = {d.name: d for d in designations}
    group_map = {
        "Registry": registry_group,
        "Staff": staff_group,
        "Executives": executives_group,
    }

    for username, first, last, des_name, dept_code, group_name in DEFAULT_LEADERSHIP_USERS:
        designation = designation_map.get(des_name)
        if not designation:
            print(f"  Warning: designation '{des_name}' not found, skipping {username}")
            continue

        dept = departments.get(dept_code)
        if not dept:
            print(f"  Warning: department '{dept_code}' not found, skipping {username}")
            continue

        group = group_map.get(group_name)
        unit = Unit.objects.filter(department=dept).first()

        user, staff = create_user_staff(
            username, first, last, group, dept, unit, designation
        )
        staff.is_supervisor = True
        staff.save()

        # Auto-verify signature for leadership users
        if not staff.get_active_signature():
            StaffSignature.objects.create(
                staff=staff,
                image=f"signatures/verified/{username}_sig.png",
                is_active=True,
                is_verified=True,
            )

        users.append(user)
        staff_members.append(staff)
        print(f"  Created {username} ({des_name})")

    # Random Staff
    for i in range(25):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        username = f"{first.lower()}.{last.lower()}{i}"
        dept_code = random.choice(list(departments.keys()))
        dept = departments[dept_code]
        # Pick a unit from that dept
        dept_units = Unit.objects.filter(department=dept)
        unit = random.choice(dept_units) if dept_units.exists() else None

        # Random designation (weighted towards lower levels)
        des = random.choice(designations[4:] + designations[4:] + designations[:4])  # more officers than directors

        # If high level, assign to Executives
        target_group = executives_group if des.level <= 2 else staff_group

        u, s = create_user_staff(username, first, last, target_group, dept, unit, des)
        users.append(u)
        staff_members.append(s)

    # Assign Heads
    assign_organization_heads(departments, units)

    # Create signatures for HODs
    for dept in departments.values():
        if dept.head:
            StaffSignature.objects.get_or_create(
                staff=dept.head,
                is_active=True,
                defaults={"image": f"signatures/verified/hod_{dept.code.lower()}.png", "is_verified": True},
            )

    # Pre-calculate HODs and Unit Managers for file sending/location
    heads_of_department = [dept.head for dept in departments.values() if dept.head]
    unit_managers = [unit.head for unit in units if unit.head]
    all_heads = list(set(heads_of_department + unit_managers))

    # --- Files & Documents ---
    print("Creating Files and Documents...")
    all_files = []

    # === PERSONAL FOLDERS (1:1 with Staff) ===
    print("Creating Personal Folders...")
    for staff in staff_members:
        # Registry officers cannot be personal file owners
        if staff.is_registry:
            print(f"  Skipping {staff.user.username} - registry staff cannot own personal folders")
            continue
        # Check if personal folder already exists for this staff
        existing_personal = File.objects.filter(file_type="personal", owner=staff).first()
        if existing_personal:
            print(f"  Skipping {staff.user.username} - personal folder already exists")
            all_files.append(existing_personal)
            continue

        # status distribution for personal folders
        status = random.choices(["inactive", "active", "closed"], weights=[15, 75, 10], k=1)[0]

        title = f"PERSONNEL RECORD - {staff.user.get_full_name().upper()}"

        file_obj = File(
            title=title,
            file_type="personal",
            department=staff.department,
            status=status,
            owner=staff,
            created_by=reg_user,  # Registry creates personal folders
            created_at=get_random_date(),
        )

        # logic for location
        if status == "active":
            file_obj.current_location = staff  # Owner has their own folder when active
        elif status == "inactive":
            file_obj.current_location = reg_staff  # Registry holds inactive
        else:  # closed
            file_obj.current_location = reg_staff

        file_obj.save()
        all_files.append(file_obj)

        # Audit Log for creation
        AuditLogEntry.objects.create(
            action="FILE_CREATED",
            user=reg_user,
            content_object=file_obj,
            timestamp=file_obj.created_at,
            details={"title": title},
        )

    # === POLICY FOLDERS (Departmental) ===
    print("Creating Policy Folders...")
    for _i in range(15):
        dept_code = random.choice(list(departments.keys()))
        dept = departments[dept_code]

        # status distribution
        status = random.choices(["inactive", "active", "closed", "archived"], weights=[10, 65, 15, 10], k=1)[0]

        title = f"{random.choice(FILE_TITLES)} - {dept.code}"

        file_obj = File(
            title=title,
            file_type="policy",
            department=dept,
            status=status,
            owner=None,  # Policy folders don't have an owner
            created_by=reg_user,
            created_at=get_random_date(),
        )

        # logic for location
        if status == "active":
            file_obj.current_location = random.choice(all_heads)
        elif status == "inactive":
            file_obj.current_location = reg_staff

        file_obj.save()
        all_files.append(file_obj)

        # Audit Log for creation
        AuditLogEntry.objects.create(
            action="FILE_CREATED",
            user=reg_user,
            content_object=file_obj,
            timestamp=file_obj.created_at,
            details={"title": title},
        )

    # === POLICY FOLDERS (External Parties) ===
    print("Creating External Policy Folders...")
    external_parties = [
        "Ministry of Health",
        "World Health Organization",
        "Ministry of Finance",
        "Federal Audit Commission",
        "National Bureau of Statistics",
    ]

    for party in external_parties:
        status = random.choices(["inactive", "active", "closed"], weights=[20, 70, 10], k=1)[0]

        title = f"EXTERNAL POLICY - {party.upper()}"

        # Assign to a random department
        dept = random.choice(list(departments.values()))

        file_obj = File(
            title=title,
            file_type="policy",
            department=dept,
            external_party=party,
            status=status,
            owner=None,
            created_by=reg_user,
            created_at=get_random_date(),
        )

        if status == "active":
            file_obj.current_location = random.choice(all_heads)
        else:
            file_obj.current_location = reg_staff

        file_obj.save()
        all_files.append(file_obj)

        # Audit Log for creation
        AuditLogEntry.objects.create(
            action="FILE_CREATED",
            user=reg_user,
            content_object=file_obj,
            timestamp=file_obj.created_at,
            details={"title": title, "external_party": party},
        )

    # === ACCESS REQUESTS ===
    print("Creating Access Requests...")
    for file_obj in random.sample(all_files, min(10, len(all_files))):
        if file_obj.status == "active":
            requester = random.choice(users)
            FileAccessRequest.objects.create(
                file=file_obj,
                requested_by=requester,
                reason="Need to review for compliance audit.",
                status=random.choice(["pending", "approved", "rejected"]),
                created_at=timezone.now(),
            )

    # === DOCUMENTS (Minutes & Attachments) ===
    print("Creating Documents...")

    # Document titles for minutes/signals
    document_titles = [
        "LEAVE APPLICATION REQUEST",
        "MONTHLY PROGRESS REPORT",
        "MEETING MINUTES",
        "TRAINING REQUEST",
        "BUDGET PROPOSAL",
        "PROJECT UPDATE",
        "INTERNAL MEMO",
        "POLICY REVIEW NOTES",
    ]

    # Personnel document titles for personal folders
    personnel_docs = [
        "Birth Certificate",
        "O-Level Certificate",
        "BSc Degree Certificate",
        "MSc Degree Certificate",
        "Employment Letter",
        "Annual Appraisal",
        "Promotion Letter",
        "Medical Certificate",
    ]

    for file_obj in all_files:
        # For personal folders, add some official personnel documents uploaded by Registry
        if file_obj.file_type == "personal" and random.random() > 0.3:
            num_personnel_docs = random.randint(1, 4)
            for _ in range(num_personnel_docs):
                doc_title = random.choice(personnel_docs)
                doc_date = get_random_date(start_date=file_obj.created_at)

                Document.objects.create(
                    file=file_obj,
                    uploaded_by=reg_user,  # Registry uploads official docs
                    uploaded_at=doc_date,
                    title=doc_title,
                    minute_content=None,  # No content, just the attachment reference
                )

        # Add minutes/signals to active folders
        if file_obj.status == "active":
            num_docs = random.randint(1, 5)

            for j in range(num_docs):
                minute_user = random.choice(staff_members).user
                doc_date = get_random_date(start_date=file_obj.created_at)

                # Determine if this document should be signed
                signature_record = None
                has_signature = False
                staff_obj = minute_user.staff if hasattr(minute_user, "staff") else None
                if staff_obj and (staff_obj.is_registry or staff_obj.is_hod or staff_obj.is_unit_manager):
                    signature_record = staff_obj.get_active_signature()
                    if signature_record:
                        has_signature = True

                doc = Document.objects.create(
                    file=file_obj,
                    uploaded_by=minute_user,
                    uploaded_at=doc_date,
                    title=random.choice(document_titles) if random.random() > 0.3 else None,
                    minute_content=(
                        f"Minute {j + 1}: Reviewed the contents of this file. "
                        f"Action required regarding section {random.randint(1, 10)}."
                    ),
                    has_signature=has_signature,
                    signature_record=signature_record,
                )

                AuditLogEntry.objects.create(
                    action="DOCUMENT_ADDED", user=minute_user, content_object=doc, timestamp=doc_date
                )

                # Random Notifications
                if file_obj.owner and random.random() < 0.3:
                    Notification.objects.create(
                        user=file_obj.owner.user,
                        message=f"New entry added to folder {file_obj.file_number} by {minute_user.username}",
                        content_object=doc,
                        timestamp=doc_date,
                    )

    print(f"Created {len(users)} users.")
    print(f"Created {len(staff_members)} staff members.")
    print(f"Created {len(all_files)} files.")
    print("--- Fixture Generation Complete ---")


if __name__ == "__main__":
    create_fixtures()
