from django.urls import path
from . import views

app_name = 'audit_log'

urlpatterns = [
    path('logs/', views.AuditLogListView.as_view(), name='audit_log_list'),
]
