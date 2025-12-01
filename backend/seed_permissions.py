import mysql.connector
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def get_db_connection():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    return conn

def seed_permissions():
    permissions = [
        ('create_role', 'Allows creation of new roles'),
        ('read_role', 'Allows viewing of roles'),
        ('update_role', 'Allows updating of existing roles'),
        ('delete_role', 'Allows deletion of roles'),
        ('read_permission', 'Allows viewing of permissions'),
        ('create_user', 'Allows creation of new users'),
        ('read_user', 'Allows viewing of user details'),
        ('update_user', 'Allows updating of user details'),
        ('delete_user', 'Allows deletion of users'),
        ('assign_role', 'Allows assigning roles to users'),
        ('create_document', 'Allows creation of new documents'),
        ('read_document', 'Allows viewing of documents'),
        ('update_document', 'Allows updating of documents'),
        ('delete_document', 'Allows deletion of documents'),
        ('approve_document', 'Allows approving documents'),
        ('read_audit_log', 'Allows viewing of audit logs'),
        ('manage_departments', 'Allows managing departments'),
        ('manage_workflows', 'Allows managing workflows'),
        ('view_workflows', 'Allows viewing workflows'),
        ('approve_workflows', 'Allows approving workflows'),
        ('create_workflow_template', 'Allows creation of new workflow templates'),
        ('view_workflow_templates', 'Allows viewing workflow templates'),
        ('view_reports', 'Allows viewing reports'),
        ('edit_workflow_templates', 'Allows editing workflow templates'),
        ('delete_workflow_templates', 'Allows deletion of workflow templates'),
        ('access_control', 'Allows managing access control settings'),
        ('generate_reports', 'Allows generating reports'),
        ('create_department', 'Allows creation of new departments'),
        ('read_department', 'Allows viewing of departments'),
        ('update_department', 'Allows updating of existing departments'),
        ('delete_department', 'Allows deletion of departments'),
        ('reassign_department_head', 'Allows reassigning department heads'),
        ('read_staff_simple', 'Allows viewing a simplified list of staff'),
        ('create_file', 'Allows creation of new files'),
        ('read_file', 'Allows viewing of files'),
        ('update_file', 'Allows updating of existing files'),
        ('delete_file', 'Allows deletion of files'),
    ]

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for name, description in permissions:
            # Check if permission already exists to prevent duplicates
            cursor.execute('SELECT id FROM permissions WHERE name = %s', (name,))
            if not cursor.fetchone():
                cursor.execute('INSERT INTO permissions (name, description) VALUES (%s, %s)', (name, description))
                print(f"Added permission: {name}")
            else:
                print(f"Permission already exists: {name}")
        conn.commit()
        print("Permissions seeding complete.")
    except mysql.connector.Error as err:
        conn.rollback()
        print(f"Error seeding permissions: {err}")
    finally:
        cursor.close()
        conn.close()

def seed_roles_and_role_permissions():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Define roles and their permissions
        roles_data = {
            'Admin': [
                'create_role', 'read_role', 'update_role', 'delete_role',
                'read_permission', 'create_user', 'read_user', 'update_user', 'delete_user',
                'assign_role', 'create_document', 'read_document', 'update_document',
                'delete_document', 'approve_document', 'read_audit_log', 'manage_departments',
                'manage_workflows', 'access_control', 'generate_reports',
                'create_department', 'read_department', 'update_department', 'delete_department',
                'reassign_department_head', 'read_staff_simple',
                'create_file', 'read_file', 'update_file', 'delete_file',
                'view_workflows', 'approve_workflows', 'create_workflow_template', 
                'view_workflow_templates',
    'view_reports'
, 'edit_workflow_templates', 'delete_workflow_templates'
            ],
            'HOD': [
                'read_document', 'update_document', 'approve_document', 'read_user',
                'read_audit_log', 'generate_reports', 'view_reports',
                'read_department', 'read_staff_simple' # HODs can view departments and staff
            ],
            'Staff': [
                'create_document', 'read_document', 'update_document',
            ]
        }

        for role_name, perms in roles_data.items():
            # Check if role exists, if not, create it
            cursor.execute('SELECT id FROM roles WHERE name = %s', (role_name,))
            role_data = cursor.fetchone()
            if not role_data:
                cursor.execute('INSERT INTO roles (name) VALUES (%s)', (role_name,))
                role_id = cursor.lastrowid
                print(f"Added role: {role_name}")
            else:
                role_id = role_data[0]
                print(f"Role already exists: {role_name}")

            # Assign permissions to the role
            for perm_name in perms:
                cursor.execute('SELECT id FROM permissions WHERE name = %s', (perm_name,))
                perm_data = cursor.fetchone()
                if perm_data:
                    permission_id = perm_data[0]
                    cursor.execute('SELECT * FROM role_permissions WHERE role_id = %s AND permission_id = %s', (role_id, permission_id))
                    if not cursor.fetchone():
                        cursor.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)', (role_id, permission_id))
                        print(f"Assigned permission {perm_name} to role {role_name}")
                    else:
                        print(f"Permission {perm_name} already assigned to role {role_name}")
                else:
                    print(f"Permission {perm_name} not found for role {role_name}")
        conn.commit()
        print("Roles and Role Permissions seeding complete.")
    except mysql.connector.Error as err:
        conn.rollback()
        print(f"Error seeding roles and role permissions: {err}")
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    seed_permissions()
    seed_roles_and_role_permissions()