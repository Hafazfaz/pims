from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy

# Reusable Q filter to exclude registry staff
EXCLUDE_REGISTRY_Q = Q(designation__name__icontains="registry") | Q(user__groups__name__iexact="Registry")


class HTMXLoginRequiredMixin(LoginRequiredMixin):
    """
    Forces a full page redirect to the login page for HTMX requests
    when the user is not authenticated.
    """

    def handle_no_permission(self):
        if self.request.headers.get("HX-Request"):
            from django.urls import reverse
            path = self.request.get_full_path()
            resolved_login_url = reverse("user_management:login")
            response = HttpResponse()
            response["HX-Redirect"] = f"{resolved_login_url}?next={path}"
            return response
        return super().handle_no_permission()


class RegistryRequiredMixin(HTMXLoginRequiredMixin, UserPassesTestMixin):
    """Restricts access to registry staff and superusers only."""

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
        return hasattr(user, "staff") and user.staff.is_registry

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "Only registry staff can access this page.")
        return redirect("document_management:my_files")
