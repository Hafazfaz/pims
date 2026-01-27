from django.db.models import Count, Avg, F
from django.utils import timezone
from datetime import timedelta
from .models import File
from organization.models import Department
from audit_log.models import AuditLogEntry

def get_daily_file_movement_report(date=None):
    """
    Generates a report of file movements and status changes for a specific date.
    Default date is today.
    """
    if date is None:
        date = timezone.now().date()
    
    # Files created on this date
    created_files = File.objects.filter(created_at__date=date)
    
    # Files activated on this date (based on AuditLog)
    activated_logs = AuditLogEntry.objects.filter(
        action='FILE_ACTIVATED', 
        timestamp__date=date
    )
    activated_files_ids = activated_logs.values_list('object_id', flat=True)
    activated_files = File.objects.filter(pk__in=activated_files_ids)

    # Files moved (sent) on this date (based on AuditLog)
    moved_logs = AuditLogEntry.objects.filter(
        action='FILE_SENT',
        timestamp__date=date
    )
    moved_files_stats = moved_logs.count()
    
    return {
        'date': date,
        'created_count': created_files.count(),
        'activated_count': activated_files.count(),
        'moved_count': moved_files_stats,
        'created_files': created_files,
        'activated_files': activated_files,
    }

def get_department_performance_report(days=30):
    """
    Generates performance metrics per department over the last N days.
    """
    start_date = timezone.now() - timedelta(days=days)
    
    report_data = []
    departments = Department.objects.all()
    
    for dept in departments:
        # Files owned by this department (or staff in it)
        dept_files = File.objects.filter(department=dept)
        
        # Files processed (e.g., closed) in the last N days
        closed_count = dept_files.filter(
            status='closed', 
            # Assuming we can track when it was closed via audit log or checking modified date if we added one (File doesn't have updated_at, relying on AuditLog for precise timing would be complex for aggregate, simply filtering by status for now or using created_at for "throughput" proxy)
        ).count()
        
        # Total active files
        active_count = dept_files.filter(status='active').count()
        
        # Detailed: Find files currently located in this department (bottleneck analysis)
        # Assuming current_location (Staff) maps to this department
        files_currently_with_dept = File.objects.filter(current_location__department=dept).count()
        
        report_data.append({
            'department': dept.name,
            'total_files_owned': dept_files.count(),
            'active_files': active_count,
            'files_currently_pending': files_currently_with_dept,
            # 'avg_processing_time': calculate_avg_processing_time(dept, start_date) # Placeholder for advanced logic
        })
        
    return report_data
