"""
Registry Routes Module
Handles all registry-specific operations including file creation, activation requests,
and file lifecycle management
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import mysql.connector
from datetime import datetime
from functools import wraps
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

print("DEBUG: registry_routes.py loaded")
registry_api = Blueprint('registry_api', __name__)
print(f"DEBUG: Registry Blueprint created: {registry_api}")


# Utility functions (duplicated to avoid circular import)
def get_db_connection():
    """Create and return database connection"""
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )


def log_file_history(file_id, user_id, action, details):
    """Log file history action"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO file_history (file_id, user_id, action, details)
            VALUES (%s, %s, %s, %s)
        """, (file_id, user_id, action, details))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error logging file history: {e}")
    finally:
        cursor.close()
        conn.close()



def permission_required(permission_name):
    """Decorator to check user permissions - MUST be used WITH @jwt_required()"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # jwt_required already called, we can use get_jwt_identity
            current_username = get_jwt_identity()
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            try:
                # Get user's role and check if Admin
                cursor.execute("""
                    SELECT r.name as role_name
                    FROM users u
                    JOIN roles r ON u.role_id = r.id
                    WHERE u.username = %s
                """, (current_username,))
                user_role = cursor.fetchone()
                
                # Admin bypass
                if user_role and user_role['role_name'] == 'Admin':
                    return fn(*args, **kwargs)
                
                # Check specific permission
                cursor.execute("""
                    SELECT COUNT(*) as has_permission
                    FROM users u
                    JOIN role_permissions rp ON u.role_id = rp.role_id
                    JOIN permissions p ON rp.permission_id = p.id
                    WHERE u.username = %s AND p.name = %s
                """, (current_username, permission_name))
                
                result = cursor.fetchone()
                if result and result['has_permission'] > 0:
                    return fn(*args, **kwargs)
                else:
                    return jsonify({'error': 'Permission denied'}), 403
                    
            finally:
                cursor.close()
                conn.close()
                
        return wrapper
    return decorator


