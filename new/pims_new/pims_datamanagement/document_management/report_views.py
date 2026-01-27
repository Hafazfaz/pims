import csv
from django.shortcuts import render
from django.http import HttpResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .reports import get_daily_file_movement_report, get_department_performance_report
from django.utils import timezone

class DailyFileMovementReportView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser or (hasattr(self.request.user, 'staff') and self.request.user.staff.is_hod)

    def get(self, request):
        report_data = get_daily_file_movement_report()
        
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="daily_file_movement_{timezone.now().date()}.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['Metric', 'Count'])
            writer.writerow(['Files Created', report_data['created_count']])
            writer.writerow(['Files Activated', report_data['activated_count']])
            writer.writerow(['Files Moved', report_data['moved_count']])
            
            writer.writerow([])
            writer.writerow(['Detailed Created Files'])
            writer.writerow(['File Number', 'Title', 'Owner'])
            for f in report_data['created_files']:
                writer.writerow([f.file_number, f.title, f.owner])
                
            return response

        return render(request, 'document_management/report_daily_movement.html', {'report': report_data})

class DepartmentPerformanceReportView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser or (hasattr(self.request.user, 'staff') and self.request.user.staff.is_hod)

    def get(self, request):
        report_data = get_department_performance_report()
        
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="dept_performance_{timezone.now().date()}.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['Department', 'Total Files Owned', 'Active Files', 'Files Currently Pending'])
            for row in report_data:
                writer.writerow([row['department'], row['total_files_owned'], row['active_files'], row['files_currently_pending']])
                
            return response

        return render(request, 'document_management/report_dept_performance.html', {'report_data': report_data})
