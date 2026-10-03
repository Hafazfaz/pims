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


def render_inbox_panel(request, status=200):
    """Render just the inbox panel fragment (tabs, filters, list, messages).

    Used by the action endpoints so an htmx request gets a fresh panel —
    counts and rows update in place with no page reload.
    """
    from django.shortcuts import render

    from .file_views import InboxView

    inbox = InboxView()
    inbox.request = request
    inbox.args, inbox.kwargs = (), {}
    context = inbox.get_context_data(object_list=inbox.get_queryset())
    return render(
        request,
        "document_management/partials/_inbox_panel.html",
        context,
        status=status,
    )


def inbox_action_response(request, redirect_url):
    """Act on an inbox row: htmx swaps in a fresh panel, others redirect.

    An htmx call issued from the inbox gets the re-rendered panel; from any
    other page it gets an ``HX-Redirect`` so the browser lands there. Plain
    form posts keep the classic redirect.
    """
    if request.headers.get("HX-Request"):
        if "/inbox/" in request.headers.get("HX-Current-URL", ""):
            return render_inbox_panel(request)
        response = HttpResponse()
        response["HX-Redirect"] = request.build_absolute_uri(_resolve_url(redirect_url))
        return response
    return redirect(_resolve_url(redirect_url))


def _resolve_url(redirect_url):
    """Accept either a path or a URL name from callers."""
    url = str(redirect_url)
    if url.startswith(("/", "http://", "https://")):
        return url
    from django.urls import reverse

    return reverse(url)
