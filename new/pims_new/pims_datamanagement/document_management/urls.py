from django.urls import path
from . import views, report_views

app_name = 'document_management'

urlpatterns = [
    path('registry/dashboard/', views.RegistryDashboardView.as_view(), name='registry_dashboard'),
    path('hod/dashboard/', views.HODDashboardView.as_view(), name='hod_dashboard'),
    path('create/', views.FileCreateView.as_view(), name='file_create'),
    path('my-files/', views.MyFilesView.as_view(), name='my_files'),
    path('file/<int:pk>/request-activation/', views.FileRequestActivationView.as_view(), name='file_request_activation'),
    path('file/<int:pk>/approve-activation/', views.FileApproveActivationView.as_view(), name='file_approve_activation'),
    path('file/<int:pk>/close/', views.FileCloseView.as_view(), name='file_close'),
    path('file/<int:pk>/archive/', views.FileArchiveView.as_view(), name='file_archive'),
    path('file/<int:pk>/', views.FileDetailView.as_view(), name='file_detail'),
    path('file/<int:pk>/edit/', views.FileUpdateView.as_view(), name='file_edit'),
    path('document/upload/', views.DocumentUploadView.as_view(), name='document_upload'),
    path('admin/dashboard/', views.DirectorAdminDashboardView.as_view(), name='admin_dashboard'),
    path('reports/daily-movement/', report_views.DailyFileMovementReportView.as_view(), name='report_daily_movement'),
    path('reports/dept-performance/', report_views.DepartmentPerformanceReportView.as_view(), name='report_dept_performance'),
    path('recipient-search/', views.RecipientSearchView.as_view(), name='recipient_search'),
    path('access-requests/', views.FileAccessRequestListView.as_view(), name='access_request_list'),
    path('access-requests/<int:pk>/approve/', views.FileAccessRequestApproveView.as_view(), name='access_request_approve'),
    path('access-requests/<int:pk>/reject/', views.FileAccessRequestRejectView.as_view(), name='access_request_reject'),
]