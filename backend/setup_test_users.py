"""
Setup test users for document routing verification
"""
import mysql.connector
from werkzeug.security import generate_password_hash
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

def setup_test_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get role IDs
        cursor.execute("SELECT id, name FROM roles")
        roles = {row['name']: row['id'] for row in cursor.fetchall()}
        
        # Get department ID (assume department 1 exists)
        dept_id = 1
        
        # Test users
        test_users = [
            ('staff_user', 'staff@test.com', 'password123', roles.get('Staff'), dept_id),
            ('registry_user', 'registry@test.com', 'password123', roles.get('Registry'), None),
            ('hod_user', 'hod@test.com', 'password123', roles.get('HOD'), dept_id),
        ]
        
        for username, email, password, role_id, department_id in test_users:
            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                print(f"User {username} already exists, skipping")
                continue
            
            hashed_pw = generate_password_hash(password)
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, role_id, department_id, is_active)
                VALUES (%s, %s, %s, %s, %s, 1)
            """, (username, email, hashed_pw, role_id, department_id))
            print(f"Created user: {username}")
        
        conn.commit()
        print("\nTest users setup complete!")
        print("Credentials: username / password123")
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    setup_test_users()
