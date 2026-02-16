from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'user_management'

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('otp/verify/email/', views.EmailOTPVerifyView.as_view(), name='otp_email_verify'),
    path('password/change/force/', views.ForcePasswordChangeView.as_view(), name='password_change_force'),
    path('locked/', views.custom_lockout_view, name='locked_out_view'), # Added this line
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/<int:pk>/unlock/', views.UserUnlockView.as_view(), name='user_unlock'),
    path('users/<int:pk>/suspend/', views.UserSuspendView.as_view(), name='user_suspend'),
    path('users/<int:pk>/delete/', views.UserDeleteView.as_view(), name='user_delete'),
    path('admin/dashboard/health/', views.AdminDashboardHealthView.as_view(), name='admin_dashboard_health'),
    path('admin/users/batch-upload/', views.UserBatchUploadView.as_view(), name='user_batch_upload'),
    path('admin/users/batch-upload/sample/', views.DownloadSampleUserCSVView.as_view(), name='user_sample_csv'),
    path('profile/', views.UserProfileView.as_view(), name='profile'),
]
