from django.db import migrations

HOD_DESIGNATION_ROLES = ("head of department", "hod", "director")


def _designation_implies_hod(designation_name):
    if not designation_name:
        return False
    lowered = designation_name.lower()
    return any(role in lowered for role in HOD_DESIGNATION_ROLES)


def configure_head_scope_permissions(apps, schema_editor):
    """Create the head-of-scope permissions and backfill them.

    ``can_head_department`` / ``can_head_unit`` replace the old positional
    ``is_hod`` / ``is_head_of_unit`` role checks: anyone who actually heads a
    department/unit (or holds an HOD-level designation) gets the matching
    permission, so every gate can be answered with ``user.has_perm``.
    """
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")
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

    dept_perm = perm("can_head_department")
    unit_perm = perm("can_head_unit")

    # Administrator holds the full user_management bundle.
    admin_group = Group.objects.filter(name="Administrator").first()
    if admin_group is not None:
        admin_group.permissions.add(dept_perm, unit_perm)

    for staff in Staff.objects.all().select_related("user", "designation"):
        if staff.user_id is None:
            continue
        wants_dept = Department.objects.filter(head=staff).exists() or _designation_implies_hod(
            staff.designation.name if staff.designation else None
        )
        wants_unit = Unit.objects.filter(head=staff).exists()
        if wants_dept:
            staff.user.user_permissions.add(dept_perm)
        else:
            staff.user.user_permissions.remove(dept_perm)
        if wants_unit:
            staff.user.user_permissions.add(unit_perm)
        else:
            staff.user.user_permissions.remove(unit_perm)


def remove_head_scope_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")

    try:
        user_ct = ContentType.objects.get(app_label="user_management", model="customuser")
    except ContentType.DoesNotExist:
        return
    for codename in ("can_head_department", "can_head_unit"):
        perm = Permission.objects.filter(codename=codename, content_type=user_ct).first()
        if perm is None:
            continue
        for group in Group.objects.all():
            group.permissions.remove(perm)
        perm.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("user_management", "0018_permission_based_groups"),
        ("organization", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="customuser",
            options={
                "permissions": [
                    ("can_set_urgent_priority", "Can mark documents as Urgent or High Priority"),
                    ("can_share_documents", "Can share documents with other users"),
                    (
                        "can_view_all_staff_files",
                        "Can view all staff files and personnel records regardless of department or custody",
                    ),
                    ("can_request_file_access", "Can request Read-Only access to files"),
                    ("can_request_file_access_rw", "Can request Read & Write access to files"),
                    ("can_approve_file_access", "Can approve or reject file access requests"),
                    (
                        "can_manage_registry",
                        "Can perform Registry operations (create files, manage lifecycle, approve access)",
                    ),
                    ("can_create_file", "Can create new files"),
                    ("can_manage_file_lifecycle", "Can activate, close and archive files"),
                    ("can_view_file", "Can view file details (subject to custody/scope)"),
                    ("can_view_file_content", "Can view document contents (subject to custody/scope)"),
                    ("can_add_document", "Can add a document/minute to a file"),
                    ("can_dispatch_document", "Can dispatch or forward a document to another staff member"),
                    ("can_delete_document", "Can delete a document"),
                    ("can_approve_document", "Can approve or reject documents"),
                    (
                        "can_supervise",
                        "Can supervise staff (HOD, head of unit/section/division, or flagged supervisor)",
                    ),
                    ("can_executive", "Has executive/MD level access across departments"),
                    ("can_head_department", "Heads a department (HOD scope)"),
                    ("can_head_unit", "Heads a unit (head-of-unit scope)"),
                ],
                "verbose_name": "user",
                "verbose_name_plural": "users",
            },
        ),
        migrations.RunPython(configure_head_scope_permissions, remove_head_scope_permissions),
    ]
