
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import mysql.connector
import os
from werkzeug.utils import secure_filename
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

staff_api = Blueprint('staff_api', __name__)

def get_db_connection():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    return conn

def log_file_history(file_id, user_id, action, details):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO file_history (file_id, user_id, action, details) VALUES (%s, %s, %s, %s)",
                       (file_id, user_id, action, details))
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error logging file history: {err}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

@staff_api.route('/submit_file', methods=['POST'])
@jwt_required()
def submit_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    data = request.form
    hod_id = data.get('hod_id')
    file_name = data.get('file_name', file.filename)
    file_category = data.get('file_category', 'Personal')
    sensitivity = data.get('sensitivity', 'Normal')

    if not hod_id:
        return jsonify({'error': 'HOD ID is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    filepath = None
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id, department_id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'Uploader user not found'}), 404
        uploader_id = user['id']
        department_id = user['department_id']

        # Determine department for the file
        # Prefer the department provided in the form; if not provided, fall back to uploader's department
        department_name = data.get('department')
        if not department_name:
            # Use uploader's department if available
            if not department_id:
                return jsonify({'error': 'User is not associated with a department and no department provided'}), 400
            # Retrieve department code using uploader's department_id
            cursor.execute("SELECT code FROM departments WHERE id = %s", (department_id,))
            department_data = cursor.fetchone()
            if not department_data:
                return jsonify({'error': 'Department not found'}), 400
            department_code = department_data['code']
        else:
            # Look up department by name (assuming 'name' field exists)
            cursor.execute("SELECT id, code FROM departments WHERE name = %s", (department_name,))
            dept = cursor.fetchone()
            if not dept:
                # Create a new department entry on the fly
                # Generate a simple code (first three letters uppercase) if not provided
                generated_code = department_name[:3].upper()
                cursor.execute(
                    "INSERT INTO departments (name, code) VALUES (%s, %s)",
                    (department_name, generated_code)
                )
                conn.commit()
                department_id = cursor.lastrowid
                department_code = generated_code
            else:
                department_id = dept['id']
                department_code = dept['code']

        cursor.execute("SELECT COUNT(*) as count FROM files WHERE department_id = %s", (department_id,))
        file_count = cursor.fetchone()['count']
        file_number = f"{department_code}-{file_count + 1}"

        upload_folder = os.path.join('backend', 'uploads')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        safe_filename = secure_filename(file.filename)
        filepath = os.path.join(upload_folder, safe_filename)
        file.save(filepath)

        cursor.execute("INSERT INTO files (file_number, filename, filepath, file_category, department_id, uploader_id, sensitivity) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                       (file_number, file_name, filepath, file_category, department_id, uploader_id, sensitivity))
        file_id = cursor.lastrowid

        cursor.execute("INSERT INTO workflows (file_id, sender_id, receiver_id) VALUES (%s, %s, %s)",
                       (file_id, uploader_id, hod_id))

        log_file_history(file_id, uploader_id, 'created', f'File {file_name} uploaded and sent for review.')

        conn.commit()
        return jsonify({'message': 'File submitted for review successfully', 'file_id': file_id, 'file_number': file_number}), 201

    except mysql.connector.Error as err:
        conn.rollback()
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(err)}), 500
    except Exception as e:
        conn.rollback()
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@staff_api.route('/hods', methods=['GET'])
@jwt_required()
def get_hods():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT u.id, u.username FROM users u JOIN roles r ON u.role_id = r.id WHERE r.name = 'HOD'")
        hods = cursor.fetchall()
        return jsonify(hods)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@staff_api.route('/files', methods=['GET'])
@jwt_required()
def get_staff_files():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        user_id = user['id']

        cursor.execute("""
            SELECT f.id, f.file_number, f.filename, w.status, u.username as receiver_name, f.created_at
            FROM files f
            JOIN workflows w ON f.id = w.file_id
            JOIN users u ON w.receiver_id = u.id
            WHERE f.uploader_id = %s
            ORDER BY f.created_at DESC
        """, (user_id,))
        files = cursor.fetchall()
        return jsonify(files)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@staff_api.route('/files/<int:file_id>/history', methods=['GET'])
