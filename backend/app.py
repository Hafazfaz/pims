import os
print("DEBUG: App starting... Loaded updated app.py")
from functools import wraps
from flask import Flask, jsonify, request, Blueprint, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, verify_jwt_in_request
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
import csv
import io
from datetime import datetime

SECRET_KEY = "wuddg283@!8nksgde#@1c6#@" # Hardcoded for debugging
JWT_SECRET_KEY = "supersecret" # Hardcoded for debugging

# Initialize Flask App
# Serve static files from the 'frontend' directory
app = Flask(__name__, 
            static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '../frontend')),
            static_url_path='')
print(f"DEBUG: Static folder path: {app.static_folder}")
print(f"DEBUG: login_index.html exists: {os.path.exists(os.path.join(app.static_folder, 'login_index.html'))}")

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

CORS(app, resources={r"/api/*": {"origins": "*"}})
jwt = JWTManager(app)
app.config["JWT_SECRET_KEY"] = JWT_SECRET_KEY
app.config["SECRET_KEY"] = SECRET_KEY
basedir = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

api = Blueprint('api', __name__)

# Import workflow validation helper (try package and module contexts)
try:
    from backend.workflow import can_transition
except Exception:
    try:
        from workflow import can_transition
    except Exception:
        # fallback: no-op that allows everything (shouldn't happen in production)
        def can_transition(actor_role, actor_id, receiver_id, current_status, requested_status, comment):
            return {'ok': True}

# Database connection
def get_db_connection():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    return conn

# Decorator for permission checking (placeholder)
def permission_required(permission):
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def decorated_function(*args, **kwargs):
            current_username = get_jwt_identity()
            if not current_username:
                return jsonify({'error': 'Unauthorized: No user identity'}), 401

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute('SELECT r.id, r.name FROM users u JOIN roles r ON u.role_id = r.id WHERE u.username = %s', (current_username,))
                user_role = cursor.fetchone()

                if not user_role:
                    return jsonify({'error': 'Unauthorized: User role not found'}), 401

                # Admin bypass
                if user_role['name'] == 'Admin':
                    return f(*args, **kwargs)

                role_id = user_role['id']

                cursor.execute("""
                    SELECT p.name FROM permissions p
                    JOIN role_permissions rp ON p.id = rp.permission_id
                    WHERE rp.role_id = %s AND p.name = %s
                """, (role_id, permission))
                has_permission = cursor.fetchone()

                if not has_permission:
                    return jsonify({'error': f'Forbidden: Missing permission {permission}'}), 403

                return f(*args, **kwargs)
            except mysql.connector.Error as err:
                return jsonify({'error': str(err)}), 500
            finally:
                cursor.close()
                conn.close()
        return decorated_function
    return decorator

# Audit Log (placeholder)
def log_audit(admin_id, modified_user_id, modified_role_id, old_values, new_values, ip_address):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Construct action string if not provided explicitly
        action = "Update"
        details = f"Old: {old_values}, New: {new_values}"
        
        # If new_values is a string like "User created...", treat it as the action/details
        if isinstance(new_values, str) and not old_values:
             action = "Action"
             details = new_values

        cursor.execute("""
            INSERT INTO audit_logs (user_id, role_id, action, details, ip_address)
            VALUES (%s, %s, %s, %s, %s)
        """, (admin_id, modified_role_id, action, details, ip_address))
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error logging audit: {err}")
    finally:
        cursor.close()
        conn.close()

# File History Log
def log_file_history(file_id, user_id, action, details, cursor=None):
    """
    Log file history. If cursor is provided, uses existing transaction.
    Otherwise creates new connection.
    """
    own_connection = cursor is None
    
    if own_connection:
        conn = get_db_connection()
        cursor = conn.cursor()
    
    try:
        cursor.execute("INSERT INTO file_history (file_id, user_id, action, details) VALUES (%s, %s, %s, %s)",
                       (file_id, user_id, action, details))
        
        if own_connection:
            conn.commit()
    except mysql.connector.Error as err:
        print(f"Error logging file history: {err}")
        if own_connection:
            conn.rollback()
    finally:
        if own_connection:
            cursor.close()
            conn.close()

# File Access Log
def log_file_access(file_id, user_id, access_type):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO file_access_logs (file_id, user_id, access_type) VALUES (%s, %s, %s)",
                       (file_id, user_id, access_type))
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error logging file access: {err}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

@api.route('/')
def index():
    print(f"DEBUG: Serving login_index.html from {app.static_folder}/public")
    return send_from_directory(os.path.join(app.static_folder, 'public'), 'login_index.html')

@app.route('/')
def root():
    print(f"DEBUG: Serving login_index.html from {app.static_folder}/public")
    return send_from_directory(os.path.join(app.static_folder, 'public'), 'login_index.html')

# Serve static files from public directory (css, js, img)
@app.route('/public/<path:path>')
def serve_public(path):
    return send_from_directory(os.path.join(app.static_folder, 'public'), path)

# Serve Admin files
@app.route('/admin/<path:path>')
def serve_admin(path):
    return send_from_directory(os.path.join(app.static_folder, 'admin'), path)

# Serve HOD files
@app.route('/hod/<path:path>')
def serve_hod(path):
    return send_from_directory(os.path.join(app.static_folder, 'hod'), path)

# Serve Staff files
@app.route('/staff/<path:path>')
def serve_staff(path):
    return send_from_directory(os.path.join(app.static_folder, 'staff'), path)

# Serve Registry files
@app.route('/registry/<path:path>')
def serve_registry(path):
    return send_from_directory(os.path.join(app.static_folder, 'registry'), path)

# Registry API Routes - MUST be before catchall route!
@app.route('/api/registry/activation-requests', methods=['GET'])
@jwt_required()
def get_registry_activation_requests():
    print("DEBUG: HIT get_registry_activation_requests endpoint!")
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