def generate_file_number(category, employment_type=None, department_code=None):
    """
    Generate unique file number based on category and type
    Format:
    - Personal: FMCAB/[YEAR]/[TYPE_CODE]/[SERIAL] (e.g., FMCAB/2025/PS/001)
    - Policy: FMCAB/[DEPT_CODE]/[YEAR]/[SERIAL] (e.g., FMCAB/MED/2025/045)
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        year = datetime.now().year
        
        # Get or create counter for this combination
        cursor.execute("""
            SELECT id, last_serial FROM file_number_counters 
            WHERE year = %s AND category = %s 
            AND (employment_type = %s OR (employment_type IS NULL AND %s IS NULL))
            AND (department_code = %s OR (department_code IS NULL AND %s IS NULL))
        """, (year, category, employment_type, employment_type, department_code, department_code))
        
        counter = cursor.fetchone()
        
        if counter:
            # Increment existing counter
            new_serial = counter['last_serial'] + 1
            cursor.execute("""
                UPDATE file_number_counters 
                SET last_serial = %s 
                WHERE id = %s
            """, (new_serial, counter['id']))
        else:
            # Create new counter
            new_serial = 1
            cursor.execute("""
                INSERT INTO file_number_counters 
                (year, category, employment_type, department_code, last_serial)
                VALUES (%s, %s, %s, %s, %s)
            """, (year, category, employment_type, department_code, new_serial))
        
        conn.commit()
        
        # Format file number based on category
        if category == 'Personal':
            type_codes = {
                'Permanent': 'PS',
                'Locum': 'LS',
                'Contract': 'CS',
                'NYSC': 'NYSC'
            }
            type_code = type_codes.get(employment_type, 'PS')
            file_number = f"FMCAB/{year}/{type_code}/{new_serial:03d}"
        else:  # Policy
            file_number = f"FMCAB/{department_code}/{year}/{new_serial:03d}"
        
        return file_number
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()


@registry_api.route('/files', methods=['POST'])
@jwt_required()
def create_file():
    """
    Create new file (Registry only)
    Generates auto-incremented file number based on category
    """
    data = request.json
    file_name = data.get('file_name', '').upper()  # Must be uppercase
    category = data.get('category')  # Personal or Policy
    employment_type = data.get('employment_type')  # For Personal files
    department_id = data.get('department_id')  # For Policy files
    owner_id = data.get('owner_id')
    second_level_auth = data.get('second_level_auth', False)
    
    if not file_name or not category:
        return jsonify({'error': 'File name and category are required'}), 400
    
    if category == 'Personal' and not employment_type:
        return jsonify({'error': 'Employment type required for Personal files'}), 400
    
    if category == 'Policy' and not department_id:
        return jsonify({'error': 'Department required for Policy files'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get department code for Policy files
        department_code = None
        if category == 'Policy':
            cursor.execute("SELECT code FROM departments WHERE id = %s", (department_id,))
            dept = cursor.fetchone()
            if not dept:
                return jsonify({'error': 'Department not found'}), 404
            department_code = dept['code']
        
        # Generate unique file number
        file_number = generate_file_number(category, employment_type, department_code)
        
        # Get current user (Registry personnel)
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        registry_user = cursor.fetchone()
        
        # Create file in Inactive state
        cursor.execute("""
            INSERT INTO files (
                file_number, filename, filepath, file_category, employment_type,
                department_id, uploader_id, owner_id, file_state, progress,
                second_level_auth, status, sensitivity
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            file_number, file_name, '', category, employment_type,
            department_id, registry_user['id'], owner_id, 'Inactive', 'Closed',
            second_level_auth, 'active', 'Normal'
        ))
        
        file_id = cursor.lastrowid
        
        # Log file creation
        log_file_history(file_id, registry_user['id'], 'created', 
                        f'File {file_number} created by Registry')
        
        conn.commit()
        
        return jsonify({
            'message': 'File created successfully',
            'file_id': file_id,
            'file_number': file_number,
            'file_state': 'Inactive'
        }), 201
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@registry_api.route('/activation-requests', methods=['GET'])
@jwt_required()
def get_activation_requests():
    """
    Get all pending file activation requests (Registry only)
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT 
                far.id, far.file_id, far.request_reason, far.status, far.created_at,
                f.file_number, f.filename, f.file_category,
                u.username as requestor_name, u.email as requestor_email,
                d.name as department_name
            FROM file_activation_requests far
            JOIN files f ON far.file_id = f.id
            JOIN users u ON far.requestor_id = u.id
            LEFT JOIN departments d ON f.department_id = d.id
            WHERE far.status = 'pending'
            ORDER BY far.created_at ASC
        """)
        
        requests = cursor.fetchall()
        return jsonify(requests), 200
        
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@registry_api.route('/activation-requests/<int:request_id>/approve', methods=['PUT'])
@jwt_required()
def approve_activation_request(request_id):
    """
    Approve file activation request
    Transitions file from Inactive to Active state
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get activation request details
        cursor.execute("""
            SELECT far.*, f.second_level_auth 
            FROM file_activation_requests far
            JOIN files f ON far.file_id = f.id
            WHERE far.id = %s AND far.status = 'pending'
        """, (request_id,))
        
        activation_request = cursor.fetchone()
        if not activation_request:
            return jsonify({'error': 'Activation request not found or already processed'}), 404
        
        # Check if second-level authorization is required
        if activation_request['second_level_auth']:
            # TODO: Check if HOD has approved (implement in Phase 2)
            pass
        
        # Get current user (Registry)
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        registry_user = cursor.fetchone()
        
        # Update file state to Active
        cursor.execute("""
            UPDATE files 
            SET file_state = 'Active', 
                progress = 'In Action',
                current_location_user_id = %s
            WHERE id = %s
        """, (activation_request['requestor_id'], activation_request['file_id']))
        
        # Update activation request status
        cursor.execute("""
            UPDATE file_activation_requests 
            SET status = 'approved', 
                processed_by = %s,
                processed_at = NOW()
            WHERE id = %s
        """, (registry_user['id'], request_id))
        
        # Log activation
        log_file_history(
            activation_request['file_id'], 
            registry_user['id'], 
            'activated', 
            f'File activated for user ID {activation_request["requestor_id"]}'
        )
        
        conn.commit()
        
        return jsonify({'message': 'File activation approved successfully'}), 200
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@registry_api.route('/activation-requests/<int:request_id>/reject', methods=['PUT'])
@jwt_required()
def reject_activation_request(request_id):
    """
    Reject file activation request
    """
    data = request.json
    rejection_reason = data.get('rejection_reason', 'Not specified')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get current user
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        registry_user = cursor.fetchone()
        
        # Update activation request
        cursor.execute("""
            UPDATE file_activation_requests 
            SET status = 'rejected',
                rejection_reason = %s,
                processed_by = %s,
                processed_at = NOW()
            WHERE id = %s AND status = 'pending'
        """, (rejection_reason, registry_user['id'], request_id))
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Activation request not found or already processed'}), 404
        
        conn.commit()
        
        return jsonify({'message': 'File activation request rejected'}), 200
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@registry_api.route('/files/<int:file_id>/deactivate', methods=['PUT'])
@jwt_required()
def deactivate_file(file_id):
    """
    Deactivate file - return to Inactive state
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get current user
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        registry_user = cursor.fetchone()
        
        # Update file state
        cursor.execute("""
            UPDATE files 
            SET file_state = 'Inactive',
                progress = 'Closed',
                current_location_user_id = NULL
            WHERE id = %s AND file_state = 'Active'
        """, (file_id,))
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'File not found or not currently active'}), 404
        
        # Log deactivation
        log_file_history(file_id, registry_user['id'], 'deactivated', 'File returned to Registry and deactivated')
        
        conn.commit()
        
        return jsonify({'message': 'File deactivated successfully'}), 200
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@registry_api.route('/files/<int:file_id>/archive', methods=['PUT'])
@jwt_required()
def archive_file(file_id):
    """
    Archive file permanently (requires management directive)
    """
    data = request.json
    directive_reference = data.get('directive_reference')
    
    if not directive_reference:
        return jsonify({'error': 'Management directive reference required for archival'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get current user
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        registry_user = cursor.fetchone()
        
        # Update file state to Archived
        cursor.execute("""
            UPDATE files 
            SET file_state = 'Archived',
                progress = 'Closed',
                current_location_user_id = NULL,
                status = 'archived'
            WHERE id = %s
        """, (file_id,))
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'File not found'}), 404
        
        # Log archival with directive reference
        log_file_history(
            file_id, 
            registry_user['id'], 
            'archived', 
            f'File permanently archived. Directive: {directive_reference}'
        )
        
        conn.commit()
        
        return jsonify({'message': 'File archived successfully'}), 200
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()
