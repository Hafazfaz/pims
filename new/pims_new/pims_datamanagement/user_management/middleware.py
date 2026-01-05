from datetime import timedelta
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.urls import NoReverseMatch, resolve, reverse
from django.utils import timezone # Import timezone

PASSWORD_EXPIRY_DAYS = 90 # Define password expiry period

class PasswordChangeMiddleware:
    """
    Middleware to enforce password change for users with the 'must_change_password' flag
    and for expired passwords.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            # Check for password expiry
            if request.user.last_password_change:
                expiry_date = request.user.last_password_change + timedelta(days=PASSWORD_EXPIRY_DAYS)
                if timezone.now() > expiry_date:
                    request.user.must_change_password = True # Force password change if expired
                    request.user.save() # Save the change to the user object

            # Enforce password change if must_change_password is True
            if request.user.must_change_password:
                try:
                    current_url_name = resolve(request.path_info).url_name
                except NoReverseMatch:
                    current_url_name = ""

                allowed_url_names = [
                    "password_change_force",
                    "logout",
                ]
                # Allow access to admin change password forms if they are superuser
                if request.user.is_superuser and current_url_name == "password_change": # Check for admin change password URL
                    pass
                elif current_url_name not in allowed_url_names:
                    return redirect(reverse("user_management:password_change_force"))

        response = self.get_response(request)
        return response