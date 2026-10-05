"""Make ``can_approve_document`` the single document-approval right.

Until now the permission rode on the Supervisor / HOD-HOU / Registry /
Executives groups, so every head could settle a document. Final approval
now belongs to the Medical Director designation only: strip the permission
from every group (and from anyone holding it directly) and hand it to the
staff whose designation marks them as an approver.
"""
from django.db import migrations

CODENAME = "can_approve_document"
GROUP_NAMES = ["Supervisor", "HOD/HOU", "Registry", "Executives", "Executive"]


def _permission(apps):
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.get(app_label="user_management", model="customuser")
    return Permission.objects.get(codename=CODENAME, content_type=ct)


def grant_to_medical_directors(apps, schema_editor):
    from organization.models import designation_implies_final_approver

    Group = apps.get_model("auth", "Group")
    CustomUser = apps.get_model("user_management", "CustomUser")
    Staff = apps.get_model("organization", "Staff")
    perm = _permission(apps)

    # No group carries approval any more — role-by-group is what we are
    # removing.
    for group in Group.objects.all():
        group.permissions.remove(perm)

    approver_ids = set()
    for staff in Staff.objects.select_related("designation"):
        if designation_implies_final_approver(staff.designation):
            approver_ids.add(staff.user_id)

    for user in CustomUser.objects.filter(user_permissions=perm):
        if user.pk not in approver_ids:
            user.user_permissions.remove(perm)
    for user in CustomUser.objects.filter(pk__in=approver_ids):
        user.user_permissions.add(perm)


def restore_group_grants(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    perm = _permission(apps)
    for name in GROUP_NAMES:
        group = Group.objects.filter(name=name).first()
        if group:
            group.permissions.add(perm)


class Migration(migrations.Migration):
    dependencies = [
        ("user_management", "0020_staff_read_write_only_access"),
        ("organization", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(grant_to_medical_directors, restore_group_grants),
    ]
