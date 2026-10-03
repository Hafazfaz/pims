from django.db import migrations


def configure_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Staff = apps.get_model("organization", "Staff")

    user_ct = ContentType.objects.get(app_label="user_management", model="customuser")

    def perm(codename):
        p, _ = Permission.objects.get_or_create(
            codename=codename,
            content_type=user_ct,
            defaults={"name": codename.replace("_", " ").title()},
        )
        return p

    supervisor_group, _ = Group.objects.get_or_create(name="Supervisor")

    groups = {}
    for name in ["Administrator", "Registry", "HOD/HOU", "Staff", "Executives", "MD"]:
        try:
            groups[name] = Group.objects.get(name=name)
        except Group.DoesNotExist:
            groups[name] = Group.objects.create(name=name)

    # Supervisor-level capabilities (HOD/HOU/flagged supervisors)
    supervisor_perms = [
        "can_request_file_access",
        "can_request_file_access_rw",
        "can_view_file",
        "can_add_document",
        "can_dispatch_document",
        "can_approve_document",
        "can_delete_document",
        "can_supervise",
        "can_share_documents",
        "can_set_urgent_priority",
    ]
    for codename in supervisor_perms:
        supervisor_group.permissions.add(perm(codename))

    # HOD/HOU is the role-identity group; it should carry the same permissions.
    for codename in supervisor_perms:
        groups["HOD/HOU"].permissions.add(perm(codename))

    # Staff group: read-only requests and basic document operations on their own files.
    staff_perms = [
        "can_request_file_access",
        "can_view_file",
        "can_view_file_content",
        "can_add_document",
        "can_delete_document",
    ]
    for codename in staff_perms:
        groups["Staff"].permissions.add(perm(codename))

    # Registry: custody management + access approvals (no content viewing by design).
    registry_perms = [
        "can_manage_registry",
        "can_create_file",
        "can_manage_file_lifecycle",
        "can_approve_file_access",
        "can_view_file",
        "can_view_file_content",
        "can_add_document",
        "can_dispatch_document",
        "can_delete_document",
        "can_approve_document",
    ]
    for codename in registry_perms:
        groups["Registry"].permissions.add(perm(codename))

    # Executives and MD (accept both "Executive" and "Executives" group names)
    exec_perms = [
        "can_executive",
        "can_view_all_staff_files",
        "can_request_file_access",
        "can_request_file_access_rw",
        "can_view_file",
        "can_view_file_content",
        "can_add_document",
        "can_dispatch_document",
        "can_approve_document",
        "can_delete_document",
        "can_share_documents",
        "can_set_urgent_priority",
    ]
    exec_group_names = ["Executives", "Executive"]
    exec_groups = [groups.get(name) for name in exec_group_names if groups.get(name)]
    # Ensure both variants exist.
    if not any(name == "Executives" for name in exec_group_names if groups.get(name)):
        exec_groups.append(Group.objects.get_or_create(name="Executives")[0])
    if not any(name == "Executive" for name in exec_group_names if groups.get(name)):
        exec_groups.append(Group.objects.get_or_create(name="Executive")[0])
    for codename in exec_perms:
        for g in exec_groups:
            g.permissions.add(perm(codename))
    for codename in exec_perms:
        groups["MD"].permissions.add(perm(codename))

    # Administrator: all user_management permissions
    for p in Permission.objects.filter(content_type__app_label="user_management"):
        groups["Administrator"].permissions.add(p)

    # Backfill: add HOD/HOU heads and flagged supervisors to the Supervisor group.
    for staff in Staff.objects.all().select_related("user"):
        is_head = (
            apps.get_model("organization", "Department").objects.filter(head=staff).exists()
            or apps.get_model("organization", "Unit").objects.filter(head=staff).exists()
        )
        if is_head or getattr(staff, "is_supervisor", False):
            staff.user.groups.add(supervisor_group)


def reverse_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    try:
        Group.objects.get(name="Supervisor").delete()
    except Group.DoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("user_management", "0017_alter_customuser_options"),
        ("organization", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(configure_permissions, reverse_permissions),
    ]
