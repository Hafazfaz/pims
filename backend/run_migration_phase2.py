"""
Database Migration: Phase 2 - Document Workflow
Run this script to add documents and document_workflow tables
"""

import mysql.connector
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def run_migration_phase2():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor()
    
    try:
        print("Starting Phase 2 migration...")
        
        # 1. Create documents table
        print("Step 1: Creating documents table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                file_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                content TEXT, -- For text-based documents or description
                file_path VARCHAR(255), -- If it's an uploaded file
                type ENUM('minute', 'memo', 'letter', 'other') DEFAULT 'other',
                created_by INT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("  - documents table created")
        
        # 2. Create document_workflow table
        print("Step 2: Creating document_workflow table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_workflow (
                id INT AUTO_INCREMENT PRIMARY KEY,
                document_id INT NOT NULL,
                from_user_id INT NOT NULL,
                to_user_id INT, -- Can be null if sent to a role/department generally
                action VARCHAR(50) NOT NULL, -- e.g., 'forward', 'approve', 'reject'
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY (from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (to_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        print("  - document_workflow table created")
        
        # 3. Add indexes
        print("Step 3: Adding indexes...")
        cursor.execute("SHOW INDEX FROM documents WHERE Key_name = 'idx_file_documents'")
        if not cursor.fetchone():
            cursor.execute("CREATE INDEX idx_file_documents ON documents(file_id)")
            print("  - Added idx_file_documents index")
            
        cursor.execute("SHOW INDEX FROM document_workflow WHERE Key_name = 'idx_doc_workflow'")
        if not cursor.fetchone():
            cursor.execute("CREATE INDEX idx_doc_workflow ON document_workflow(document_id)")
            print("  - Added idx_doc_workflow index")
        
        conn.commit()
        print("\n✅ Phase 2 Migration completed successfully!")
        
    except mysql.connector.Error as err:
        print(f"\n❌ Migration failed: {err}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("Phase 2: Document Workflow Migration")
    print("=" * 60)
    run_migration_phase2()
