"""
Database Migration: Registry File Lifecycle Management
Run this script to add file states, activation workflow, and auto-numbering support
"""

import mysql.connector
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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
        print("Starting migration...")
        
        # 1. Add columns to files table
        print("Step 1: Adding columns to files table...")
        
        # Check if columns already exist
        cursor.execute("SHOW COLUMNS FROM files LIKE 'file_state'")
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE files 
                ADD COLUMN file_state ENUM('Inactive', 'Active', 'Archived') DEFAULT 'Inactive' AFTER status
            """)
            print("  - Added file_state column")
        
        cursor.execute("SHOW COLUMNS FROM files LIKE 'employment_type'")
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE files 
                ADD COLUMN employment_type ENUM('Permanent', 'Locum', 'Contract', 'NYSC') NULL AFTER file_category
            """)
            print("  - Added employment_type column")
        
        cursor.execute("SHOW COLUMNS FROM files LIKE 'second_level_auth'")
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE files 
                ADD COLUMN second_level_auth BOOLEAN DEFAULT FALSE AFTER employment_type
            """)
            print("  - Added second_level_auth column")
        
        cursor.execute("SHOW COLUMNS FROM files LIKE 'progress'")
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE files 
                ADD COLUMN progress ENUM('In Action', 'Closed') DEFAULT 'Closed' AFTER file_state
            """)
            print("  - Added progress column")
        
        cursor.execute("SHOW COLUMNS FROM files LIKE 'current_location_user_id'")
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE files 
                ADD COLUMN current_location_user_id INT NULL AFTER uploader_id,
                ADD CONSTRAINT fk_files_current_location FOREIGN KEY (current_location_user_id) 
                REFERENCES users(id) ON DELETE SET NULL
            """)
            print("  - Added current_location_user_id column with foreign key")
        
        cursor.execute("SHOW COLUMNS FROM files LIKE 'owner_id'")
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE files 
                ADD COLUMN owner_id INT NULL AFTER uploader_id,
                ADD CONSTRAINT fk_files_owner FOREIGN KEY (owner_id) 
                REFERENCES users(id) ON DELETE SET NULL
            """)
            print("  - Added owner_id column with foreign key")
        
        # 2. Create file_activation_requests table
        print("Step 2: Creating file_activation_requests table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_activation_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                file_id INT NOT NULL,
                requestor_id INT NOT NULL,
                request_reason TEXT NOT NULL,
                status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
                processed_by INT NULL,
                processed_at TIMESTAMP NULL,
                rejection_reason TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (requestor_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (processed_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        print("  - file_activation_requests table created")
        
        # 3. Create file_number_counters table
        print("Step 3: Creating file_number_counters table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_number_counters (
                id INT AUTO_INCREMENT PRIMARY KEY,
                year INT NOT NULL,
                category ENUM('Personal', 'Policy') NOT NULL,
                employment_type ENUM('Permanent', 'Locum', 'Contract', 'NYSC') NULL,
                department_code VARCHAR(50) NULL,
                last_serial INT DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY unique_counter (year, category, employment_type, department_code)
            )
        """)
        print("  - file_number_counters table created")
        
        # 4. Add indexes
        print("Step 4: Adding indexes for performance...")
        cursor.execute("SHOW INDEX FROM files WHERE Key_name = 'idx_file_state'")
        if not cursor.fetchone():
            cursor.execute("CREATE INDEX idx_file_state ON files(file_state)")
            print("  - Added idx_file_state index")
        
        cursor.execute("SHOW INDEX FROM files WHERE Key_name = 'idx_current_location'")
        if not cursor.fetchone():
            cursor.execute("CREATE INDEX idx_current_location ON files(current_location_user_id)")
            print("  - Added idx_current_location index")
        
        cursor.execute("SHOW INDEX FROM files WHERE Key_name = 'idx_owner'")
        if not cursor.fetchone():
            cursor.execute("CREATE INDEX idx_owner ON files(owner_id)")
            print("  - Added idx_owner index")
        
        cursor.execute("SHOW INDEX FROM file_activation_requests WHERE Key_name = 'idx_activation_status'")
        if not cursor.fetchone():
            cursor.execute("CREATE INDEX idx_activation_status ON file_activation_requests(status)")
            print("  - Added idx_activation_status index")
        
        # 5. Update existing data
        print("Step 5: Updating existing file states...")
        cursor.execute("UPDATE files SET file_state = 'Active' WHERE status = 'active' AND file_state IS NULL")
        cursor.execute("UPDATE files SET file_state = 'Archived' WHERE status = 'archived' AND file_state IS NULL")
        print("  - Existing files updated with appropriate states")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
    except mysql.connector.Error as err:
        print(f"\n❌ Migration failed: {err}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("Registry File Lifecycle Management Migration")
    print("=" * 60)
    run_migration()
