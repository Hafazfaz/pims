"""
Notifications Module
Handles creation and retrieval of user notifications
"""

from datetime import datetime
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

def create_notification(user_id, title, message, type='info', category='system', link=None):
    """
    Create a new notification for a user
    
    Args:
        user_id: ID of the user to notify
        title: Short notification title
        message: Detailed notification message
        type: 'info', 'success', 'warning', 'error', 'urgent'
        category: 'file_assignment', 'activation', 'approval', 'deadline', 'completion', 'system'
        link: Optional link to related resource
    
    Returns:
        notification_id or None if failed
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO notifications (user_id, title, message, type, category, link)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, title, message, type, category, link))
        
        conn.commit()
        notification_id = cursor.lastrowid
        
        # TODO: Check user preferences and send email if enabled
        # send_email_notification(user_id, title, message)
        
        return notification_id
        
    except mysql.connector.Error as err:
        print(f"Error creating notification: {err}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()


def get_user_notifications(user_id, unread_only=False, limit=50):
    """
    Get notifications for a user
    
    Args:
        user_id: ID of the user
        unread_only: If True, only return unread notifications
        limit: Maximum number of notifications to return
    
    Returns:
        List of notification dictionaries
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        query = "SELECT * FROM notifications WHERE user_id = %s"
        params = [user_id]
        
        if unread_only:
            query += " AND is_read = FALSE"
        
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, tuple(params))
        notifications = cursor.fetchall()
        
        # Convert datetime objects to strings for JSON serialization
        for notif in notifications:
            if isinstance(notif.get('created_at'), datetime):
                notif['created_at'] = notif['created_at'].isoformat()
        
        return notifications
        
    except mysql.connector.Error as err:
        print(f"Error fetching notifications: {err}")
        return []
    finally:
        cursor.close()
        conn.close()


def mark_notification_read(notification_id, user_id):
    """
    Mark a notification as read
    
    Args:
        notification_id: ID of the notification
        user_id: ID of the user (for security check)
    
    Returns:
        True if successful, False otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE notifications 
            SET is_read = TRUE 
            WHERE id = %s AND user_id = %s
        """, (notification_id, user_id))
        
        conn.commit()
        return cursor.rowcount > 0
        
    except mysql.connector.Error as err:
        print(f"Error marking notification as read: {err}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def mark_all_read(user_id):
    """
    Mark all notifications as read for a user
    
    Args:
        user_id: ID of the user
    
    Returns:
        Number of notifications marked as read
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE notifications 
            SET is_read = TRUE 
            WHERE user_id = %s AND is_read = FALSE
        """, (user_id,))
        
        conn.commit()
        return cursor.rowcount
        
    except mysql.connector.Error as err:
        print(f"Error marking all notifications as read: {err}")
        conn.rollback()
        return 0
    finally:
        cursor.close()
        conn.close()


def get_unread_count(user_id):
    """
    Get count of unread notifications for a user
    
    Args:
        user_id: ID of the user
    
    Returns:
        Count of unread notifications
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM notifications 
            WHERE user_id = %s AND is_read = FALSE
        """, (user_id,))
        
        count = cursor.fetchone()[0]
        return count
        
    except mysql.connector.Error as err:
        print(f"Error getting unread count: {err}")
        return 0
    finally:
        cursor.close()
        conn.close()


def delete_notification(notification_id, user_id):
    """
    Delete a notification (soft delete - actually just marks as read)
    
    Args:
        notification_id: ID of the notification
        user_id: ID of the user (for security check)
    
    Returns:
        True if successful, False otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # For now, just mark as read. Could add a deleted flag later.
        cursor.execute("""
            DELETE FROM notifications 
            WHERE id = %s AND user_id = %s
        """, (notification_id, user_id))
        
        conn.commit()
        return cursor.rowcount > 0
        
    except mysql.connector.Error as err:
        print(f"Error deleting notification: {err}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


# Helper functions for common notification scenarios

def notify_file_assignment(user_id, file_name, file_id):
    """Notify user of new file assignment"""
    return create_notification(
        user_id=user_id,
        title="New File Assigned",
        message=f"You have been assigned a new file: {file_name}",
        type='info',
        category='file_assignment',
        link=f"/files/{file_id}"
    )


def notify_activation_approved(user_id, file_name, file_number):
    """Notify user their activation request was approved"""
    return create_notification(
        user_id=user_id,
        title="File Activation Approved",
        message=f"Your activation request for file {file_number} ({file_name}) has been approved. The file is now active.",
        type='success',
        category='activation'
    )


def notify_activation_rejected(user_id, file_name, file_number, reason):
    """Notify user their activation request was rejected"""
    return create_notification(
        user_id=user_id,
        title="File Activation Rejected",
        message=f"Your activation request for file {file_number} ({file_name}) was rejected. Reason: {reason}",
        type='warning',
        category='activation'
    )


def notify_file_overdue(user_id, file_name, days_overdue):
    """Notify user of overdue file"""
    return create_notification(
        user_id=user_id,
        title="URGENT: File Overdue",
        message=f"File '{file_name}' is overdue by {days_overdue} days. Please take action immediately.",
        type='urgent',
        category='deadline'
    )


def notify_file_completed(user_id, file_name):
    """Notify user their file completed its cycle"""
    return create_notification(
        user_id=user_id,
        title="File Completed",
        message=f"File '{file_name}' has completed its workflow cycle and returned to Registry.",
        type='success',
        category='completion'
    )
