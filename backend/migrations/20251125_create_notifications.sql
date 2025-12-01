-- Migration: Create Notifications System
-- Created: 2025-11-25
-- Description: Add notifications table for in-app alerts and email notifications

-- ============================================
-- UP Migration (Apply Changes)
-- ============================================

-- Create notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type ENUM('info', 'success', 'warning', 'error', 'urgent') DEFAULT 'info',
    category ENUM('file_assignment', 'activation', 'approval', 'deadline', 'completion', 'system') DEFAULT 'system',
    is_read BOOLEAN DEFAULT FALSE,
    link VARCHAR(500) NULL COMMENT 'Optional link to related resource',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_is_read (is_read),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create notification_preferences table for user settings
CREATE TABLE IF NOT EXISTS notification_preferences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    email_enabled BOOLEAN DEFAULT TRUE,
    in_app_enabled BOOLEAN DEFAULT TRUE,
    email_digest ENUM('immediate', 'daily', 'weekly', 'never') DEFAULT 'immediate',
    quiet_hours_start TIME NULL,
    quiet_hours_end TIME NULL,
    file_assignment_enabled BOOLEAN DEFAULT TRUE,
    activation_enabled BOOLEAN DEFAULT TRUE,
    approval_enabled BOOLEAN DEFAULT TRUE,
    deadline_enabled BOOLEAN DEFAULT TRUE,
    completion_enabled BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create default notification preferences for existing users
INSERT INTO notification_preferences (user_id)
SELECT id FROM users 
WHERE id NOT IN (SELECT user_id FROM notification_preferences);

-- ============================================
-- DOWN Migration (Rollback Changes)
-- ============================================

-- DROP TABLE IF EXISTS notification_preferences;
-- DROP TABLE IF EXISTS notifications;
