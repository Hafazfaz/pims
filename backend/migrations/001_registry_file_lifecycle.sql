-- Migration: Registry File Lifecycle Management
-- Description: Add file states, activation workflow, and auto-numbering support
-- Date: 2025-11-23

-- 1. Add columns to files table for file lifecycle management
ALTER TABLE files 
ADD COLUMN file_state ENUM('Inactive', 'Active', 'Archived') DEFAULT 'Inactive' AFTER status,
ADD COLUMN employment_type ENUM('Permanent', 'Locum', 'Contract', 'NYSC') NULL AFTER file_category,
ADD COLUMN second_level_auth BOOLEAN DEFAULT FALSE AFTER employment_type,
ADD COLUMN current_location_user_id INT NULL AFTER uploader_id,
ADD COLUMN progress ENUM('In Action', 'Closed') DEFAULT 'Closed' AFTER file_state,
ADD COLUMN owner_id INT NULL AFTER uploader_id,
ADD CONSTRAINT fk_files_current_location FOREIGN KEY (current_location_user_id) REFERENCES users(id) ON DELETE SET NULL,
ADD CONSTRAINT fk_files_owner FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL;

-- 2. Create file activation requests table
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
);

-- 3. Create file numbering counters table for auto-increment
CREATE TABLE IF NOT EXISTS file_number_counters (
    id INT AUTO_INCREMENT PRIMARY KEY,
    year INT NOT NULL,
    category ENUM('Personal', 'Policy') NOT NULL,
    employment_type ENUM('Permanent', 'Locum', 'Contract', 'NYSC') NULL,
    department_code VARCHAR(50) NULL,
    last_serial INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_counter (year, category, employment_type, department_code)
);

-- 4. Add index for better query performance
CREATE INDEX idx_file_state ON files(file_state);
CREATE INDEX idx_current_location ON files(current_location_user_id);
CREATE INDEX idx_owner ON files(owner_id);
CREATE INDEX idx_activation_status ON file_activation_requests(status);

-- 5. Update existing files to have proper states (migration data)
UPDATE files SET file_state = 'Active' WHERE status = 'active';
UPDATE files SET file_state = 'Archived' WHERE status = 'archived';
