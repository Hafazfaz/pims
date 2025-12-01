"""
Document Routes Module
Handles document creation, retrieval, and workflow routing
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import mysql.connector
from datetime import datetime
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

document_api = Blueprint('document_api', __name__)

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

@document_api.route('/files/<int:file_id>/documents', methods=['GET'])
@jwt_required()
def get_file_documents(file_id):
    """
    Get all documents within a specific file
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify file access (basic check: file exists)
        # TODO: Add more granular permission checks (e.g. is user owner or in dept?)
        cursor.execute("SELECT id, file_number FROM files WHERE id = %s", (file_id,))
        file_record = cursor.fetchone()
        if not file_record:
            return jsonify({'error': 'File not found'}), 404
            
        cursor.execute("""
            SELECT d.*, u.username as created_by_name 
            FROM documents d
            JOIN users u ON d.created_by = u.id
            WHERE d.file_id = %s
            ORDER BY d.created_at DESC
        """, (file_id,))
        
        documents = cursor.fetchall()
        return jsonify(documents), 200
        
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@document_api.route('/documents', methods=['POST'])
@jwt_required()
def create_document():
    """
    Create a new document within a file
    """
    data = request.json
    file_id = data.get('file_id')
    title = data.get('title')
    content = data.get('content')
    doc_type = data.get('type', 'other')
    
    if not file_id or not title:
        return jsonify({'error': 'File ID and Title are required'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        # Verify file is Active
        cursor.execute("SELECT file_state FROM files WHERE id = %s", (file_id,))
        file_record = cursor.fetchone()
        
        if not file_record:
            return jsonify({'error': 'File not found'}), 404
            
        if file_record['file_state'] != 'Active':
            return jsonify({'error': 'Documents can only be added to Active files'}), 400
            
        # Create document
        cursor.execute("""
            INSERT INTO documents (file_id, title, content, type, created_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (file_id, title, content, doc_type, user['id']))
        
        doc_id = cursor.lastrowid
        
        # Log initial workflow step (Creation)
        cursor.execute("""
            INSERT INTO document_workflow (document_id, from_user_id, action, comment)
            VALUES (%s, %s, 'created', 'Document created')
        """, (doc_id, user['id']))
        
        conn.commit()
        
        return jsonify({
            'message': 'Document created successfully',
            'document_id': doc_id
        }), 201
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@document_api.route('/documents/<int:document_id>/route', methods=['POST'])
@jwt_required()
def route_document(document_id):
    """
    Route a document to another user (e.g., Send to HOD)
    """
    data = request.json
    target_role = data.get('target_role') # e.g., 'HOD', 'HOU'
    comment = data.get('comment', '')
    
    if not target_role:
        return jsonify({'error': 'Target role is required'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id, department_id FROM users WHERE username = %s", (current_username,))
        sender = cursor.fetchone()
        
        if not sender:
            return jsonify({'error': 'User not found'}), 404
            
        # Find receiver based on role and department
        receiver_id = None
        
        if target_role == 'HOD':
            # Find HOD of the department
            cursor.execute("""
                SELECT u.id FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name = 'HOD' AND u.department_id = %s
            """, (sender['department_id'],))
            receiver = cursor.fetchone()
            
            if not receiver:
                # Fallback: Check department head_id
                cursor.execute("SELECT head_id FROM departments WHERE id = %s", (sender['department_id'],))
                dept = cursor.fetchone()
                if dept and dept['head_id']:
                    receiver_id = dept['head_id']
            else:
                receiver_id = receiver['id']
                
        elif target_role == 'Admin':
             cursor.execute("""
                SELECT u.id FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE r.name = 'Admin'
                LIMIT 1
            """)
             receiver = cursor.fetchone()
             if receiver:
                 receiver_id = receiver['id']

        if not receiver_id:
             return jsonify({'error': f'No user found with role {target_role} in your department'}), 404

        # Update document workflow
        cursor.execute("""
            INSERT INTO document_workflow (document_id, from_user_id, to_user_id, action, comment)
            VALUES (%s, %s, %s, %s, %s)
        """, (document_id, sender['id'], receiver_id, 'forward', comment))
        
        conn.commit()
        
        return jsonify({'message': f'Document sent to {target_role} successfully'}), 200
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@document_api.route('/documents/inbox', methods=['GET'])
@jwt_required()
def get_document_inbox():
    """
    Get all documents routed to the current user
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        current_username = get_jwt_identity()
        print(f"DEBUG: Inbox request from username: {current_username}")
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        print(f"DEBUG: User lookup result: {user}")
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        # Fetch files routed to the HOD (in workflows table)
        cursor.execute("""
            SELECT 
                w.id as workflow_id,
                f.id, f.file_number, f.filename as title, f.file_category as type,
                f.created_at,
                sender.username as from_user,
                w.created_at as received_at,
                'file_review' as action
            FROM workflows w
            JOIN files f ON w.file_id = f.id
            JOIN users sender ON w.sender_id = sender.id
            WHERE w.receiver_id = %s
                AND w.status NOT IN ('approved', 'rejected')
            ORDER BY w.created_at DESC
        """, (user['id'],))
        
        inbox_items = cursor.fetchall()
        print(f"DEBUG: Found {len(inbox_items)} inbox items for user {user['id']}")
        return jsonify(inbox_items), 200
        
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@document_api.route('/documents/<int:document_id>', methods=['GET'])
@jwt_required()
def get_document_details(document_id):
    """
    Get complete document details including workflow history
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get document details
        cursor.execute("""
            SELECT 
                d.id, d.title, d.type, d.content, d.created_at,
                f.id as file_id, f.file_number, f.filename,
                creator.username as created_by_name
            FROM documents d
            JOIN files f ON d.file_id = f.id
            JOIN users creator ON d.created_by = creator.id
            WHERE d.id = %s
        """, (document_id,))
        
        document = cursor.fetchone()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
            
        # Get workflow history
        cursor.execute("""
            SELECT 
                dw.action, dw.comment, dw.created_at,
                from_user.username as from_user,
                to_user.username as to_user
            FROM document_workflow dw
            LEFT JOIN users from_user ON dw.from_user_id = from_user.id
            LEFT JOIN users to_user ON dw.to_user_id = to_user.id
            WHERE dw.document_id = %s
            ORDER BY dw.created_at ASC
        """, (document_id,))
        
        workflow = cursor.fetchall()
        document['workflow_history'] = workflow
        
        return jsonify(document), 200
        
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@document_api.route('/documents/<int:document_id>/action', methods=['POST'])
@jwt_required()
def document_action(document_id):
    """
    Perform action on document (approve, reject, forward)
    """
    data = request.json
    action = data.get('action')  # 'approve', 'reject', 'forward'
    comment = data.get('comment', '')
    target_role = data.get('target_role')  # For forward action
    
    if not action:
        return jsonify({'error': 'Action is required'}), 400
        
    if action not in ['approve', 'reject', 'forward']:
        return jsonify({'error': 'Invalid action'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id, department_id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        # For forward action, find the next recipient
        to_user_id = None
        if action == 'forward':
            if not target_role:
                return jsonify({'error': 'Target role required for forward action'}), 400
                
            if target_role == 'Admin':
                cursor.execute("""
                    SELECT u.id FROM users u
                    JOIN roles r ON u.role_id = r.id
                    WHERE r.name = 'Admin'
                    LIMIT 1
                """)
                receiver = cursor.fetchone()
                if receiver:
                    to_user_id = receiver['id']
                else:
                    return jsonify({'error': 'No Admin user found'}), 404
        
        # Record the action in workflow
        cursor.execute("""
            INSERT INTO document_workflow (document_id, from_user_id, to_user_id, action, comment)
            VALUES (%s, %s, %s, %s, %s)
        """, (document_id, user['id'], to_user_id, action, comment))
        
        conn.commit()
        
        action_messages = {
            'approve': 'Document approved successfully',
            'reject': 'Document rejected',
            'forward': f'Document forwarded to {target_role}'
        }
        
        return jsonify({'message': action_messages.get(action, 'Action completed')}), 200
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()
