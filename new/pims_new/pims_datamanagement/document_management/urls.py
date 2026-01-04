from django.urls import path
from . import views

app_name = 'document_management'

urlpatterns = [
    path('registry/dashboard/', views.RegistryDashboardView.as_view(), name='registry_dashboard'),
    path('create/', views.FileCreateView.as_view(), name='file_create'),
    path('my-files/', views.MyFilesView.as_view(), name='my_files'),
    path('file/<int:pk>/request-activation/', views.FileRequestActivationView.as_view(), name='file_request_activation'),
    path('file/<int:pk>/approve-activation/', views.FileApproveActivationView.as_view(), name='file_approve_activation'),
    path('file/<int:pk>/', views.FileDetailView.as_view(), name='file_detail'),
    path('file/<int:pk>/edit/', views.FileUpdateView.as_view(), name='file_edit'),
    path('document/upload/', views.DocumentUploadView.as_view(), name='document_upload'), # New URL pattern
]
