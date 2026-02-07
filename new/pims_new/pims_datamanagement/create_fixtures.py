import os
import random
from datetime import timedelta

import django

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pims_datamanagement.settings")
django.setup()

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from document_management.models import Document, File, FileAccessRequest
from organization.models import Department, Designation, Staff, StaffSignature, Unit
from user_management.models import CustomUser
from audit_log.models import AuditLogEntry
from notifications.models import Notification

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
    {"name": "Director", "level": 1},
    {"name": "Deputy Director", "level": 2},
    {"name": "Assistant Director", "level": 3},
    {"name": "Chief Officer", "level": 4},
    {"name": "Principal Officer", "level": 5},
    {"name": "Senior Officer", "level": 6},
    {"name": "Officer I", "level": 7},
    {"name": "Officer II", "level": 8},
]

FIRST_NAMES = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]

FILE_TITLES = [
    "ANNUAL BUDGET REPORT", "STAFF RECRUITMENT 2025", "IT INFRASTRUCTURE UPGRADE",
    "SERVER MAINTENANCE LOGS", "LEGAL COMPLIANCE REVIEW", "OFFICE RENOVATION PLANS",
    "QUARTERLY FINANCIAL AUDIT", "EMPLOYEE TRAINING PROGRAM", "NEW POLICY IMPLEMENTATION",
    "VENDOR CONTRACTS 2025", "SECURITY PROTOCOLS UPDATE", "CLIENT FEEDBACK ANALYSIS",
    "PROJECT PHOENIX BLUEPRINT", "SOFTWARE LICENSE RENEWALS", "DISASTER RECOVERY PLAN",
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

def create_fixtures():
    print("--- Starting Fixture Generation ---")

    # --- Groups & Permissions (Keep existing logic but optimized) ---
    print("Setting up Permissions and Groups...")
    
    # Define models for standard permissions
    models_perm = [
        CustomUser, Department, Unit, Designation, Staff, File, Document, 
        FileAccessRequest, AuditLogEntry, Notification
    ]
    
    perms_list = []
    for model in models_perm:
        ct = ContentType.objects.get_for_model(model)
        for action in ["add", "change", "delete", "view"]:
            codename = f"{action}_{model.__name__.lower()}"
            try:
                perms_list.append(Permission.objects.get(content_type=ct, codename=codename))
            except Permission.DoesNotExist:
                pass # Some models might not have all standard perms or differently named

    # Custom perms
    custom_perms = [
        ("document_management", "file", "activate_file"),
        ("document_management", "file", "create_file"),
        ("document_management", "file", "send_file"),
        ("document_management", "file", "close_file"),
        ("document_management", "file", "archive_file"),
        ("document_management", "document", "add_minute"),
        ("document_management", "document", "add_attachment"),
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
    
    # Assign all gathered perms to both for simplicity in dev (refine as needed)
    registry_group.permissions.set(perms_list)
    staff_group.permissions.set(perms_list)
    executives_group.permissions.set(perms_list)


    # --- Organization Structure ---
    print("Creating Organization Structure...")
    departments = {}
    for d_data in DEPARTMENTS_DATA:
        dept, created = Department.objects.get_or_create(
            code=d_data["code"], defaults={"name": d_data["name"]}
        )
        departments[d_data["code"]] = dept
    
    units = []
    for dept_code, unit_names in UNITS_DATA.items():
        dept = departments[dept_code]
        for u_name in unit_names:
            unit, _ = Unit.objects.get_or_create(department=dept, name=u_name)
            units.append(unit)

    designations = []
    for des_data in DESIGNATIONS_DATA:
        des, _ = Designation.objects.get_or_create(
            name=des_data["name"], defaults={"level": des_data["level"]}
        )
        designations.append(des)

    # --- Users & Staff ---
    print("Creating Users and Staff...")
    users = []
    staff_members = []
    
    # Create Admin
    admin_user, _ = CustomUser.objects.get_or_create(
        username="admin", 
        defaults={
            "is_superuser": True, "is_staff": True, "email": "admin@example.com",
            "first_name": "Super", "last_name": "Admin"
        }
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
                "is_staff": (group.name == "Executives" or username == "admin")
            }
        )
        if created:
            user.set_password("password123")
            user.save()
        
        user.groups.add(group)
        
        staff, s_created = Staff.objects.get_or_create(
            user=user,
            defaults={
                "department": dept,
                "unit": unit,
                "designation": designation,
                "phone_number": f"555-{random.randint(1000, 9999)}"
            }
        )
        return user, staff

    reg_user, reg_staff = create_user_staff("registry", "Registry", "Officer", registry_group, departments["HR"], units[0], designations[6])
    staff_members.append(reg_staff)
    users.append(reg_user)

    # Create a signature for registry officer
    StaffSignature.objects.create(
        staff=reg_staff,
        image="signatures/verified/registry_sig.png", # Placeholder path
        is_active=True,
        is_verified=True
    )

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
        des = random.choice(designations[4:] + designations[4:] + designations[:4]) # more officers than directors
        
        # If high level, assign to Executives
        target_group = executives_group if des.level <= 2 else staff_group
        
        u, s = create_user_staff(username, first, last, target_group, dept, unit, des)
        users.append(u)
        staff_members.append(s)

    # Assign Heads
    for dept in departments.values():
        if not dept.head:
            # Find a high ranking staff in this dept
            potential_heads = Staff.objects.filter(department=dept, designation__level__lte=3)
            if potential_heads.exists():
                dept.head = potential_heads.first()
                dept.save()

    for unit in units:
        if not unit.head:
            potential_heads = Staff.objects.filter(unit=unit, designation__level__lte=6)
            if potential_heads.exists():
                unit.head = potential_heads.first()
                unit.save()
    
    # Create signatures for HODs
    for dept in departments.values():
        if dept.head:
            StaffSignature.objects.get_or_create(
                staff=dept.head,
                is_active=True,
                defaults={
                    "image": f"signatures/verified/hod_{dept.code.lower()}.png",
                    "is_verified": True
                }
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
        # Check if personal folder already exists for this staff
        existing_personal = File.objects.filter(file_type="personal", owner=staff).first()
        if existing_personal:
            print(f"  Skipping {staff.user.username} - personal folder already exists")
            all_files.append(existing_personal)
            continue
        
        # status distribution for personal folders
        status = random.choices(
            ["inactive", "pending_activation", "active", "closed"],
            weights=[15, 10, 65, 10], 
            k=1
        )[0]
        
        title = f"PERSONNEL RECORD - {staff.user.get_full_name().upper()}"
        
        file_obj = File(
            title=title,
            file_type="personal",
            department=staff.department,
            status=status,
            owner=staff,
            created_by=reg_user,  # Registry creates personal folders
            created_at=get_random_date()
        )
        
        # logic for location
        if status == "active":
            file_obj.current_location = staff  # Owner has their own folder when active
        elif status in ["inactive", "pending_activation"]:
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
            details={"title": title}
        )

    # === POLICY FOLDERS (Departmental) ===
    print("Creating Policy Folders...")
    for i in range(15):
        dept_code = random.choice(list(departments.keys()))
        dept = departments[dept_code]
        
        # status distribution
        status = random.choices(
            ["inactive", "pending_activation", "active", "closed", "archived"],
            weights=[10, 5, 60, 15, 10], 
            k=1
        )[0]
        
        title = f"{random.choice(FILE_TITLES)} - {dept.code}"
        
        file_obj = File(
            title=title,
            file_type="policy",
            department=dept,
            status=status,
            owner=None,  # Policy folders don't have an owner
            created_by=reg_user,
            created_at=get_random_date()
        )
        
        # logic for location
        if status == "active":
            file_obj.current_location = random.choice(all_heads)
        elif status in ["inactive", "pending_activation"]:
            file_obj.current_location = reg_staff
        
        file_obj.save()
        all_files.append(file_obj)

        # Audit Log for creation
        AuditLogEntry.objects.create(
            action="FILE_CREATED",
            user=reg_user,
            content_object=file_obj,
            timestamp=file_obj.created_at,
            details={"title": title}
        )

    # === POLICY FOLDERS (External Parties) ===
    print("Creating External Policy Folders...")
    external_parties = [
        "Ministry of Health",
        "World Health Organization", 
        "Ministry of Finance",
        "Federal Audit Commission",
        "National Bureau of Statistics"
    ]
    
    for party in external_parties:
        status = random.choices(
            ["inactive", "active", "closed"],
            weights=[20, 70, 10], 
            k=1
        )[0]
        
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
            created_at=get_random_date()
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
            details={"title": title, "external_party": party}
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
                status=random.choice(['pending', 'approved', 'rejected']),
                created_at=timezone.now()
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
        "POLICY REVIEW NOTES"
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
        "Medical Certificate"
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
                staff_obj = minute_user.staff if hasattr(minute_user, 'staff') else None
                if staff_obj and (staff_obj.is_registry or staff_obj.is_hod or staff_obj.is_unit_manager):
                    signature_record = staff_obj.get_active_signature()
                    if signature_record:
                        has_signature = True

                doc = Document.objects.create(
                    file=file_obj,
                    uploaded_by=minute_user,
                    uploaded_at=doc_date,
                    title=random.choice(document_titles) if random.random() > 0.3 else None,
                    minute_content=f"Minute {j+1}: Reviewed the contents of this file. Action required regarding section {random.randint(1, 10)}.",
                    has_signature=has_signature,
                    signature_record=signature_record
                )
                
                AuditLogEntry.objects.create(
                    action="DOCUMENT_ADDED",
                    user=minute_user,
                    content_object=doc,
                    timestamp=doc_date
                )
                
                # Random Notifications
                if file_obj.owner and random.random() < 0.3:
                    Notification.objects.create(
                        user=file_obj.owner.user,
                        message=f"New entry added to folder {file_obj.file_number} by {minute_user.username}",
                    content_object=doc,
                    timestamp=doc_date
                )

    print(f"Created {len(users)} users.")
    print(f"Created {len(staff_members)} staff members.")
    print(f"Created {len(all_files)} files.")
    print("--- Fixture Generation Complete ---")

if __name__ == "__main__":
    create_fixtures()
