-- Delegations Table for HOD Authority Transfer
-- Allows HOD to delegate approval authority temporarily

CREATE TABLE IF NOT EXISTS delegations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hod_user_id INT NOT NULL,
    delegate_user_id INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason TEXT,
    status ENUM('active', 'cancelled', 'completed') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (hod_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (delegate_user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    INDEX idx_hod_user (hod_user_id),
    INDEX idx_delegate_user (delegate_user_id),
    INDEX idx_status (status),
    INDEX idx_dates (start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