@app.route('/api/registry/files', methods=['GET'])
@jwt_required()
def get_registry_files():
    """
    Get all files for Registry view
    Includes file state, location, and other details
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        search_query = request.args.get('search')
        
        query = """
            SELECT 
                f.id, f.file_number, f.filename, f.file_category, f.file_state,
                f.created_at, f.current_location_user_id,
                d.name as department_name,
                u.username as current_holder
            FROM files f
            LEFT JOIN departments d ON f.department_id = d.id
            LEFT JOIN users u ON f.current_location_user_id = u.id
        """
        
        params = []
        if search_query:
            query += " WHERE f.filename LIKE %s OR f.file_number LIKE %s"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
            
        query += " ORDER BY f.created_at DESC"
        
        cursor.execute(query, tuple(params))
        files = cursor.fetchall()
        
        return jsonify(files), 200
        
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


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


@app.route('/api/registry/files', methods=['POST'])
@jwt_required()
def create_registry_file():
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
                        f'File {file_number} created by Registry', cursor)
        
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


@app.route('/api/registry/activation-requests/<int:request_id>/approve', methods=['PUT'])
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
            f'File activated for user ID {activation_request["requestor_id"]}',
            cursor
        )
        
        conn.commit()
        
        return jsonify({'message': 'File activation approved successfully'}), 200
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/registry/activation-requests/<int:request_id>/reject', methods=['PUT'])
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


@app.route('/api/registry/files/<int:file_id>/deactivate', methods=['PUT'])
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
        log_file_history(file_id, registry_user['id'], 'deactivated', 'File returned to Registry and deactivated', cursor)
        
        conn.commit()
        
        return jsonify({'message': 'File deactivated successfully'}), 200
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/registry/files/<int:file_id>/archive', methods=['PUT'])
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
            f'File permanently archived. Directive: {directive_reference}',
            cursor
        )
        
        conn.commit()
        
        return jsonify({'message': 'File archived successfully'}), 200
        
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()




# Role Management
@api.route('/roles', methods=['POST'])
@permission_required('create_role')
def create_role():
    data = request.get_json()
    name = data.get('name')
    permissions = data.get('permissions', [])

    if not name:
        return jsonify({'error': 'Role name is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO roles (name) VALUES (%s)', (name,))
        role_id = cursor.lastrowid

        if permissions:
            for perm_id in permissions:
                cursor.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)', (role_id, perm_id))
        
        conn.commit()
        # For audit log, we need the admin_user_id. Assuming it's available from JWT identity.
        admin_username = get_jwt_identity()
        admin_id = None
        if admin_username:
            admin_cursor = conn.cursor()
            admin_cursor.execute('SELECT id FROM users WHERE username = %s', (admin_username,))
            admin_id = admin_cursor.fetchone()[0]
            admin_cursor.close()

        log_audit(admin_id, None, role_id, None, name, request.remote_addr)
        return jsonify({'message': 'Role created successfully', 'id': role_id}), 201
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/roles', methods=['GET'])
@permission_required('read_role')
def get_roles():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id, name FROM roles')
        roles = cursor.fetchall()
        return jsonify(roles)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/roles/<int:role_id>', methods=['PUT'])
@permission_required('update_role')
def update_role(role_id):
    data = request.get_json()
    name = data.get('name')
    permissions = data.get('permissions', [])

    if not name:
        return jsonify({'error': 'Role name is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT name FROM roles WHERE id = %s', (role_id,))
        old_name = cursor.fetchone()['name']

        cursor.execute('UPDATE roles SET name = %s WHERE id = %s', (name, role_id))

        cursor.execute('DELETE FROM role_permissions WHERE role_id = %s', (role_id,))
        if permissions:
            for perm_id in permissions:
                cursor.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)', (role_id, perm_id))

        conn.commit()
        admin_username = get_jwt_identity()
        admin_id = None
        if admin_username:
            admin_cursor = conn.cursor()
            admin_cursor.execute('SELECT id FROM users WHERE username = %s', (admin_username,))
            admin_id = admin_cursor.fetchone()[0]
            admin_cursor.close()
        log_audit(admin_id, None, role_id, old_name, name, request.remote_addr)
        return jsonify({'message': 'Role updated successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/roles/<int:role_id>', methods=['DELETE'])
@permission_required('delete_role')
def delete_role(role_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM role_permissions WHERE role_id = %s', (role_id,))
        cursor.execute('DELETE FROM roles WHERE id = %s', (role_id,))
        conn.commit()
        admin_username = get_jwt_identity()
        admin_id = None
        if admin_username:
            admin_cursor = conn.cursor()
            admin_cursor.execute('SELECT id FROM users WHERE username = %s', (admin_username,))
            admin_id = admin_cursor.fetchone()[0]
            admin_cursor.close()
        log_audit(admin_id, None, role_id, f'deleted role id {role_id}', None, request.remote_addr)
        return jsonify({'message': 'Role deleted successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/roles/<int:role_id>/permissions', methods=['GET'])
@permission_required('read_permission')
def get_role_permissions(role_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT p.id, p.name, p.description FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id = %s
        """, (role_id,))
        permissions = cursor.fetchall()
        return jsonify(permissions)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

# Permission Management
@api.route('/permissions', methods=['GET'])
@permission_required('read_permission')
def get_permissions():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id, name FROM permissions')
        permissions = cursor.fetchall()
        return jsonify(permissions)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/users', methods=['POST'])
@permission_required('create_user')
def create_user():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    role_name = data.get('role')

    if not username or not email or not password or not role_name:
        return jsonify({'error': 'Username, email, password, and role are required'}), 400

    hashed_password = generate_password_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if username already exists
        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            return jsonify({'error': 'Username already exists'}), 409

        # Get role_id from role_name (case-insensitive)
        cursor.execute('SELECT id FROM roles WHERE LOWER(name) = LOWER(%s)', (role_name,))
        role_data = cursor.fetchone()
        if not role_data:
            return jsonify({'error': 'Role not found'}), 400
        role_id = role_data[0]

        cursor.execute('INSERT INTO users (username, email, password_hash, role_id) VALUES (%s, %s, %s, %s)', (username, email, hashed_password, role_id))
        user_id = cursor.lastrowid
        conn.commit()

        admin_username = get_jwt_identity()
        admin_id = None
        if admin_username:
            admin_cursor = conn.cursor()
            admin_cursor.execute('SELECT id FROM users WHERE username = %s', (admin_username,))
            admin_id = admin_cursor.fetchone()[0]
            admin_cursor.close()
        log_audit(admin_id, user_id, role_id, None, f'User {username} created with role {role_name}', request.remote_addr)

        return jsonify({'message': 'User created successfully', 'id': user_id}), 201
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/users/bulk', methods=['POST'])
@permission_required('create_user') # Assuming same permission for bulk create
def bulk_create_users():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and file.filename.endswith('.csv'):
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.reader(stream)
        header = [h.strip() for h in next(csv_input)]  # Read header and strip whitespace

        # Expected columns
        expected_columns = ['Username', 'Email', 'Password', 'Role']
        if not all(col in header for col in expected_columns):
            return jsonify({'error': f'CSV header must contain: {", ".join(expected_columns)}'}), 400

        users_to_add = []
        errors = []
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # Fetch all roles once to map role names to IDs efficiently
            cursor.execute('SELECT id, name FROM roles')
            roles_map = {role['name'].lower(): role['id'] for role in cursor.fetchall()}

            for i, row in enumerate(csv_input):
                if not row:  # Skip empty rows
                    continue
                
                row_data = dict(zip(header, [r.strip() for r in row])) # Strip whitespace from row values
                
                username = row_data.get('Username')
                email = row_data.get('Email')
                password = row_data.get('Password')
                role_name = row_data.get('Role')

                if not all([username, email, password, role_name]):
                    errors.append(f'Row {i+2}: Missing data in one or more required columns (Username, Email, Password, Role).') # i+2 for 1-based indexing and header row
                    continue

                # Check if username already exists
                cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
                if cursor.fetchone():
                    errors.append(f'Row {i+2}: Username \'{username}\' already exists.')
                    continue

                role_id = roles_map.get(role_name.lower())
                if not role_id:
                    errors.append(f'Row {i+2}: Role \'{role_name}\' not found.')
                    continue

                hashed_password = generate_password_hash(password)
                users_to_add.append((username, email, hashed_password, role_id))
            
            if errors:
                conn.rollback()
                return jsonify({'errors': errors}), 400

            if not users_to_add:
                return jsonify({'message': 'No valid users to add from CSV'}), 200

            # Bulk insert valid users
            insert_query = 'INSERT INTO users (username, email, password_hash, role_id) VALUES (%s, %s, %s, %s)'
            cursor.executemany(insert_query, users_to_add)
            conn.commit()

            admin_username = get_jwt_identity()
            admin_id = None
            if admin_username:
                admin_cursor = conn.cursor()
                admin_cursor.execute('SELECT id FROM users WHERE username = %s', (admin_username,))
                admin_id = admin_cursor.fetchone()[0]
                admin_cursor.close()
            
            for user_data in users_to_add:
                username = user_data[0]
                email = user_data[1]
                role_id = user_data[3]
                log_audit(admin_id, None, role_id, None, f'Bulk created user {username} ({email})', request.remote_addr)

            return jsonify({'message': f'Successfully created {len(users_to_add)} users.'}), 201

        except mysql.connector.Error as err:
            conn.rollback()
            return jsonify({'error': str(err)}), 500
        except Exception as e:
            conn.rollback()
            return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500
        finally:
            cursor.close()
            conn.close()
    else:
        return jsonify({'error': 'Invalid file type. Please upload a CSV file.'}), 400

@api.route('/users', methods=['GET'])
@permission_required('read_user')
def get_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT u.id, u.username, u.email, r.name as role, u.is_active FROM users u JOIN roles r ON u.role_id = r.id')
        users = cursor.fetchall()
        return jsonify(users)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@api.route('/users/count', methods=['GET'])
