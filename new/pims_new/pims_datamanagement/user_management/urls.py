from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'user_management'

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('otp/verify/email/', views.EmailOTPVerifyView.as_view(), name='otp_verify_email'),
    path('password/change/force/', views.ForcePasswordChangeView.as_view(), name='password_change_force'),
]
