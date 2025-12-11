from django.db import migrations

def create_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    # Define roles and their initial permissions
    roles_permissions = {
        "Administrator": [],  # Will have all permissions
        "Registry": [],
        "HOD/HOU": [],
        "Staff": [],
        "Executives": [],
    }

    for role_name, permissions_list in roles_permissions.items():
        group, created = Group.objects.get_or_create(name=role_name)
        if created:
            print(f"Created Group: {role_name}")
        
        # Assign permissions (this part will be expanded later)
        for perm_codename in permissions_list:
            try:
                permission = Permission.objects.get(codename=perm_codename)
                group.permissions.add(permission)
            except Permission.DoesNotExist:
                print(f"Warning: Permission '{perm_codename}' not found for role '{role_name}'.")

def remove_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for role_name in ["Administrator", "Registry", "HOD/HOU", "Staff", "Executives"]:
        try:
            group = Group.objects.get(name=role_name)
            group.delete()
            print(f"Removed Group: {role_name}")
        except Group.DoesNotExist:
            pass

class Migration(migrations.Migration):

    dependencies = [
        ('user_management', '0002_customuser_must_change_password'),
        ('auth', '0012_alter_user_first_name_max_length'), # Dependency on auth migrations for Group and Permission models
    ]

    operations = [
        migrations.RunPython(create_roles, remove_roles),
    ]