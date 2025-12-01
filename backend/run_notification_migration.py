"""
Run notifications migration
"""
import mysql.connector
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def run_migration():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor()
    
    try:
        # Read migration file
        with open('backend/migrations/20251125_create_notifications.sql', 'r') as f:
            sql = f.read()
        
        # Split by statements (simple split on ;)
        statements = [s.strip() for s in sql.split(';') if s.strip() and not s.strip().startswith('--')]
        
        for statement in statements:
            if 'CREATE TABLE' in statement or 'INSERT' in statement:
                print(f"Executing: {statement[:80]}...")
                cursor.execute(statement)
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        print("Created tables: notifications, notification_preferences")
        
    except mysql.connector.Error as err:
        print(f"❌ Error: {err}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    run_migration()
