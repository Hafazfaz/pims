"""Seed the Nursing Services department and its head designation."""
from django.db import migrations


def create_nursing_services(apps, schema_editor):
    Department = apps.get_model("organization", "Department")
    Designation = apps.get_model("organization", "Designation")

    Department.objects.get_or_create(code="NUR", defaults={"name": "Nursing Services"})
    Designation.objects.get_or_create(
        name="Head of Nursing Services", defaults={"level": 4}
    )


def remove_nursing_services(apps, schema_editor):
    Department = apps.get_model("organization", "Department")
    Designation = apps.get_model("organization", "Designation")
    Department.objects.filter(code="NUR", name="Nursing Services").delete()
    Designation.objects.filter(name="Head of Nursing Services").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("organization", "0012_auto_verify_existing_signatures"),
    ]

    operations = [
        migrations.RunPython(create_nursing_services, remove_nursing_services),
    ]
