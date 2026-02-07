from django.urls import path
from . import views, report_views

app_name = 'document_management'

urlpatterns = [
    path('registry/', views.RegistryDashboardView.as_view(), name='registry'),
    path('registry/hub/', views.RegistryHubView.as_view(), name='registry_hub'),
    path('executive/dashboard/', views.ExecutiveDashboardView.as_view(), name='executive_dashboard'),
    path('hod/dashboard/', views.HODDashboardView.as_view(), name='hod_dashboard'),
    path('create/', views.FileCreateView.as_view(), name='file_create'),
    path('my-files/', views.MyFilesView.as_view(), name='my_files'),
    path('messages/', views.MessagesView.as_view(), name='messages'),
    path('file/<int:pk>/request-activation/', views.FileRequestActivationView.as_view(), name='file_request_activation'),
    path('file/<int:pk>/approve-activation/', views.FileApproveActivationView.as_view(), name='file_approve_activation'),
    path('file/<int:pk>/recall/', views.FileRecallView.as_view(), name='file_recall'),
    path('file/<int:pk>/close/', views.FileCloseView.as_view(), name='file_close'),
    path('file/<int:pk>/archive/', views.FileArchiveView.as_view(), name='file_archive'),
    path('file/<int:pk>/', views.FileDetailView.as_view(), name='file_detail'),
    path('file/<int:pk>/edit/', views.FileUpdateView.as_view(), name='file_edit'),
    path('file/<int:file_pk>/add-document/', views.DocumentCreateView.as_view(), name='document_add'),
    path('document/upload/', views.DocumentUploadView.as_view(), name='document_upload'),
    path('admin/dashboard/', views.DirectorAdminDashboardView.as_view(), name='admin_dashboard'),
    path('reports/daily-movement/', report_views.DailyFileMovementReportView.as_view(), name='report_daily_movement'),
    path('reports/dept-performance/', report_views.DepartmentPerformanceReportView.as_view(), name='report_dept_performance'),
    path('recipient-search/', views.RecipientSearchView.as_view(), name='recipient_search'),
    path('staff-without-files/', views.StaffWithoutFilesView.as_view(), name='staff_without_files'),
    path('access-requests/', views.FileAccessRequestListView.as_view(), name='access_request_list'),
    path('access-requests/<int:pk>/approve/', views.FileAccessRequestApproveView.as_view(), name='access_request_approve'),
    path('access-requests/<int:pk>/reject/', views.FileAccessRequestRejectView.as_view(), name='access_request_reject'),
    path('staff-search/', views.StaffSearchView.as_view(), name='staff_search'),
    path('document/<int:pk>/delete/', views.DocumentDeleteView.as_view(), name='document_delete'),
    path('document/<int:pk>/share/', views.DocumentShareView.as_view(), name='document_share'),
    path('document/<int:pk>/detail/', views.DocumentDetailView.as_view(), name='document_detail'),
    path('file/<int:pk>/documents/paginate/', views.FileDocumentsView.as_view(), name='file_documents_paginate'),
    path('explorer/', views.RecordExplorerView.as_view(), name='record_explorer'),
]