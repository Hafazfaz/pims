from django.contrib.auth.backends import ModelBackend
from django.utils import timezone
from datetime import timedelta
from .models import CustomUser
from audit_log.utils import log_action # Import audit logging utility
from notifications.utils import create_notification, notify_admins_of_critical_event # Import notification utilities
from django.urls import reverse

MAX_FAILED_ATTEMPTS = 3
LOCKOUT_DURATION_MINUTES = 15

class CustomOTPBackend( ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # First, try to authenticate with the default ModelBackend
        user = super().authenticate(request, username, password, **kwargs)

        if username:
            try:
                custom_user = CustomUser.objects.get(username=username)
            except CustomUser.DoesNotExist:
                custom_user = None

            if custom_user:
                # Check if the user is currently locked out
                if custom_user.lockout_until and custom_user.lockout_until > timezone.now():
                    # Account is locked, prevent login
                    if request: # Only set error message if request is available
                        # Store lockout message in session to display it later in the login view
                        request.session['lockout_message'] = f"Account locked until {custom_user.lockout_until.strftime('%H:%M')}. Please try again later."
                        request.session['locked_username'] = username # Store username for potential custom_lockout_view redirect
                    return None # Authentication fails if account is locked

                if user:
                    # Authentication successful, reset failed attempts
                    custom_user.failed_login_attempts = 0
                    custom_user.lockout_until = None
                    custom_user.save()
                    return user
                else:
                    # Authentication failed, increment attempts
                    log_action(custom_user, 'LOGIN_FAILED', request=request) # Log failed login
                    custom_user.failed_login_attempts += 1
                    if custom_user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                        custom_user.lockout_until = timezone.now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                        custom_user.failed_login_attempts = 0 # Reset attempts after lockout
                        log_action(custom_user, 'ACCOUNT_LOCKED', request=request) # Log account locked
                        
                        # In-app notification for locked user
                        create_notification(
                            user=custom_user,
                            message=f"Your account has been locked due to too many failed login attempts. It will be unlocked in {LOCKOUT_DURATION_MINUTES} minutes.",
                            link=reverse('user_management:locked_out_view') # Link to locked out page
                        )
                        # Notify admins
                        notify_admins_of_critical_event(
                            message=f"User '{custom_user.username}' account has been locked due to multiple failed login attempts.",
                            obj=custom_user
                        )
                        if request: # Only set error message if request is available
                           request.session['lockout_message'] = f"Too many failed login attempts. Account locked for {LOCKOUT_DURATION_MINUTES} minutes."
                           request.session['locked_username'] = username
                    custom_user.save()
        return user # If user is None (auth failed or user not found) or custom_user not found
