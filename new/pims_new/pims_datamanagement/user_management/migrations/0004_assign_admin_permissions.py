from django.db import migrations

def assign_admin_permissions(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    admin_group = Group.objects.get(name='Administrator')

    # Get all permissions
    all_permissions = Permission.objects.all()

    # Assign all permissions to the Administrator group
    admin_group.permissions.set(all_permissions)
    print("Assigned all permissions to the Administrator group.")

def remove_admin_permissions(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    admin_group = Group.objects.get(name='Administrator')
    admin_group.permissions.clear()
    print("Removed all permissions from the Administrator group.")

class Migration(migrations.Migration):

    dependencies = [
        ('user_management', '0003_create_roles'),
        ('auth', '0012_alter_user_first_name_max_length'), # Dependency on auth migrations for Group and Permission models
        ('contenttypes', '0002_remove_content_type_name'), # Dependency on contenttypes for ContentType model
    ]

    operations = [
        migrations.RunPython(assign_admin_permissions, remove_admin_permissions),
    ]