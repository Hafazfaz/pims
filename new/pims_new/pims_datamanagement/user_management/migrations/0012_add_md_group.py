from django.db import migrations


def add_md_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='MD')


def remove_md_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name='MD').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('user_management', '0011_restrict_file_creation'),
    ]

    operations = [
        migrations.RunPython(add_md_group, remove_md_group),
    ]