@jwt_required()
def get_users_count():
    """Return total users count (for dashboard KPI)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM users')
        total = cursor.fetchone()[0]
        return jsonify({'total_users': total})
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@api.route('/stats/overview', methods=['GET'])
@jwt_required()
def stats_overview():
    """Return a small set of overview KPIs for admin dashboard.
    Fields: total_users, active_files, pending_approvals, overdue_tasks
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # total users
        cursor.execute('SELECT COUNT(*) as cnt FROM users')
        total_users = cursor.fetchone()['cnt']

        # active files (not archived)
        try:
            cursor.execute("SELECT COUNT(*) as cnt FROM files WHERE status IS NULL OR status != 'archived'")
            active_files = cursor.fetchone()['cnt']
        except Exception:
            # If status column not present or other schema differences, fallback to total files
            cursor.execute('SELECT COUNT(*) as cnt FROM files')
            active_files = cursor.fetchone()['cnt']

        # pending approvals - workflows with status 'pending'
        try:
            cursor.execute("SELECT COUNT(*) as cnt FROM workflows WHERE status = 'pending'")
            pending_approvals = cursor.fetchone()['cnt']
        except Exception:
            pending_approvals = 0

        # overdue tasks - workflows pending older than 7 days
        try:
            cursor.execute("SELECT COUNT(*) as cnt FROM workflows WHERE status = 'pending' AND created_at < (NOW() - INTERVAL 7 DAY)")
            overdue_tasks = cursor.fetchone()['cnt']
        except Exception:
            overdue_tasks = 0

        return jsonify({
            'total_users': total_users,
            'active_files': active_files,
            'pending_approvals': pending_approvals,
            'overdue_tasks': overdue_tasks
        })
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@api.route('/admin/users', methods=['POST'])
@jwt_required()
def admin_create_user():
    """Admin-only endpoint to create a user and assign a role by name.
    Expects JSON: { username, email, password, role }
    """
    data = request.get_json() or {}
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    role_name = data.get('role')

    if not username or not email or not password or not role_name:
        return jsonify({'error': 'username, email, password and role are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # verify current user is admin
        current_username = get_jwt_identity()
        cursor.execute("SELECT r.name FROM users u JOIN roles r ON u.role_id = r.id WHERE u.username = %s", (current_username,))
        row = cursor.fetchone()
        if not row or row[0].lower() != 'admin':
            return jsonify({'error': 'Forbidden: admin role required'}), 403

        # check username uniqueness
        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            return jsonify({'error': 'Username already exists'}), 409

        # look up role id
        cursor.execute('SELECT id FROM roles WHERE LOWER(name) = LOWER(%s)', (role_name,))
        role_row = cursor.fetchone()
        if not role_row:
            return jsonify({'error': 'Role not found'}), 400
        role_id = role_row[0]

        hashed = generate_password_hash(password)
        cursor.execute('INSERT INTO users (username, email, password_hash, role_id) VALUES (%s, %s, %s, %s)', (username, email, hashed, role_id))
        user_id = cursor.lastrowid
        conn.commit()

        # audit
        admin_id = None
        cursor.execute('SELECT id FROM users WHERE username = %s', (current_username,))
        arow = cursor.fetchone()
        if arow:
            admin_id = arow[0]
        log_audit(admin_id, user_id, role_id, None, f'User {username} created by admin', request.remote_addr)

        return jsonify({'message': 'User created successfully', 'id': user_id}), 201
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/users/<int:user_id>', methods=['GET'])
@permission_required('read_user')
def get_user_by_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT u.id, u.username, u.email, r.name as role, u.is_active FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = %s', (user_id,))
        user = cursor.fetchone()
        if user:
            return jsonify(user)
        return jsonify({'error': 'User not found'}), 404
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/users/<int:user_id>/status', methods=['PUT'])
@permission_required('update_user')
def update_user_status(user_id):
    data = request.get_json()
    is_active = data.get('is_active')

    if is_active is None:
        return jsonify({'error': 'is_active status is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE users SET is_active = %s WHERE id = %s', (is_active, user_id))
        conn.commit()
        return jsonify({'message': 'User status updated successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/users/<int:user_id>', methods=['PUT'])
@permission_required('update_user')
def update_user(user_id):
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    role_name = data.get('role')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get role_id from role_name
        role_id = None
        if role_name:
            cursor.execute('SELECT id FROM roles WHERE name = %s', (role_name,))
            role_data = cursor.fetchone()
            if not role_data:
                return jsonify({'error': 'Role not found'}), 400
            role_id = role_data[0]

        updates = []
        params = []
        if username:
            updates.append('username = %s')
            params.append(username)
        if email:
            updates.append('email = %s')
            params.append(email)
        if role_id:
            updates.append('role_id = %s')
            params.append(role_id)

        if not updates:
            return jsonify({'message': 'No fields to update'}), 200

        params.append(user_id)
        query = f'UPDATE users SET {", ".join(updates)} WHERE id = %s'
        cursor.execute(query, tuple(params))
        conn.commit()
        return jsonify({'message': 'User updated successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/users/<int:user_id>', methods=['DELETE'])
@permission_required('delete_user')
def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        conn.commit()
        return jsonify({'message': 'User deleted successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()



# Department Management
@api.route('/departments', methods=['GET'])
@permission_required('read_department')
def get_departments():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT d.id, d.name, d.code, u.username as head_name FROM departments d LEFT JOIN users u ON d.head_id = u.id")
        departments = cursor.fetchall()
        return jsonify(departments)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/departments/<int:department_id>', methods=['GET'])
@permission_required('read_department')
def get_department(department_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, name, code, head_id FROM departments WHERE id = %s", (department_id,))
        department = cursor.fetchone()
        if department:
            return jsonify(department)
        return jsonify({'error': 'Department not found'}), 404
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/departments', methods=['POST'])
@permission_required('create_department')
def create_department():
    data = request.get_json()
    name = data.get('name')
    code = data.get('code')
    head_id = data.get('head_id')

    if not name or not code:
        return jsonify({'error': 'Department name and code are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO departments (name, code, head_id) VALUES (%s, %s, %s)", (name, code, head_id))
        conn.commit()
        department_id = cursor.lastrowid
        return jsonify({'id': department_id, 'name': name, 'code': code, 'head_id': head_id}), 201
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/departments/<int:department_id>', methods=['PUT'])
@permission_required('update_department')
def update_department(department_id):
    data = request.get_json()
    name = data.get('name')
    code = data.get('code')
    head_id = data.get('head_id')

    if not name or not code:
        return jsonify({'error': 'Department name and code are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE departments SET name = %s, code = %s, head_id = %s WHERE id = %s", (name, code, head_id, department_id))
        conn.commit()
        return jsonify({'message': 'Department updated successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/departments/<int:department_id>', methods=['DELETE'])
@permission_required('delete_department')
def delete_department(department_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM departments WHERE id = %s", (department_id,))
        conn.commit()
        return jsonify({'message': 'Department deleted successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

# File Management



@api.route('/files/<int:file_id>', methods=['GET'])
@jwt_required()
@permission_required('read_file')
def get_file(file_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
                f.id, f.file_number, f.filename, f.file_category, 
                f.department_id, d.name as department_name, u.username as uploader_name, 
                f.status, f.sensitivity, f.created_at, f.expires_at,
                GROUP_CONCAT(DISTINCT ft.tag SEPARATOR ',') as tags
            FROM files f 
            JOIN departments d ON f.department_id = d.id 
            JOIN users u ON f.uploader_id = u.id
            LEFT JOIN file_tags ft ON f.id = ft.file_id
            WHERE f.id = %s
            GROUP BY f.id
        """, (file_id,))
        file = cursor.fetchone()
        if file:
            file['tags'] = [tag.strip() for tag in file['tags'].split(',')] if file['tags'] else []
            return jsonify(file)
        return jsonify({'error': 'File not found'}), 404
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/files/<int:file_id>/download', methods=['GET'])
@jwt_required()
@permission_required('download_file')
def download_file(file_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT filename, filepath FROM files WHERE id = %s", (file_id,))
        file_data = cursor.fetchone()

        if not file_data:
            return jsonify({'error': 'File not found'}), 404

        filepath = file_data['filepath']
        filename = file_data['filename']

        # Log file access
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found for logging'}), 404
        user_id = user['id']
        log_file_access(file_id, user_id, 'download')

        return send_from_directory(app.config['UPLOAD_FOLDER'], os.path.basename(filepath), as_attachment=True, download_name=filename)

    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/files/<int:file_id>', methods=['PUT'])
@jwt_required()
@permission_required('update_file')
def update_file(file_id):
    data = request.get_json()
    file_name = data.get('file_name')
    file_category = data.get('file_category')
    department_id = data.get('department_id')
    sensitivity = data.get('sensitivity')
    status = data.get('status')
    expires_at = data.get('expires_at')
    tags_str = data.get('tags')

    updates = []
    params = []

    if file_name:
        updates.append('filename = %s')
        params.append(file_name)
    if file_category:
        updates.append('file_category = %s')
        params.append(file_category)
    if department_id:
        updates.append('department_id = %s')
        params.append(department_id)
    if sensitivity:
        updates.append('sensitivity = %s')
        params.append(sensitivity)
    if status:
        updates.append('status = %s')
        params.append(status)
    if expires_at:
        updates.append('expires_at = %s')
        params.append(expires_at)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get current file details for logging
        cursor.execute("SELECT filename FROM files WHERE id = %s", (file_id,))
        file_data = cursor.fetchone()
        if not file_data:
            return jsonify({'error': 'File not found'}), 404
        old_filename = file_data[0]

        if updates:
            params.append(file_id)
            query = f'UPDATE files SET {", ".join(updates)} WHERE id = %s'
            cursor.execute(query, tuple(params))
        
        # Update tags in file_tags table
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found for logging'}), 404
        user_id = user['id']

        if tags_str is not None: # Check if tags were provided in the request
            cursor.execute("DELETE FROM file_tags WHERE file_id = %s", (file_id,))
            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
            for tag in tags:
                cursor.execute("INSERT INTO file_tags (file_id, tag) VALUES (%s, %s)", (file_id, tag))

        # Log file update in file_history
        log_file_history(file_id, user_id, 'updated', f'File {old_filename} updated.')

        conn.commit()
        return jsonify({'message': 'File updated successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/files/<int:file_id>', methods=['DELETE'])
@jwt_required()
@permission_required('delete_file')
def delete_file(file_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    filepath = None
    try:
        # Get file path and filename before deleting from DB
        cursor.execute("SELECT filename, filepath FROM files WHERE id = %s", (file_id,))
        file_data = cursor.fetchone()
        if not file_data:
            return jsonify({'error': 'File not found'}), 404
        
        filename = file_data[0]
        filepath = file_data[1]

        cursor.execute("DELETE FROM file_tags WHERE file_id = %s", (file_id,))
        cursor.execute("DELETE FROM file_history WHERE file_id = %s", (file_id,))
        cursor.execute("DELETE FROM file_access_logs WHERE file_id = %s", (file_id,))
        cursor.execute("DELETE FROM files WHERE id = %s", (file_id,))
        
        # Log file deletion in file_history
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found for logging'}), 404
        user_id = user['id']
        log_file_history(file_id, user_id, 'deleted', f'File {filename} deleted.')

        conn.commit()

        # Delete the physical file
        if filepath and os.path.exists(filepath):
            os.remove(filepath)

        return jsonify({'message': 'File deleted successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/files/<int:file_id>/history', methods=['GET'])
@jwt_required()
@permission_required('read_file_history')
def get_file_history(file_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT fh.action, u.username as user, fh.timestamp, fh.details FROM file_history fh JOIN users u ON fh.user_id = u.id WHERE fh.file_id = %s ORDER BY fh.timestamp DESC", (file_id,))
        history = cursor.fetchall()
        return jsonify(history)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/files/<int:file_id>/access_logs', methods=['GET'])
@jwt_required()
@permission_required('read_file_access_logs')
def get_file_access_logs(file_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT fal.access_type, u.username as user, fal.timestamp FROM file_access_logs fal JOIN users u ON fal.user_id = u.id WHERE fal.file_id = %s ORDER BY fal.timestamp DESC", (file_id,))
        access_logs = cursor.fetchall()
        return jsonify(access_logs)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/files', methods=['POST'])
@jwt_required()
@permission_required('create_document')
def upload_file():
    print("DEBUG: upload_file endpoint called")
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    data = request.form
    file_category = data.get('file_category')
    department_id = data.get('department_id')
    sensitivity = data.get('sensitivity')
    expires_at = data.get('expires_at')
    tags_str = data.get('tags')

    if not file_category or not department_id or not sensitivity:
        return jsonify({'error': 'File category, department, and sensitivity are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    filepath = None
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'Uploader user not found'}), 404
        uploader_id = user['id']

        cursor.execute("SELECT code FROM departments WHERE id = %s", (department_id,))
        department_data = cursor.fetchone()
        if not department_data:
            return jsonify({'error': 'Department not found'}), 400
        department_code = department_data['code']

        # Generate file number
        cursor.execute("SELECT COUNT(*) as count FROM files WHERE department_id = %s", (department_id,))
        file_count = cursor.fetchone()['count']
        file_number = f"{department_code}-{file_count + 1}"

        # Save the file
        original_filename = file.filename
        safe_filename = secure_filename(original_filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(filepath)

        # Insert into database
        cursor.execute("INSERT INTO files (file_number, filename, filepath, file_category, department_id, uploader_id, sensitivity, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", 
                       (file_number, original_filename, filepath, file_category, department_id, uploader_id, sensitivity, expires_at))
        file_id = cursor.lastrowid
        
        # Insert tags into file_tags table
        if tags_str:
            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
            for tag in tags:
                cursor.execute("INSERT INTO file_tags (file_id, tag) VALUES (%s, %s)", (file_id, tag))

        # Log file creation in file_history
        log_file_history(file_id, uploader_id, 'created', f'File {original_filename} uploaded.')
        
        conn.commit()
        return jsonify({'message': 'File uploaded successfully', 'file_id': file_id, 'file_number': file_number}), 201

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

@api.route('/files', methods=['GET'])
@jwt_required()
@permission_required('read_document')
def get_files():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Search functionality
        search_query = request.args.get('search')
        
        base_query = """
            SELECT f.id, f.file_number, f.filename, f.file_category, d.name as department_name, 
                   u.username as uploader_name, f.created_at, f.status,
                   f.file_state, f.current_location_user_id, f.owner_id, f.uploader_id
            FROM files f
            JOIN departments d ON f.department_id = d.id
            JOIN users u ON f.uploader_id = u.id
        """
        
        if search_query:
            base_query += " WHERE f.filename LIKE %s OR f.file_number LIKE %s"
            params = (f"%{search_query}%", f"%{search_query}%")
            cursor.execute(base_query, params)
        else:
            cursor.execute(base_query)
            
        files = cursor.fetchall()
        return jsonify(files)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/files/bulk', methods=['POST'])
@jwt_required()
@permission_required('create_document')
def bulk_upload_files():
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files part'}), 400

    files = request.files.getlist('files[]')
    if not files:
        return jsonify({'error': 'No selected files'}), 400

    data = request.form
    file_category = data.get('file_category')
    department_id = data.get('department_id')
    sensitivity = data.get('sensitivity')
    expires_at = data.get('expires_at')
    tags_str = data.get('tags')

    if not file_category or not department_id or not sensitivity:
        return jsonify({'error': 'File category, department, and sensitivity are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    uploaded_files_info = []
    errors = []

    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'Uploader user not found'}), 404
        uploader_id = user['id']

        cursor.execute("SELECT code FROM departments WHERE id = %s", (department_id,))
        department_data = cursor.fetchone()
        if not department_data:
            return jsonify({'error': 'Department not found'}), 400
        department_code = department_data['code']

        for file in files:
            filepath = None # Initialize filepath for each file
            if file.filename == '':
                errors.append({'filename': 'N/A', 'error': 'No selected file'})
                continue

            try:
                # Generate file number
                cursor.execute("SELECT COUNT(*) as count FROM files WHERE department_id = %s", (department_id,))
                file_count = cursor.fetchone()['count']
                file_number = f"{department_code}-{file_count + 1}"

                # Save the file
                original_filename = file.filename
                safe_filename = secure_filename(original_filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
                file.save(filepath)

                # Insert into database
                cursor.execute("INSERT INTO files (file_number, filename, filepath, file_category, department_id, uploader_id, sensitivity, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", 
                               (file_number, original_filename, filepath, file_category, department_id, uploader_id, sensitivity, expires_at))
                file_id = cursor.lastrowid
                
                # Insert tags into file_tags table
                if tags_str:
                    tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                    for tag in tags:
                        cursor.execute("INSERT INTO file_tags (file_id, tag) VALUES (%s, %s)", (file_id, tag))

                # Log file creation in file_history
                log_file_history(file_id, uploader_id, 'created', f'File {original_filename} uploaded.')
                
                uploaded_files_info.append({'filename': original_filename, 'file_id': file_id, 'file_number': file_number})

            except mysql.connector.Error as err:
                errors.append({'filename': file.filename, 'error': str(err)})
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                errors.append({'filename': file.filename, 'error': str(e)})
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
        
        conn.commit()
        if errors:
            return jsonify({'message': 'Some files failed to upload', 'uploaded': uploaded_files_info, 'errors': errors}), 207 # Multi-Status
        return jsonify({'message': 'All files uploaded successfully', 'uploaded': uploaded_files_info}), 201

    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')


    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT u.id, u.username, u.password_hash, u.email, u.role_id, r.name as role_name FROM users u JOIN roles r ON u.role_id = r.id WHERE u.username = %s', (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            identity_data = user['username']
            role = user['role_name']
            print(f"DEBUG: Identity data for token creation: {identity_data}, role: {role}")
            access_token = create_access_token(identity=identity_data, additional_claims={'role': role})
            return jsonify(access_token=access_token)
        else:
            return jsonify({'error': 'Invalid credentials'}), 401

    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@api.route('/me', methods=['GET'])
@jwt_required()
def me():
    """Return basic information about the current authenticated user."""
    current_username = get_jwt_identity()
    if not current_username:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT u.id, u.username, u.email, u.department_id, r.name as role FROM users u JOIN roles r ON u.role_id = r.id WHERE u.username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify(user)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/hods', methods=['GET'])
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

@api.route('/workflows/submit', methods=['POST'])
@jwt_required()
def submit_file_for_review():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    data = request.form
    hod_id = data.get('hod_id')
    file_name = data.get('file_name', file.filename) # Use provided name or original filename
    file_category = data.get('file_category', 'Personal') # Default to Personal
    sensitivity = data.get('sensitivity', 'Normal') # Default to Normal

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

        if not department_id:
            return jsonify({'error': 'User is not associated with a department'}), 400

        cursor.execute("SELECT code FROM departments WHERE id = %s", (department_id,))
        department_data = cursor.fetchone()
        if not department_data:
            return jsonify({'error': 'Department not found'}), 400
        department_code = department_data['code']

        cursor.execute("SELECT COUNT(*) as count FROM files WHERE department_id = %s", (department_id,))
        file_count = cursor.fetchone()['count']
        file_number = f"{department_code}-{file_count + 1}"

        safe_filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(filepath)

        cursor.execute("INSERT INTO files (file_number, filename, filepath, file_category, department_id, uploader_id, sensitivity) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                       (file_number, file_name, filepath, file_category, department_id, uploader_id, sensitivity))
        file_id = cursor.lastrowid

        # Workflow Creation Logic
        if workflow_template_id:
            # Template-based workflow
            cursor.execute("SELECT * FROM workflow_steps WHERE template_id = %s ORDER BY step_order ASC", (workflow_template_id,))
            steps = cursor.fetchall()
            if not steps:
                raise Exception("Selected workflow template has no steps")
            
            first_step = steps[0]
            
            # Create workflow instance
            cursor.execute("""
                INSERT INTO workflows (file_id, template_id, current_step_id, sender_id, receiver_id, status) 
                VALUES (%s, %s, %s, %s, %s, 'pending')
            """, (file_id, workflow_template_id, first_step['id'], uploader_id, None)) # receiver_id is null, handled by role
            
            log_file_history(file_id, uploader_id, 'created', f'File {file_name} uploaded and workflow started (Template ID: {workflow_template_id}).')

        elif hod_id:
            # Legacy/Ad-hoc workflow (Sender -> HOD)
            cursor.execute("INSERT INTO workflows (file_id, sender_id, receiver_id) VALUES (%s, %s, %s)",
                           (file_id, uploader_id, hod_id))
            log_file_history(file_id, uploader_id, 'created', f'File {file_name} uploaded and sent for review to HOD.')
        
        else:
            # No workflow (just upload)
            log_file_history(file_id, uploader_id, 'created', f'File {file_name} uploaded.')

        conn.commit()
        return jsonify({'message': 'File uploaded successfully', 'file_id': file_id, 'file_number': file_number}), 201

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


@api.route('/workflows/<int:workflow_id>', methods=['PUT'])
@jwt_required()
def update_workflow_status(workflow_id):
    """Update workflow status (approve/reject) by the receiver (HOD) or admin.
    Expects JSON: { "status": "approved"|"rejected" , "comment": "optional" }
    """
    data = request.get_json() or {}
    status = data.get('status')
    comment = data.get('comment')

    if not status:
        return jsonify({'error': 'Status is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        current_username = get_jwt_identity()
        # get current user id and role
        cursor.execute("SELECT u.id, r.name as role_name FROM users u JOIN roles r ON u.role_id = r.id WHERE u.username = %s", (current_username,))
        user_row = cursor.fetchone()
        if not user_row:
            return jsonify({'error': 'User not found'}), 404
        user_id = user_row['id']
        role_name = user_row.get('role_name')

        # fetch workflow
        cursor.execute("SELECT id, file_id, sender_id, receiver_id, status FROM workflows WHERE id = %s", (workflow_id,))
        workflow = cursor.fetchone()
        if not workflow:
            return jsonify({'error': 'Workflow not found'}), 404
        
        file_id = workflow['file_id']  # Extract file_id for logging

        # Validate transition using workflow helper
        validation = can_transition(role_name, user_id, workflow['receiver_id'], workflow['status'], status, comment)
        if not validation.get('ok'):
            t = validation.get('type')
            msg = validation.get('message', 'Transition not allowed')
            if t == 'forbidden':
                return jsonify({'error': msg}), 403
            if t == 'comment_required':
                return jsonify({'error': msg}), 400
            return jsonify({'error': msg}), 422

        # Update workflow status
        if workflow.get('template_id'):
            # Multi-step logic
            if status == 'approved':
                # Find next step
                cursor.execute("SELECT * FROM workflow_steps WHERE template_id = %s AND step_order > (SELECT step_order FROM workflow_steps WHERE id = %s) ORDER BY step_order ASC LIMIT 1", 
                               (workflow['template_id'], workflow['current_step_id']))
                next_step = cursor.fetchone()
                
                if next_step:
                    # Move to next step
                    cursor.execute("UPDATE workflows SET current_step_id = %s, status = 'pending', updated_at = NOW() WHERE id = %s", 
                                   (next_step['id'], workflow_id))
                    log_file_history(file_id, user_id, 'approved', f'Workflow step approved. Moved to next step (Role ID: {next_step["role_id"]}).')
                else:
                    # Final approval
                    cursor.execute("UPDATE workflows SET status = 'approved', current_step_id = NULL, comment = %s, updated_at = NOW() WHERE id = %s", (comment, workflow_id))
                    log_file_history(file_id, user_id, 'approved', 'Workflow completed and fully approved.')
            else:
                # Rejected
                cursor.execute("UPDATE workflows SET status = 'rejected', comment = %s, updated_at = NOW() WHERE id = %s", (comment, workflow_id))
                log_file_history(file_id, user_id, 'rejected', f'Workflow rejected by {current_username}.')
        else:
            # Legacy logic
            cursor.execute("UPDATE workflows SET status = %s, comment = %s, updated_at = NOW() WHERE id = %s", (status, comment, workflow_id))
            log_file_history(file_id, user_id, status, comment or f'Workflow {status} by {current_username}')
            
            # Update file state when workflow is approved
            if status == 'approved':
                cursor.execute("UPDATE files SET file_state = 'Active' WHERE id = %s", (file_id,))

        conn.commit()
        return jsonify({'message': 'Workflow updated successfully'})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


@api.route('/workflows/bulk', methods=['PUT'])
@jwt_required()
def bulk_update_workflows():
    """Update multiple workflows' status in bulk. Expects JSON: { workflow_ids: [1,2,3], status: 'approved'| 'rejected' }
    Only the designated receiver for each workflow or Admin can update that workflow.
    """
    data = request.get_json() or {}
    workflow_ids = data.get('workflow_ids', [])
    status = data.get('status')
    comment = data.get('comment')

    if not workflow_ids or not isinstance(workflow_ids, list) or not status:
        return jsonify({'error': 'workflow_ids (list) and status are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT u.id, r.name as role_name FROM users u JOIN roles r ON u.role_id = r.id WHERE u.username = %s", (current_username,))
        user_row = cursor.fetchone()
        if not user_row:
            return jsonify({'error': 'User not found'}), 404
        user_id = user_row['id']
        role_name = user_row.get('role_name')

        updated = []
        errors = []
        for wid in workflow_ids:
            cursor.execute("SELECT id, file_id, receiver_id, status FROM workflows WHERE id = %s", (wid,))
            wf = cursor.fetchone()
            if not wf:
                errors.append({'id': wid, 'error': 'not found'})
                continue

            # Validate transition for this workflow
            validation = can_transition(role_name, user_id, wf['receiver_id'], wf.get('status'), status, comment)
            if not validation.get('ok'):
                errors.append({'id': wid, 'error': validation.get('message', 'not allowed')})
                continue

            cursor.execute("UPDATE workflows SET status = %s, comment = %s, updated_at = NOW() WHERE id = %s", (status, comment, wid))
            log_file_history(wf['file_id'], user_id, status, comment or f'Bulk {status} by {current_username}')
            updated.append(wid)

        conn.commit()
        return jsonify({'updated': updated, 'errors': errors})
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

# Workflow Templates Management
@api.route('/workflow-templates', methods=['POST'])
@permission_required('create_workflow_template')
def create_workflow_template():
    data = request.get_json()
    name = data.get('name')
    description = data.get('description')
    department_id = data.get('department_id')
    steps = data.get('steps', []) # List of {step_order, role_id, action_type}

    if not name:
        return jsonify({'error': 'Template name is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO workflow_templates (name, description, department_id) VALUES (%s, %s, %s)", 
                       (name, description, department_id))
        template_id = cursor.lastrowid

        for step in steps:
            cursor.execute("INSERT INTO workflow_steps (template_id, step_order, role_id, action_type) VALUES (%s, %s, %s, %s)",
                           (template_id, step.get('step_order'), step.get('role_id'), step.get('action_type', 'approval')))
        
        conn.commit()
        return jsonify({'message': 'Workflow template created', 'id': template_id}), 201
    except mysql.connector.Error as err:
        conn.rollback()
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@api.route('/workflow-templates', methods=['GET'])
@jwt_required()
def get_workflow_templates():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM workflow_templates")
        templates = cursor.fetchall()
        return jsonify(templates)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

# Analytics Endpoint
@api.route('/analytics/stats', methods=['GET'])
@jwt_required()
@permission_required('view_reports') # Assuming 'view_reports' permission exists, or use 'admin' role check
def get_analytics_stats():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = conn.cursor(dictionary=True)

        # 1. Key Metrics
        cursor.execute("SELECT COUNT(*) as total FROM files")
        total_files = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as active FROM files WHERE status != 'archived'") # Assuming 'archived' status exists or similar
        active_files = cursor.fetchone()['active']

        cursor.execute("SELECT COUNT(*) as pending FROM workflows WHERE status = 'pending' OR status = 'in_progress'")
        pending_approvals = cursor.fetchone()['pending']

        # Overdue: Files with expires_at in the past and not completed (simplified)
        cursor.execute("SELECT COUNT(*) as overdue FROM files WHERE expires_at < NOW()")
        overdue_tasks = cursor.fetchone()['overdue']

        # 2. Files per Department
        cursor.execute("""
            SELECT d.name, COUNT(f.id) as count 
            FROM departments d 
            LEFT JOIN files f ON d.id = f.department_id 
            GROUP BY d.id
        """)
        files_per_dept = cursor.fetchall()

        # 3. Files Created Over Time (Last 7 Days)
        cursor.execute("""
            SELECT DATE(created_at) as date, COUNT(*) as count 
            FROM files 
            WHERE created_at >= DATE(NOW()) - INTERVAL 7 DAY 
            GROUP BY DATE(created_at) 
            ORDER BY date ASC
        """)
        files_over_time = cursor.fetchall()
        # Format dates as strings
        files_over_time = [{'date': str(item['date']), 'count': item['count']} for item in files_over_time]

        # 4. File Status Distribution
        cursor.execute("SELECT status, COUNT(*) as count FROM files GROUP BY status")
        status_distribution = cursor.fetchall()


        return jsonify({
            'total_files': total_files,
            'active_files': active_files,
            'pending_approvals': pending_approvals,
            'overdue_tasks': overdue_tasks,
            'files_per_department': files_per_dept,
            'files_over_time': files_over_time,
            'status_distribution': status_distribution
        })

    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

@api.route('/workflow-templates/<int:template_id>', methods=['GET'])
@jwt_required()
def get_workflow_template_details(template_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM workflow_templates WHERE id = %s", (template_id,))
        template = cursor.fetchone()
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        
        cursor.execute("SELECT ws.*, r.name as role_name FROM workflow_steps ws JOIN roles r ON ws.role_id = r.id WHERE ws.template_id = %s ORDER BY ws.step_order", (template_id,))
        steps = cursor.fetchall()
        template['steps'] = steps
        return jsonify(template)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()


# ============================================
# FILE ARCHIVAL & COMPLETION ENDPOINTS
# ============================================

@api.route('/registry/archive-file/<int:file_id>', methods=['PUT'])
@jwt_required()
def archive_file(file_id):
    """
    Permanently archive a file (Registry only)
    Requires: management directive reference
    Sets file to read-only archived state
    """
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify user has registry role
        cursor.execute("SELECT role FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user or user['role'] != 'registry':
            return jsonify({'error': 'Unauthorized - Registry role required'}), 403
        
        # Get request data
        data = request.json or {}
        directive_ref = data.get('directive_reference', '')
        notes = data.get('notes', '')
        
        if not directive_ref:
            return jsonify({'error': 'Management directive reference required'}), 400
        
        # Verify file exists
        cursor.execute("SELECT file_number, file_name FROM files WHERE id = %s", (file_id,))
        file = cursor.fetchone()
        
        if not file:
            return jsonify({'error': 'File not found'}), 404
        
        # Update file state to Archived
        cursor.execute("""
            UPDATE files 
            SET file_state = 'Archived', 
                updated_at = NOW()
            WHERE id = %s
        """, (file_id,))
        
        # Log to file_history
        cursor.execute("""
            INSERT INTO file_history 
            (file_id, action, performed_by, notes, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (file_id, 'Archived', current_username, f"Directive: {directive_ref}. {notes}"))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'File {file["file_number"]} permanently archived',
            'file_id': file_id,
            'directive_reference': directive_ref
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@api.route('/registry/complete-file/<int:file_id>', methods=['PUT'])
@jwt_required()
def complete_file(file_id):
    """
    Mark a file as completed (Registry only)
    File has completed its workflow cycle
    """
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify user has registry role
        cursor.execute("SELECT role FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user or user['role'] != 'registry':
            return jsonify({'error': 'Unauthorized - Registry role required'}), 403
        
        # Get request data
        data = request.json or {}
        notes = data.get('notes', '')
        
        # Verify file exists
        cursor.execute("SELECT file_number, file_name, owner_id FROM files WHERE id = %s", (file_id,))
        file = cursor.fetchone()
        
        if not file:
            return jsonify({'error': 'File not found'}), 404
        
        # Update file state to Completed
        cursor.execute("""
            UPDATE files 
            SET file_state = 'Completed', 
                updated_at = NOW()
            WHERE id = %s
        """, (file_id,))
        
        # Log to file_history
        cursor.execute("""
            INSERT INTO file_history 
            (file_id, action, performed_by, notes, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (file_id, 'Completed', current_username, notes if notes else 'File workflow completed'))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'File {file["file_number"]} marked as completed',
            'file_id': file_id
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@api.route('/admin/bulk-users', methods=['POST'])
@jwt_required()
def bulk_create_users():
    """
    Bulk create users from CSV file (Admin only)
    CSV format: username,full_name,email,role,department_id
    Returns detailed success/failure report
    """
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify user has admin role
        cursor.execute("SELECT role FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user or user['role'] != 'admin':
            return jsonify({'error': 'Unauthorized - Admin role required'}), 403
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'File must be CSV format'}), 400
        
        # Read CSV content
        import csv
        import io
        
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)
        
        results = {
            'success_count': 0,
            'failure_count': 0,
            'successes': [],
            'failures': []
        }
        
        # Default password for all new users
        default_password = 'ChangeMe123!'
        hashed_password = generate_password_hash(default_password)
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
            try:
                username = row.get('username', '').strip()
                full_name = row.get('full_name', '').strip()
                email = row.get('email', '').strip()
                role = row.get('role', '').strip().lower()
                department_id = row.get('department_id', '').strip()
                
                # Validate required fields
                if not username or not full_name or not role:
                    results['failures'].append({
                        'row': row_num,
                        'username': username,
                        'error': 'Missing required fields (username, full_name, or role)'
                    })
                    results['failure_count'] += 1
                    continue
                
                # Validate role
                valid_roles = ['admin', 'hod', 'registry', 'staff']
                if role not in valid_roles:
                    results['failures'].append({
                        'row': row_num,
                        'username': username,
                        'error': f'Invalid role: {role}. Must be one of {valid_roles}'
                    })
                    results['failure_count'] += 1
                    continue
                
                # Check if username already exists
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                if cursor.fetchone():
                    results['failures'].append({
                        'row': row_num,
                        'username': username,
                        'error': 'Username already exists'
                    })
                    results['failure_count'] += 1
                    continue
                
                # Insert user
                cursor.execute("""
                    INSERT INTO users 
                    (username, password, full_name, email, role, department_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """, (username, hashed_password, full_name, email if email else None, 
                      role, int(department_id) if department_id else None))
                
                results['successes'].append({
                    'row': row_num,
                    'username': username,
                    'full_name': full_name,
                    'role': role
                })
                results['success_count'] += 1
                
            except Exception as e:
                results['failures'].append({
                    'row': row_num,
                    'username': row.get('username', 'unknown'),
                    'error': str(e)
                })
                results['failure_count'] += 1
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Processed {results["success_count"] + results["failure_count"]} users',
            'default_password': default_password,
            'results': results
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============================================
# FILE SEARCH API (HIGH PRIORITY)
# ============================================

@api.route('/registry/search-files', methods=['GET'])
@jwt_required()
def search_files():
    """
    Comprehensive file search API
    Supports multiple search criteria:
    - q: Quick search (file number or name)
    - file_number: Exact file number
    - file_name: File name (partial match)
    - category: File category
    - status: File state
    - date_from: Created after date
    - date_to: Created before date
    - owner_id: File owner
    - department_id: Owner's department
    - limit: Results limit (default 50, max 200)
    """
    current_username = get_jwt_identity()
    
    # Get all search parameters
    quick_search = request.args.get('q', '').strip()
    file_number = request.args.get('file_number', '').strip()
    file_name = request.args.get('file_name', '').strip()
    category = request.args.get('category', '').strip()
    status = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    owner_id = request.args.get('owner_id', '').strip()
    department_id = request.args.get('department_id', '').strip()
    limit = min(int(request.args.get('limit', 50)), 200)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Build dynamic query
        query = """
            SELECT 
                f.id,
                f.file_number,
                f.file_name,
                f.category,
                f.file_state,
                f.created_at,
                f.updated_at,
                u.username as owner_username,
                u.full_name as owner_name,
                d.name as department_name,
                (SELECT COUNT(*) FROM file_history WHERE file_id = f.id) as action_count
            FROM files f
            LEFT JOIN users u ON f.owner_id = u.id
            LEFT JOIN departments d ON u.department_id = d.id
            WHERE 1=1
        """
        
        params = []
        
        # Quick search (file number OR file name)
        if quick_search:
            query += " AND (f.file_number LIKE %s OR f.file_name LIKE %s)"
            search_term = f"%{quick_search}%"
            params.extend([search_term, search_term])
        
        # Specific file number search
        if file_number:
            query += " AND f.file_number LIKE %s"
            params.append(f"%{file_number}%")
        
        # File name search
        if file_name:
            query += " AND f.file_name LIKE %s"
            params.append(f"%{file_name}%")
        
        # Category filter
        if category:
            query += " AND f.category = %s"
            params.append(category)
        
        # Status filter
        if status:
            query += " AND f.file_state = %s"
            params.append(status)
        
        # Date range filters
        if date_from:
            query += " AND DATE(f.created_at) >= %s"
            params.append(date_from)
        
        if date_to:
            query += " AND DATE(f.created_at) <= %s"
            params.append(date_to)
        
        # Owner filter
        if owner_id:
            query += " AND f.owner_id = %s"
            params.append(int(owner_id))
        
        # Department filter
        if department_id:
            query += " AND u.department_id = %s"
            params.append(int(department_id))
        
        # Order by most recent first
        query += " ORDER BY f.updated_at DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # Format results
        files = []
        for row in results:
            files.append({
                'id': row['id'],
                'file_number': row['file_number'],
                'file_name': row['file_name'],
                'category': row['category'],
                'status': row['file_state'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
                'owner': {
                    'username': row['owner_username'],
                    'full_name': row['owner_name'],
                    'department': row['department_name']
                },
                'action_count': row['action_count']
            })
        
        # Get total count (without limit)
        count_query = query.rsplit('ORDER BY', 1)[0]  # Remove ORDER BY and LIMIT
        count_params = params[:-1]  # Remove limit param
        
        cursor.execute(f"SELECT COUNT(*) as total FROM ({count_query}) as subquery", count_params)
        total_count = cursor.fetchone()['total']
        
        return jsonify({
            'success': True,
            'total': total_count,
            'returned': len(files),
            'limit': limit,
            'filters_applied': {
                'quick_search': quick_search if quick_search else None,
                'file_number': file_number if file_number else None,
                'file_name': file_name if file_name else None,
                'category': category if category else None,
                'status': status if status else None,
                'date_from': date_from if date_from else None,
                'date_to': date_to if date_to else None,
                'owner_id': owner_id if owner_id else None,
                'department_id': department_id if department_id else None
            },
            'files': files
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@api.route('/registry/search-suggestions', methods=['GET'])
@jwt_required()
def search_suggestions():
    """
    Get search suggestions for autocomplete
    Returns unique values for categories, file numbers, etc.
    """
    suggestion_type = request.args.get('type', 'category')  # category, file_number, owner
    query = request.args.get('q', '').strip()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        if suggestion_type == 'category':
            cursor.execute("""
                SELECT DISTINCT category 
                FROM files 
                WHERE category IS NOT NULL 
                AND category LIKE %s
                LIMIT 10
            """, (f"%{query}%",))
            
            suggestions = [row['category'] for row in cursor.fetchall()]
            
        elif suggestion_type == 'file_number':
            cursor.execute("""
                SELECT file_number, file_name
                FROM files 
                WHERE file_number LIKE %s
                LIMIT 10
            """, (f"%{query}%",))
            
            suggestions = [
                {'number': row['file_number'], 'name': row['file_name']} 
                for row in cursor.fetchall()
            ]
            
        elif suggestion_type == 'owner':
            cursor.execute("""
                SELECT DISTINCT u.id, u.username, u.full_name
                FROM users u
                JOIN files f ON u.id = f.owner_id
                WHERE u.full_name LIKE %s OR u.username LIKE %s
                LIMIT 10
            """, (f"%{query}%", f"%{query}%"))
            
            suggestions = [
                {'id': row['id'], 'username': row['username'], 'name': row['full_name']}
                for row in cursor.fetchall()
            ]
        else:
            suggestions = []
        
        return jsonify({
            'success': True,
            'type': suggestion_type,
            'suggestions': suggestions
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============================================
# USER EXPORT API (ADMIN)
# ============================================

@api.route('/admin/export-users', methods=['GET'])
@jwt_required()
def export_users():
    """
    Export all users to CSV file
    Admin only - for reports, backups, data analysis
    """
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify admin role
        cursor.execute("SELECT role FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        
        if not user or user['role'] != 'admin':
            return jsonify({'error': 'Unauthorized - Admin role required'}), 403
        
        # Get all users with department info
        cursor.execute("""
            SELECT 
                u.id,
                u.username,
                u.full_name,
                u.email,
                u.role,
                d.name as department_name,
                u.created_at,
                (SELECT COUNT(*) FROM files WHERE owner_id = u.id) as file_count
            FROM users u
            LEFT JOIN departments d ON u.department_id = d.id
            ORDER BY u.created_at DESC
        """)
        
        users = cursor.fetchall()
        
        # Generate CSV
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'ID', 'Username', 'Full Name', 'Email', 'Role', 
            'Department', 'Created Date', 'File Count'
        ])
        
        # Write data
        for user_row in users:
            writer.writerow([
                user_row['id'],
                user_row['username'],
                user_row['full_name'],
                user_row['email'] or '',
                user_row['role'],
                user_row['department_name'] or 'N/A',
                user_row['created_at'].strftime('%Y-%m-%d') if user_row['created_at'] else '',
                user_row['file_count']
            ])
        
        # Prepare response
        csv_data = output.getvalue()
        output.close()
        
        from flask import make_response
        response = make_response(csv_data)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============================================
# DELEGATION API (HOD)
# ============================================

@api.route('/hod/delegate', methods=['POST'])
@jwt_required()
def create_delegation():
    """
    HOD delegates authority to another user temporarily
    For leave, official duty, etc.
    """
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify HOD role
        cursor.execute("SELECT id, role, department_id FROM users WHERE username = %s", (current_username,))
        hod = cursor.fetchone()
        
        if not hod or hod['role'] != 'hod':
            return jsonify({'error': 'Unauthorized - HOD role required'}), 403
        
        # Get request data
        data = request.json
        delegate_to_user_id = data.get('delegate_to_user_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        reason = data.get('reason', '')
        
        if not all([delegate_to_user_id, start_date, end_date]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Verify delegate user exists
        cursor.execute("SELECT id, username, full_name FROM users WHERE id = %s", (delegate_to_user_id,))
        delegate = cursor.fetchone()
        
        if not delegate:
            return jsonify({'error': 'Delegate user not found'}), 404
        
        # Create delegation record
        cursor.execute("""
            INSERT INTO delegations 
            (hod_user_id, delegate_user_id, start_date, end_date, reason, status, created_at)
            VALUES (%s, %s, %s, %s, %s, 'active', NOW())
        """, (hod['id'], delegate_to_user_id, start_date, end_date, reason))
        
        delegation_id = cursor.lastrowid
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Authority delegated to {delegate["full_name"]} from {start_date} to {end_date}',
            'delegation_id': delegation_id,
            'delegate': {
                'id': delegate['id'],
                'username': delegate['username'],
                'full_name': delegate['full_name']
            },
            'period': {
                'start': start_date,
                'end': end_date
            }
        }), 201
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@api.route('/hod/delegations', methods=['GET'])
@jwt_required()
def get_delegations():
    """
    Get all delegations for current HOD
    Shows active, past, and upcoming delegations
    """
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get HOD user
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        hod = cursor.fetchone()
        
        if not hod:
            return jsonify({'error': 'User not found'}), 404
        
        # Get all delegations
        cursor.execute("""
            SELECT 
                d.*,
                u.username as delegate_username,
                u.full_name as delegate_name
            FROM delegations d
            JOIN users u ON d.delegate_user_id = u.id
            WHERE d.hod_user_id = %s
            ORDER BY d.created_at DESC
        """, (hod['id'],))
        
        delegations = cursor.fetchall()
        
        # Format results
        result = {
            'active': [],
            'upcoming': [],
            'past': []
        }
        
        from datetime import date
        today = date.today()
        
        for deleg in delegations:
            item = {
                'id': deleg['id'],
                'delegate': {
                    'id': deleg['delegate_user_id'],
                    'username': deleg['delegate_username'],
                    'full_name': deleg['delegate_name']
                },
                'start_date': deleg['start_date'].isoformat() if deleg['start_date'] else None,
                'end_date': deleg['end_date'].isoformat() if deleg['end_date'] else None,
                'reason': deleg['reason'],
                'status': deleg['status'],
                'created_at': deleg['created_at'].isoformat() if deleg['created_at'] else None
            }
            
            # Categorize by date
            if deleg['start_date'] and deleg['end_date']:
                if deleg['start_date'] <= today <= deleg['end_date'] and deleg['status'] == 'active':
                    result['active'].append(item)
                elif deleg['start_date'] > today:
                    result['upcoming'].append(item)
                else:
                    result['past'].append(item)
        
        return jsonify({
            'success': True,
            'delegations': result
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@api.route('/hod/delegations/<int:delegation_id>', methods=['DELETE'])
@jwt_required()
def cancel_delegation(delegation_id):
    """
    Cancel a delegation (only if not yet started or currently active)
    """
    current_username = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get HOD user
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        hod = cursor.fetchone()
        
        # Verify delegation belongs to this HOD
        cursor.execute("""
            SELECT * FROM delegations 
            WHERE id = %s AND hod_user_id = %s
        """, (delegation_id, hod['id']))
        
        delegation = cursor.fetchone()
        
        if not delegation:
            return jsonify({'error': 'Delegation not found'}), 404
        
        # Update status to cancelled
        cursor.execute("""
            UPDATE delegations 
            SET status = 'cancelled'
            WHERE id = %s
        """, (delegation_id,))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Delegation cancelled successfully'
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============================================
# BLUEPRINT REGISTRATION
# ============================================

from staff_routes import staff_api
# from registry_routes import registry_api  # Temporarily disabled - routes moved to app.py
from document_routes import document_api
from notification_routes import notification_api
from analytics_routes import analytics_api

app.register_blueprint(api, url_prefix='/api')
app.register_blueprint(staff_api, url_prefix='/api/staff')
app.register_blueprint(document_api, url_prefix='/api')
app.register_blueprint(notification_api, url_prefix='/api')
app.register_blueprint(analytics_api, url_prefix='/api/analytics')
# app.register_blueprint(registry_api, url_prefix='/api/registry')  # Temporarily disabled
print(f"DEBUG: Registered notification_api blueprint")
print(f"DEBUG: Registered analytics_api blueprint")
print(f"DEBUG: Registered registry_api blueprint with {len([r for r in app.url_map.iter_rules() if 'registry' in str(r)])} registry routes")
for rule in app.url_map.iter_rules():
    print(f"  - {rule}")


# Fallback for other static files (if any) or shared resources
@app.route('/<path:path>')
def serve_static(path):
    # Try public first
    if os.path.exists(os.path.join(app.static_folder, 'public', path)):
        return send_from_directory(os.path.join(app.static_folder, 'public'), path)
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        conn.database = DB_NAME
        # Initialize DB
        with app.app_context():
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
            with open(schema_path, 'r') as f:
                sql_script = f.read()

            sql_statements = sql_script.split(';')

            for statement in sql_statements:
                if statement.strip():
                    cursor.execute(statement)
            
            conn.commit()
            print("Database setup successful")

    except mysql.connector.Error as err:
        print(f"Error during database setup: {err}")

    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

    # Force reload
    app.run(debug=True)