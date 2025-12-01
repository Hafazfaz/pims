"""
Notification API Routes
Provides endpoints for notification management
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import mysql.connector
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
from notifications import (
    create_notification,
    get_user_notifications,
    mark_notification_read,
    mark_all_read,
    get_unread_count,
    delete_notification
)

notification_api = Blueprint('notification_api', __name__)

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

@notification_api.route('/notifications', methods=['GET'])
@jwt_required()
def get_notifications():
    """
    Get notifications for current user
    Query params:
    - unread_only: boolean (default: false)
    - limit: int (default: 50, max: 100)
    """
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get user ID
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user_id = user['id']
        
        # Get query parameters
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        limit = min(int(request.args.get('limit', 50)), 100)
        
        # Get notifications
        notifications = get_user_notifications(user_id, unread_only, limit)
        
        return jsonify(notifications), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@notification_api.route('/notifications/unread-count', methods=['GET'])
@jwt_required()
def get_unread_count_endpoint():
    """Get count of unread notifications for current user"""
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        count = get_unread_count(user['id'])
        
        return jsonify({'unread_count': count}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@notification_api.route('/notifications/<int:notification_id>/read', methods=['PUT'])
@jwt_required()
def mark_read(notification_id):
    """Mark a notification as read"""
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        success = mark_notification_read(notification_id, user['id'])
        
        if success:
            return jsonify({'message': 'Notification marked as read'}), 200
        else:
            return jsonify({'error': 'Notification not found or unauthorized'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@notification_api.route('/notifications/mark-all-read', methods=['PUT'])
@jwt_required()
def mark_all_read_endpoint():
    """Mark all notifications as read for current user"""
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        count = mark_all_read(user['id'])
        
        return jsonify({'message': f'{count} notifications marked as read'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@notification_api.route('/notifications/<int:notification_id>', methods=['DELETE'])
@jwt_required()
def delete_notification_endpoint(notification_id):
    """Delete a notification"""
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        success = delete_notification(notification_id, user['id'])
        
        if success:
            return jsonify({'message': 'Notification deleted'}), 200
        else:
            return jsonify({'error': 'Notification not found or unauthorized'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@notification_api.route('/notifications/test', methods=['POST'])
@jwt_required()
def create_test_notification():
    """Create a test notification (for testing only)"""
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.json or {}
        title = data.get('title', 'Test Notification')
        message = data.get('message', 'This is a test notification')
        type = data.get('type', 'info')
        
        notification_id = create_notification(
            user_id=user['id'],
            title=title,
            message=message,
            type=type
        )
        
        if notification_id:
            return jsonify({'message': 'Test notification created', 'id': notification_id}), 201
        else:
            return jsonify({'error': 'Failed to create notification'}), 500
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
