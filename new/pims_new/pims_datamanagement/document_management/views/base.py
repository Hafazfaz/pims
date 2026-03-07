from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy

class HTMXLoginRequiredMixin(LoginRequiredMixin):
    """
    Forces a full page redirect to the login page for HTMX requests
    when the user is not authenticated.
    """
    def handle_no_permission(self):
        if self.request.headers.get("HX-Request"):
            response = HttpResponse()
            # Redirect to login page and let it redirect back to current page
            response["HX-Redirect"] = str(reverse_lazy("user_management:login"))
            return response
        return super().handle_no_permission()
