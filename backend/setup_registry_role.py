"""
Script to create Registry role and permissions
Run this after migration to set up Registry access
"""

import mysql.connector
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def setup_registry_permissions():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor(dictionary=True)
    
    try:
        print("Setting up Registry role and permissions...")
        
        # 1. Check if Registry role exists
        cursor.execute("SELECT id FROM roles WHERE name = 'Registry'")
        registry_role = cursor.fetchone()
        
        if not registry_role:
            cursor.execute("""
                INSERT INTO roles (name, description) 
                VALUES ('Registry', 'Registry personnel responsible for file custodianship and activation')
            """)
            registry_role_id = cursor.lastrowid
            print(f"  - Registry role created (ID: {registry_role_id})")
        else:
            registry_role_id = registry_role['id']
            print(f"  - Registry role exists (ID: {registry_role_id})")
        
        # 2. Create Registry-specific permissions
        registry_permissions = [
            ('create_file', 'Create new files with auto-numbering'),
            ('manage_file_activation', 'Approve/reject file activation requests'),
            ('deactivate_file', 'Deactivate active files'),
            ('archive_file', 'Archive files permanently'),
            ('read_all_files', 'Read access to all files in the system')
        ]
        
        for perm_name, perm_desc in registry_permissions:
            cursor.execute("SELECT id FROM permissions WHERE name = %s", (perm_name,))
            permission = cursor.fetchone()
            
            if not permission:
                cursor.execute("""
                    INSERT INTO permissions (name, description) 
                    VALUES (%s, %s)
                """, (perm_name, perm_desc))
                permission_id = cursor.lastrowid
                print(f"  - Permission '{perm_name}' created (ID: {permission_id})")
            else:
                permission_id = permission['id']
                print(f"  - Permission '{perm_name}' exists (ID: {permission_id})")
            
            # Assign permission to Registry role
            cursor.execute("""
                SELECT * FROM role_permissions 
                WHERE role_id = %s AND permission_id = %s
            """, (registry_role_id, permission_id))
            
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO role_permissions (role_id, permission_id) 
                    VALUES (%s, %s)
                """, (registry_role_id, permission_id))
                print(f"    --> Assigned to Registry role")
        
        conn.commit()
        print("\nRegistry permissions setup complete!")
        print("\nTo create a Registry user:")
        print("1. Use Admin dashboard to create a new user")
        print("2. Assign the 'Registry' role to that user")
        print("3. User can then access: http://localhost:5000/registry/registry-dashboard.html")
        
    except mysql.connector.Error as err:
        print(f"\nError: {err}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("Registry Role and Permissions Setup")
    print("=" * 60)
    setup_registry_permissions()
