# Grant view_staff_documents to every group except Registry.
# Registry staff must NOT see staff personnel documents (not even titles/metadata).

from django.db import migrations


def _get_or_create_perm(apps):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct, _ = ContentType.objects.get_or_create(
        app_label="document_management",
        model="document",
    )
    perm, _ = Permission.objects.get_or_create(
        content_type=ct,
        codename="view_staff_documents",
        defaults={
            "name": "Can view staff personnel documents (titles and metadata). "
            "Granted to every group except Registry."
        },
    )
    return perm


def grant_view_staff_documents(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    perm = _get_or_create_perm(apps)
    for group in Group.objects.exclude(name__iexact="Registry"):
        group.permissions.add(perm)
    # Belt-and-braces: strip it from Registry even if previously granted.
    for group in Group.objects.filter(name__iexact="Registry"):
        group.permissions.remove(perm)


def revoke_view_staff_documents(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    try:
        perm = Permission.objects.get(
            content_type__app_label="document_management",
            content_type__model="document",
            codename="view_staff_documents",
        )
    except Permission.DoesNotExist:
        return
    for group in Group.objects.all():
        group.permissions.remove(perm)


class Migration(migrations.Migration):

    dependencies = [
        ("document_management", "0044_alter_document_options"),
    ]

    operations = [
        migrations.RunPython(grant_view_staff_documents, revoke_view_staff_documents),
    ]