@jwt_required()
def get_file_history(file_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT fh.action, u.username as user, fh.timestamp, fh.details
            FROM file_history fh
            JOIN users u ON fh.user_id = u.id
            WHERE fh.file_id = %s
            ORDER BY fh.timestamp DESC
        """, (file_id,))
        history = cursor.fetchall()
        return jsonify(history)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@staff_api.route('/inbox', methods=['GET'])
@jwt_required()
def get_inbox():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        user_id = user['id']

        cursor.execute("""
            SELECT w.id as workflow_id, f.file_number, f.filename, u.username as sender_name, w.status, w.received_at
            FROM workflows w
            JOIN files f ON w.file_id = f.id
            JOIN users u ON w.sender_id = u.id
            WHERE w.receiver_id = %s
            ORDER BY w.received_at DESC
        """, (user_id,))
        inbox_items = cursor.fetchall()
        return jsonify(inbox_items)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@staff_api.route('/stats', methods=['GET'])
@jwt_required()
def get_staff_stats():
    """Return simple inbox/workflow stats for the current staff (HOD) user.
    Ex: inbox_count, pending_count, processed_today, overdue_count
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        user_id = user['id']

        # inbox count (all workflows assigned to this user)
        cursor.execute("SELECT COUNT(*) as cnt FROM workflows WHERE receiver_id = %s", (user_id,))
        inbox_count = cursor.fetchone()['cnt']

        # pending count
        cursor.execute("SELECT COUNT(*) as cnt FROM workflows WHERE receiver_id = %s AND status = 'pending'", (user_id,))
        pending_count = cursor.fetchone()['cnt']

        # processed today (any non-pending updated today)
        cursor.execute("SELECT COUNT(*) as cnt FROM workflows WHERE receiver_id = %s AND status != 'pending' AND DATE(updated_at) = CURDATE()", (user_id,))
        processed_today = cursor.fetchone()['cnt']

        # overdue (pending older than 7 days) - heuristic
        cursor.execute("SELECT COUNT(*) as cnt FROM workflows WHERE receiver_id = %s AND status = 'pending' AND created_at < (NOW() - INTERVAL 7 DAY)", (user_id,))
        overdue_count = cursor.fetchone()['cnt']

        return jsonify({
            'inbox_count': inbox_count,
            'pending_count': pending_count,
            'processed_today': processed_today,
            'overdue_count': overdue_count
        })
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@staff_api.route('/workflows/<int:workflow_id>/acknowledge', methods=['PUT'])
@jwt_required()
def acknowledge_file(workflow_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        user_id = user['id']

        # Check if the user is the receiver of this workflow
        cursor.execute("SELECT file_id FROM workflows WHERE id = %s AND receiver_id = %s", (workflow_id, user_id))
        workflow = cursor.fetchone()
        if not workflow:
            return jsonify({'error': 'Forbidden'}), 403

        cursor.execute("UPDATE workflows SET status = 'Acknowledged' WHERE id = %s", (workflow_id,))
        
        log_file_history(workflow['file_id'], user_id, 'acknowledged', f'File acknowledged by {current_username}')

        conn.commit()
        return jsonify({'message': 'File acknowledged successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@staff_api.route('/files/<int:file_id>/request-activation', methods=['POST'])
@jwt_required()
def request_file_activation(file_id):
    """
    Staff member requests activation of an inactive file
    """
    data = request.json
    request_reason = data.get('request_reason')
    
    if not request_reason:
        return jsonify({'error': 'Activation reason is required'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get current user
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        user_id = user['id']
        
        # Check if file exists and is Inactive
        cursor.execute("""
            SELECT id, file_state, filename 
            FROM files 
           WHERE id = %s AND (owner_id = %s OR uploader_id = %s)
        """, (file_id, user_id, user_id))
        
        file_data = cursor.fetchone()
        if not file_data:
            return jsonify({'error': 'File not found or you do not have access'}), 404
        
        if file_data['file_state'] != 'Inactive':
            return jsonify({'error': f'File is already {file_data["file_state"]}'}), 400
        
        # Check if there's already a pending request
        cursor.execute("""
            SELECT id FROM file_activation_requests 
            WHERE file_id = %s AND status = 'pending'
        """, (file_id,))
        
        if cursor.fetchone():
            return jsonify({'error': 'An activation request is already pending for this file'}), 400
        
        # Create activation request
        cursor.execute("""
            INSERT INTO file_activation_requests (file_id, requestor_id, request_reason)
            VALUES (%s, %s, %s)
        """, (file_id, user_id, request_reason))
        
        # Log the request
        log_file_history(file_id, user_id, 'activation_requested', 
                        f'Activation requested: {request_reason}')
        
        conn.commit()
        
        return jsonify({
            'message': 'File activation request submitted successfully',
            'file_id': file_id
        }), 201
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()
