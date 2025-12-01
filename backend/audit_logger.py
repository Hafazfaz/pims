"""
Audit Logger Module
Comprehensive audit trail for all system actions
Backend-only logging service
"""
from db_config import get_db_connection
from datetime import datetime
from flask import request


class AuditLogger:
    """Centralized audit logging for compliance and security"""
    
    @staticmethod
    def log(user_id, username, action, resource_type, resource_id=None, details=None):
        """
        Log an action to audit trail
        
        Args:
            user_id: ID of user performing action
            username: Username of user
            action: Action performed (e.g., 'create', 'update', 'delete', 'approve')
            resource_type: Type of resource (e.g., 'file', 'user', 'workflow')
            resource_id: ID of the resource affected
            details: Additional context (JSON or text)
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get IP address and user agent from request context
            ip_address = request.remote_addr if request else None
            user_agent = request.headers.get('User-Agent', '')[:255] if request else None
            
            cursor.execute("""
                INSERT INTO audit_logs 
                (user_id, username, action, resource_type, resource_id, details, 
                 ip_address, user_agent, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (user_id, username, action, resource_type, resource_id, details,
                  ip_address, user_agent))
            
            conn.commit()
            return True
            
        except Exception as e:
            print(f"Audit log error: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
    
    @staticmethod
    def get_user_audit_trail(user_id, limit=100):
        """Get audit trail for a specific user"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT *
                FROM audit_logs
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (user_id, limit))
            
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
    
    @staticmethod
    def get_resource_audit_trail(resource_type, resource_id, limit=50):
        """Get audit trail for a specific resource"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT *
                FROM audit_logs
                WHERE resource_type = %s AND resource_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (resource_type, resource_id, limit))
            
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()


# Convenience functions
def log_file_action(user_id, username, action, file_id, details=None):
    """Log a file-related action"""
    return AuditLogger.log(user_id, username, action, 'file', file_id, details)


def log_user_action(user_id, username, action, target_user_id, details=None):
    """Log a user management action"""
    return AuditLogger.log(user_id, username, action, 'user', target_user_id, details)


def log_workflow_action(user_id, username, action, workflow_id, details=None):
    """Log a workflow action"""
    return AuditLogger.log(user_id, username, action, 'workflow', workflow_id, details)


def log_system_action(user_id, username, action, details=None):
    """Log a system-level action"""
    return AuditLogger.log(user_id, username, action, 'system', None, details)
