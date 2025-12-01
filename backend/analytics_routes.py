"""
Analytics API Routes
Provides statistics, reports, and system health monitoring
Backend-only endpoints for dashboard data visualization
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from functools import wraps
from db_config import get_db_connection
from datetime import datetime, timedelta

analytics_api = Blueprint('analytics_api', __name__)


def role_required(allowed_roles):
    """Decorator to restrict endpoints by role"""
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            current_username = get_jwt_identity()
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            try:
                cursor.execute("SELECT role FROM users WHERE username = %s", (current_username,))
                user = cursor.fetchone()
                
                if not user or user['role'] not in allowed_roles:
                    return jsonify({'error': f'Unauthorized - Requires one of: {allowed_roles}'}), 403
                
                return fn(*args, **kwargs)
            finally:
                cursor.close()
                conn.close()
        
        return wrapper
    return decorator


# ============================================
# DEPARTMENT STATISTICS
# ============================================

@analytics_api.route('/department/<int:dept_id>/stats', methods=['GET'])
@role_required(['admin', 'hod'])
def get_department_stats(dept_id):
    """
    Get comprehensive statistics for a department
    Accessible by Admin and HOD roles
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get department info
        cursor.execute("SELECT name FROM departments WHERE id = %s", (dept_id,))
        dept = cursor.fetchone()
        
        if not dept:
            return jsonify({'error': 'Department not found'}), 404
        
        # Files processed (last 30 days)
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM file_history fh
            JOIN users u ON fh.performed_by = u.username
            WHERE u.department_id = %s 
            AND fh.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            AND fh.action IN ('approved', 'completed')
        """, (dept_id,))
        files_processed = cursor.fetchone()['count']
        
        # Average processing time (hours)
        cursor.execute("""
            SELECT AVG(TIMESTAMPDIFF(HOUR, f.created_at, fh.created_at)) as avg_hours
            FROM files f
            JOIN file_history fh ON f.id = fh.file_id
            JOIN users u ON f.owner_id = u.id
            WHERE u.department_id = %s
            AND fh.action = 'completed'
            AND f.created_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
        """, (dept_id,))
        result = cursor.fetchone()
        avg_processing_time = round(result['avg_hours'] or 0, 2)
        
        # Overdue files
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM files f
            JOIN users u ON f.owner_id = u.id
            WHERE u.department_id = %s
            AND f.file_state IN ('active', 'in_progress')
            AND TIMESTAMPDIFF(HOUR, f.updated_at, NOW()) > 48
        """, (dept_id,))
        overdue_files = cursor.fetchone()['count']
        
        # Staff count and workload
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT u.id) as staff_count,
                COUNT(f.id) as total_files,
                ROUND(COUNT(f.id) / NULLIF(COUNT(DISTINCT u.id), 0), 2) as avg_files_per_staff
            FROM users u
            LEFT JOIN files f ON u.id = f.owner_id AND f.file_state IN ('active', 'in_progress')
            WHERE u.department_id = %s AND u.role = 'staff'
        """, (dept_id,))
        workload = cursor.fetchone()
        
        # Files by state
        cursor.execute("""
            SELECT 
                f.file_state,
                COUNT(*) as count
            FROM files f
            JOIN users u ON f.owner_id = u.id
            WHERE u.department_id = %s
            GROUP BY f.file_state
        """, (dept_id,))
        files_by_state = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'department': {
                'id': dept_id,
                'name': dept['name']
            },
            'performance': {
                'files_processed_30d': files_processed,
                'avg_processing_hours': avg_processing_time,
                'overdue_files': overdue_files
            },
            'workload': {
                'staff_count': workload['staff_count'],
                'total_active_files': workload['total_files'],
                'avg_files_per_staff': float(workload['avg_files_per_staff'] or 0)
            },
            'files_by_state': {item['file_state']: item['count'] for item in files_by_state}
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============================================
# SYSTEM HEALTH MONITORING
# ============================================

@analytics_api.route('/system/health', methods=['GET'])
@role_required(['admin'])
def get_system_health():
    """
    System health check and monitoring
    Admin only - shows database status, recent errors, activity
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        health_data = {
            'timestamp': datetime.now().isoformat(),
            'status': 'healthy'
        }
        
        # Database connection test
        cursor.execute("SELECT 1")
        health_data['database'] = {
            'status': 'connected',
            'timestamp': datetime.now().isoformat()
        }
        
        # Table counts
        tables = ['users', 'files', 'departments', 'file_history', 'document_workflow']
        table_counts = {}
        
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                table_counts[table] = cursor.fetchone()['count']
            except:
                table_counts[table] = 'error'
        
        health_data['database']['table_counts'] = table_counts
        
        # Recent activity (last 24 hours)
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT user_id) as active_users,
                COUNT(*) as total_actions
            FROM file_history
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """)
        activity = cursor.fetchone()
        health_data['activity_24h'] = activity
        
        # Files created today
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM files
            WHERE DATE(created_at) = CURDATE()
        """)
        health_data['files_created_today'] = cursor.fetchone()['count']
        
        # Pending workflows
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM document_workflow
            WHERE status = 'pending'
        """)
        health_data['pending_workflows'] = cursor.fetchone()['count']
        
        # System alerts (overdue files > 72 hours)
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM files
            WHERE file_state IN ('active', 'in_progress')
            AND TIMESTAMPDIFF(HOUR, updated_at, NOW()) > 72
        """)
        overdue_count = cursor.fetchone()['count']
        
        health_data['alerts'] = {
            'overdue_files_72h': overdue_count,
            'severity': 'high' if overdue_count > 10 else 'medium' if overdue_count > 5 else 'low'
        }
        
        return jsonify({
            'success': True,
            'health': health_data
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'unhealthy',
            'error': str(e)
        }), 500
    finally:
        cursor.close()
        conn.close()


