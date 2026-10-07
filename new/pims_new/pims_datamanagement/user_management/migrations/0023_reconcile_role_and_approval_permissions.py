"""DB-level permission reset for every existing account.

Signals only reconcile state from the moment a row is saved, and fixture
scripts only touch the database they build. Accounts that were created,
reassigned or edited before those rules landed can still be carrying stale
state: a Registry user without ``can_manage_registry``, a group still holding
the approval right, a head who lost the appointment but kept the permission.
This migration rebuilds that state in one pass, from the database up:

* role codenames on the role groups (Registry / Staff / Executives / MD /
  Supervisor / HOD-HOU / Administrator) — the same mapping the fixtures now
  install, minus ``can_approve_document``;
* ``can_approve_document``: stripped from every group, held only by staff
  whose designation marks them a final approver (Medical Director);
* ``can_head_department`` / ``can_head_unit`` recomputed from designations
  and current head appointments;
* Supervisor / HOD-HOU group membership recomputed so only current heads and
  flagged supervisors sit in them.

The designation role tuples below are copied from ``organization/models.py``
(``HOD_DESIGNATION_ROLES`` / ``FINAL_APPROVER_DESIGNATION_ROLES``) — a
migration must not import the live model module.
"""
from django.db import migrations

HOD_DESIGNATION_ROLES = ("head of department", "head of nursing", "hod", "director")
FINAL_APPROVER_DESIGNATION_ROLES = ("medical director",)

# Mirror of create_fixtures.py::GROUP_ROLE_PERMISSIONS and migration 0018,
# with can_approve_document deliberately absent (0021 made it person-based).
GROUP_ROLE_PERMISSIONS = {
    "Registry": [
        "can_manage_registry",
        "can_create_file",
        "can_manage_file_lifecycle",
        "can_approve_file_access",
        "can_view_file",
        "can_view_file_content",
        "can_add_document",
        "can_dispatch_document",
        "can_delete_document",
    ],
    "Staff": [
        "can_request_file_access",
        "can_view_file",
        "can_view_file_content",
        "can_add_document",
        "can_delete_document",
    ],
    "Executives": [
        "can_executive",
        "can_view_all_staff_files",
        "can_request_file_access",
        "can_request_file_access_rw",
        "can_view_file",
        "can_view_file_content",
        "can_add_document",
        "can_dispatch_document",
        "can_delete_document",
        "can_share_documents",
        "can_set_urgent_priority",
    ],
    "Supervisor": [
        "can_request_file_access",
        "can_request_file_access_rw",
        "can_view_file",
        "can_add_document",
        "can_dispatch_document",
        "can_delete_document",
        "can_supervise",
        "can_share_documents",
        "can_set_urgent_priority",
    ],
    "HOD/HOU": [
        "can_request_file_access",
        "can_request_file_access_rw",
        "can_view_file",
        "can_add_document",
        "can_dispatch_document",
        "can_delete_document",
        "can_supervise",
        "can_share_documents",
        "can_set_urgent_priority",
    ],
}
GROUP_ROLE_PERMISSIONS["MD"] = GROUP_ROLE_PERMISSIONS["Executives"]


def _implies(designation, roles):
    if designation is None or not designation.name:
        return False
    lowered = designation.name.lower()
    return any(role in lowered for role in roles)


def reconcile_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomUser = apps.get_model("user_management", "CustomUser")
    Staff = apps.get_model("organization", "Staff")
    Department = apps.get_model("organization", "Department")
    Unit = apps.get_model("organization", "Unit")

    user_ct = ContentType.objects.get(app_label="user_management", model="customuser")

    def perm(codename):
        p, _ = Permission.objects.get_or_create(
            codename=codename,
            content_type=user_ct,
            defaults={"name": codename.replace("_", " ").title()},
        )
        return p

    # --- 1. Role codenames on the role groups ------------------------------
    for name, codenames in GROUP_ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=name)
        for codename in codenames:
            group.permissions.add(perm(codename))
    # 0018 also accepted the singular "Executive" spelling.
    executive_group = Group.objects.filter(name="Executive").first()
    if executive_group:
        for codename in GROUP_ROLE_PERMISSIONS["Executives"]:
            executive_group.permissions.add(perm(codename))
    # Administrator keeps every user_management permission, including any
    # created after 0018 ran.
    admin_group, _ = Group.objects.get_or_create(name="Administrator")
    for p in Permission.objects.filter(content_type__app_label="user_management"):
        admin_group.permissions.add(p)

    # --- 2. Approval right: Medical Director only -------------------------
    approve_perm = Permission.objects.get(
        codename="can_approve_document", content_type=user_ct
    )
    for group in Group.objects.all():
        group.permissions.remove(approve_perm)

    approver_ids = {
        staff.user_id
        for staff in Staff.objects.select_related("designation")
        if staff.user_id and _implies(staff.designation, FINAL_APPROVER_DESIGNATION_ROLES)
    }
    for user in CustomUser.objects.filter(user_permissions=approve_perm):
        if user.pk not in approver_ids:
            user.user_permissions.remove(approve_perm)
    for user in CustomUser.objects.filter(pk__in=approver_ids):
        user.user_permissions.add(approve_perm)

    # --- 3. Head-of-scope permissions, recomputed --------------------------
    dept_head_ids = set(
        Department.objects.exclude(head__isnull=True).values_list("head_id", flat=True)
    )
    unit_head_ids = set(
        Unit.objects.exclude(head__isnull=True).values_list("head_id", flat=True)
    )

    def sync_user_perm(desired_ids, codename):
        p = perm(codename)
        current_ids = set(
            CustomUser.objects.filter(user_permissions=p).values_list("pk", flat=True)
        )
        for user in CustomUser.objects.filter(
            pk__in=desired_ids - current_ids
        ).iterator():
            user.user_permissions.add(p)
        for user in CustomUser.objects.filter(
            pk__in=current_ids - desired_ids
        ).iterator():
            user.user_permissions.remove(p)

    hod_user_ids = set()
    unit_user_ids = set()
    for staff in Staff.objects.select_related("designation", "user"):
        if not staff.user_id:
            continue
        if _implies(staff.designation, HOD_DESIGNATION_ROLES) or staff.pk in dept_head_ids:
            hod_user_ids.add(staff.user_id)
        if staff.pk in unit_head_ids:
            unit_user_ids.add(staff.user_id)
    sync_user_perm(hod_user_ids, "can_head_department")
    sync_user_perm(unit_user_ids, "can_head_unit")

    # --- 4. Supervisor / HOD-HOU membership, recomputed --------------------
    supervisor_group, _ = Group.objects.get_or_create(name="Supervisor")
    hod_group, _ = Group.objects.get_or_create(name="HOD/HOU")
    heads_now = dept_head_ids | unit_head_ids
    for staff in Staff.objects.select_related("user").iterator():
        if not staff.user_id:
            continue
        user = staff.user
        if bool(staff.is_supervisor) or staff.pk in heads_now:
            user.groups.add(supervisor_group)
        else:
            user.groups.remove(supervisor_group)
        if staff.pk in heads_now:
            user.groups.add(hod_group)
        else:
            user.groups.remove(hod_group)


def reverse_reconcile(apps, schema_editor):
    """Forward-only: permission state is owned by signals and fixtures.

    Undoing this reconciliation would strip grants that were already correct
    before it ran, so reversing does nothing.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("user_management", "0022_alter_customuser_options"),
        ("organization", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(reconcile_permissions, reverse_reconcile),
    ]
