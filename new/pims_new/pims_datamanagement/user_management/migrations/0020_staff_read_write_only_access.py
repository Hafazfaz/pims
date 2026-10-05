from django.db import migrations
from django.db.models import Q


def restrict_staff_access_level(apps, schema_editor):
    """
    Read-Write becomes the only access level offered to normal staff;
    Read-Only stays reserved for supervisor roles.
    """
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomUser = apps.get_model("user_management", "CustomUser")
    Staff = apps.get_model("organization", "Staff")
    FileAccessRequest = apps.get_model("document_management", "FileAccessRequest")

    user_ct = ContentType.objects.get(app_label="user_management", model="customuser")

    read_only = Permission.objects.filter(
        codename="can_request_file_access", content_type=user_ct
    ).first()
    read_write = Permission.objects.filter(
        codename="can_request_file_access_rw", content_type=user_ct
    ).first()

    staff_group, _ = Group.objects.get_or_create(name="Staff")
    if read_write:
        staff_group.permissions.add(read_write)
    if read_only:
        staff_group.permissions.remove(read_only)

    # Pending Read-Only requests raised by non-supervisors can no longer be
    # approved under the new rule, so reject them instead of leaving them stuck.
    supervisor_group_names = ["Supervisor", "HOD/HOU", "Executives", "Executive", "MD"]
    supervisor_user_ids = set(
        CustomUser.objects.filter(groups__name__in=supervisor_group_names).values_list(
            "id", flat=True
        )
    )
    supervisor_user_ids |= set(
        CustomUser.objects.filter(
            Q(user_permissions__codename__in=["can_supervise", "can_executive"])
            | Q(groups__permissions__codename__in=["can_supervise", "can_executive"])
        ).values_list("id", flat=True)
    )

    head_staff_ids = set()
    for model_name in ["Department", "Division", "Section", "Unit"]:
        model = apps.get_model("organization", model_name)
        head_staff_ids |= set(
            model.objects.exclude(head__isnull=True).values_list("head", flat=True)
        )
    supervisor_user_ids |= set(
        Staff.objects.filter(
            Q(pk__in=head_staff_ids) | Q(is_supervisor=True)
        ).values_list("user", flat=True)
    )

    supervisor_user_ids.discard(None)

    FileAccessRequest.objects.filter(
        status="pending", access_type="read_only"
    ).exclude(requested_by_id__in=supervisor_user_ids).update(status="rejected")


def restore_staff_access_level(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    user_ct = ContentType.objects.get(app_label="user_management", model="customuser")
    read_only = Permission.objects.filter(
        codename="can_request_file_access", content_type=user_ct
    ).first()

    try:
        staff_group = Group.objects.get(name="Staff")
    except Group.DoesNotExist:
        return
    if read_only:
        staff_group.permissions.add(read_only)


class Migration(migrations.Migration):
    dependencies = [
        ("user_management", "0019_add_head_scope_permissions"),
        ("organization", "0001_initial"),
        ("document_management", "0011_fileaccessrequest_access_type"),
    ]

    operations = [
        migrations.RunPython(restrict_staff_access_level, restore_staff_access_level),
    ]
