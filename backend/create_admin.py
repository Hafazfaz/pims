import mysql.connector
from werkzeug.security import generate_password_hash
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def create_admin():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor()
    
    username = "admin"
    password = "your_secure_admin_password"
    email = "admin@example.com" # Dummy email
    
    try:
        # Get Admin role ID
        cursor.execute("SELECT id FROM roles WHERE name = 'Admin'")
        role_row = cursor.fetchone()
        if not role_row:
            print("Error: Admin role not found. Please run seed_permissions.py first.")
            return
        
        role_id = role_row[0]
        hashed_password = generate_password_hash(password)
        
        # Check if admin exists
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            print("Admin user already exists. Updating password...")
            cursor.execute("UPDATE users SET password_hash = %s, role_id = %s WHERE username = %s", (hashed_password, role_id, username))
        else:
            print("Creating admin user...")
            cursor.execute("INSERT INTO users (username, email, password_hash, role_id) VALUES (%s, %s, %s, %s)", (username, email, hashed_password, role_id))
            
        conn.commit()
        print("Admin user created/updated successfully.")
        
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    create_admin()