# ============================================
# USER ACTIVITY REPORTS
# ============================================

@analytics_api.route('/users/activity', methods=['GET'])
@role_required(['admin', 'hod'])
def get_user_activity():
    """
    User activity report
    Shows who's been active, file actions, login patterns
    """
    # Get query parameters
    days = int(request.args.get('days', 7))  # Default last 7 days
    department_id = request.args.get('department_id', None)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Build query based on filters
        base_query = """
            SELECT 
                u.id,
                u.username,
                u.full_name,
                u.role,
                d.name as department,
                COUNT(fh.id) as actions_count,
                MAX(fh.created_at) as last_activity,
                GROUP_CONCAT(DISTINCT fh.action) as action_types
            FROM users u
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN file_history fh ON u.username = fh.performed_by 
                AND fh.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        """
        
        params = [days]
        
        if department_id:
            base_query += " WHERE u.department_id = %s"
            params.append(int(department_id))
        
        base_query += """ 
            GROUP BY u.id, u.username, u.full_name, u.role, d.name
            ORDER BY actions_count DESC, last_activity DESC
        """
        
        cursor.execute(base_query, params)
        users = cursor.fetchall()
        
        # Format results
        activity_report = []
        for user in users:
            activity_report.append({
                'user_id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'],
                'role': user['role'],
                'department': user['department'],
                'actions_count': user['actions_count'] or 0,
                'last_activity': user['last_activity'].isoformat() if user['last_activity'] else None,
                'action_types': user['action_types'].split(',') if user['action_types'] else []
            })
        
        return jsonify({
            'success': True,
            'period_days': days,
            'total_users': len(activity_report),
            'active_users': len([u for u in activity_report if u['actions_count'] > 0]),
            'users': activity_report
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============================================
# FILE STATISTICS
# ============================================

@analytics_api.route('/files/statistics', methods=['GET'])
@role_required(['admin', 'registry', 'hod'])
def get_file_statistics():
    """
    Overall file statistics
    File counts by state, category, recent trends
    """
    period = request.args.get('period', '30')  # days
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        stats = {}
        
        # Files by state
        cursor.execute("""
            SELECT file_state, COUNT(*) as count
            FROM files
            GROUP BY file_state
        """)
        stats['by_state'] = {row['file_state']: row['count'] for row in cursor.fetchall()}
        
        # Files by category
        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM files
            WHERE category IS NOT NULL
            GROUP BY category
        """)
        stats['by_category'] = {row['category']: row['count'] for row in cursor.fetchall()}
        
        # Trend (files created per day for last N days)
        cursor.execute(f"""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as count
            FROM files
            WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL {int(period)} DAY)
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """)
        stats['daily_trend'] = [
            {'date': row['date'].isoformat(), 'count': row['count']} 
            for row in cursor.fetchall()
        ]
        
        # Total counts
        cursor.execute("SELECT COUNT(*) as total FROM files")
        stats['total_files'] = cursor.fetchone()['total']
        
        cursor.execute("""
            SELECT COUNT(*) as count FROM files 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        """)
        stats['created_last_30_days'] = cursor.fetchone()['count']
        
        return jsonify({
            'success': True,
            'period_days': int(period),
            'statistics': stats
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
