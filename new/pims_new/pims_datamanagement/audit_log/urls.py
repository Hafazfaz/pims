from django.urls import path

from . import views

app_name = "audit_log"

urlpatterns = [
    path("logs/", views.AuditLogListView.as_view(), name="audit_log_list"),
    path("my-activity/", views.MyActivityReportView.as_view(), name="my_activity_report"),
    path("user-search/", views.ActivityUserSearchView.as_view(), name="activity_user_search"),
    path("export/access-denied/", views.AccessDeniedExportView.as_view(), name="export_access_denied"),
    path("export/full-activity/", views.FullActivityExportView.as_view(), name="export_full_activity"),
]
