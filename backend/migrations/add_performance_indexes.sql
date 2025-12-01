-- ============================================
-- PERFORMANCE INDEXES
-- Add indexes for frequently queried columns
-- ============================================

-- Files table indexes
CREATE INDEX IF NOT EXISTS idx_files_state ON files(file_state);
CREATE INDEX IF NOT EXISTS idx_files_owner ON files(owner_id);
CREATE INDEX IF NOT EXISTS idx_files_created ON files(created_at);
CREATE INDEX IF NOT EXISTS idx_files_updated ON files(updated_at);
CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);

-- File history indexes
CREATE INDEX IF NOT EXISTS idx_file_history_file ON file_history(file_id);
CREATE INDEX IF NOT EXISTS idx_file_history_user ON file_history(performed_by);
CREATE INDEX IF NOT EXISTS idx_file_history_created ON file_history(created_at);
CREATE INDEX IF NOT EXISTS idx_file_history_action ON file_history(action);

-- Document workflow indexes  
CREATE INDEX IF NOT EXISTS idx_workflow_status ON document_workflow(status);
CREATE INDEX IF NOT EXISTS idx_workflow_file ON document_workflow(file_id);
CREATE INDEX IF NOT EXISTS idx_workflow_current ON document_workflow(current_holder_id);
CREATE INDEX IF NOT EXISTS idx_workflow_created ON document_workflow(created_at);

-- Users table indexes
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_department ON users(department_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_files_state_updated ON files(file_state, updated_at);
CREATE INDEX IF NOT EXISTS idx_workflow_status_created ON document_workflow(status, created_at);

-- ============================================
-- AUDIT LOG TABLE (Enhanced)
-- ============================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    username VARCHAR(100),
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id INT,
    details TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_user (user_id),
    INDEX idx_audit_action (action),
    INDEX idx_audit_resource (resource_type, resource_id),
    INDEX idx_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- PERFORMANCE VERIFICATION
-- ============================================

-- Show all indexes
SELECT 
    TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME,
    INDEX_TYPE
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

-- Check index usage
SHOW INDEX FROM files;
SHOW INDEX FROM file_history;
SHOW INDEX FROM document_workflow;
SHOW INDEX FROM users;
