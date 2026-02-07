from django.db import migrations

def restrict_file_creation(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    # Get the create_file permission
    try:
        create_file = Permission.objects.get(codename='create_file')
    except Permission.DoesNotExist:
        create_file = Permission.objects.filter(codename='create_file').first()

    if not create_file:
        return

    # Remove from Staff group
    try:
        staff_group = Group.objects.get(name='Staff')
        staff_group.permissions.remove(create_file)
        print("Removed create_file permission from Staff group.")
    except Group.DoesNotExist:
        print("Staff group not found.")

    # Remove from HOD/HOU group (if they had it)
    try:
        hod_group = Group.objects.get(name='HOD/HOU')
        hod_group.permissions.remove(create_file)
        print("Removed create_file permission from HOD/HOU group.")
    except Group.DoesNotExist:
        pass

    # Explicitly ensure it is ONLY in Registry
    try:
        registry_group = Group.objects.get(name='Registry')
        registry_group.permissions.add(create_file)
        print("Confirmed create_file permission for Registry group.")
    except Group.DoesNotExist:
        print("Registry group not found.")

def unassign_permissions(apps, schema_editor):
    # This is a one-way correction, but we can re-add if needed
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('user_management', '0010_merge_20260204_1617'),
        ('document_management', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(restrict_file_creation, reverse_code=unassign_permissions),
    ]
