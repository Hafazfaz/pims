from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.urls import NoReverseMatch, resolve, reverse


class PasswordChangeMiddleware:
    """
    Middleware to enforce password change for users with the 'must_change_password' flag.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.user.must_change_password
            and not request.user.is_superuser
        ):
            try:
                current_url_name = resolve(request.path_info).url_name
            except NoReverseMatch:
                current_url_name = ""

            allowed_url_names = [
                "password_change_force",
                "logout",
            ]
            if current_url_name not in allowed_url_names:
                return redirect(reverse("user_management:password_change_force"))

        response = self.get_response(request)
        return response
