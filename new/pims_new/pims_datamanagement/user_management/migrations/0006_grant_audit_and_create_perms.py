from django.db import migrations

def assign_permissions(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    # Get the relevant permissions
    try:
        view_auditlog = Permission.objects.get(codename='view_auditlogentry')
    except Permission.DoesNotExist:
        # Fallback if content type needs to be specified or if it's not created yet
        # AuditLogEntry is in audit_log app
        view_auditlog = Permission.objects.filter(codename='view_auditlogentry').first()

    try:
        create_file = Permission.objects.get(codename='create_file')
    except Permission.DoesNotExist:
        create_file = Permission.objects.filter(codename='create_file').first()

    groups_to_get_audit = ['Registry', 'HOD/HOU']
    groups_to_get_create = ['Staff']
    groups_to_remove_view = ['Staff']

    for group_name in groups_to_get_audit:
        try:
            group = Group.objects.get(name=group_name)
            if view_auditlog:
                group.permissions.add(view_auditlog)
                print(f"Assigned view_auditlogentry to {group_name}")
        except Group.DoesNotExist:
            print(f"Warning: Group '{group_name}' not found.")

    for group_name in groups_to_get_create:
        try:
            group = Group.objects.get(name=group_name)
            if create_file:
                group.permissions.add(create_file)
                print(f"Assigned create_file to {group_name}")
        except Group.DoesNotExist:
            print(f"Warning: Group '{group_name}' not found.")

    # Remove view_file and view_document from Staff group
    try:
        staff_group = Group.objects.get(name='Staff')
        view_file_perm = Permission.objects.filter(codename='view_file').first()
        view_doc_perm = Permission.objects.filter(codename='view_document').first()
        if view_file_perm:
            staff_group.permissions.remove(view_file_perm)
        if view_doc_perm:
            staff_group.permissions.remove(view_doc_perm)
        print("Removed view_file and view_document from Staff group")
    except Group.DoesNotExist:
        pass

def unassign_permissions(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    view_auditlog = Permission.objects.filter(codename='view_auditlogentry').first()
    create_file = Permission.objects.filter(codename='create_file').first()
    view_file_perm = Permission.objects.filter(codename='view_file').first()
    view_doc_perm = Permission.objects.filter(codename='view_document').first()

    groups_to_get_audit = ['Staff', 'Registry', 'HOD/HOU']
    groups_to_get_create = ['Staff']

    for group_name in groups_to_get_audit:
        try:
            group = Group.objects.get(name=group_name)
            if view_auditlog:
                group.permissions.remove(view_auditlog)
        except Group.DoesNotExist:
            pass

    for group_name in groups_to_get_create:
        try:
            group = Group.objects.get(name=group_name)
            if create_file:
                group.permissions.remove(create_file)
        except Group.DoesNotExist:
            pass
    
    # Re-add view permissions if unassigning (optional, but for completeness)
    try:
        staff_group = Group.objects.get(name='Staff')
        if view_file_perm:
            staff_group.permissions.add(view_file_perm)
        if view_doc_perm:
            staff_group.permissions.add(view_doc_perm)
    except Group.DoesNotExist:
        pass

class Migration(migrations.Migration):

    dependencies = [
        ('user_management', '0005_assign_mvp_permissions'),
        ('audit_log', '0001_initial'),
        ('document_management', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(assign_permissions, reverse_code=unassign_permissions),
    ]
