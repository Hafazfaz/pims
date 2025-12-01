import mysql.connector
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def debug_db():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor(dictionary=True)

    print("--- ROLES ---")
    cursor.execute("SELECT * FROM roles")
    for role in cursor.fetchall():
        print(role)

    print("\n--- USERS ---")
    cursor.execute("SELECT id, username, email, role_id FROM users")
    users = cursor.fetchall()
    for user in users:
        print(user)
        # Get role name for this user
        cursor.execute("SELECT name FROM roles WHERE id = %s", (user['role_id'],))
        role_name = cursor.fetchone()
        print(f"  -> Role: {role_name['name'] if role_name else 'None'}")

    conn.close()

if __name__ == "__main__":
    debug_db()
