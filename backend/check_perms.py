import mysql.connector
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def check_permissions():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor(dictionary=True)

    print("--- ROLE PERMISSIONS ---")
    cursor.execute("""
        SELECT r.name as role, p.name as permission 
        FROM role_permissions rp 
        JOIN roles r ON rp.role_id = r.id 
        JOIN permissions p ON rp.permission_id = p.id
        ORDER BY r.name, p.name
    """)
    for row in cursor.fetchall():
        print(f"{row['role']}: {row['permission']}")

    conn.close()

if __name__ == "__main__":
    check_permissions()
