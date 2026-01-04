import base64
import io
import random
from datetime import datetime, timedelta

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View

from .models import CustomUser  # Import CustomUser


class CustomLoginView(LoginView):
    template_name = "registration/login.html"

    def form_invalid(self, form):
        # Check if a lockout message was set in the session by the authentication backend
        lockout_message = self.request.session.pop('lockout_message', None)
        locked_username = self.request.session.pop('locked_username', None)

        if lockout_message:
            messages.error(self.request, lockout_message)
            return redirect("user_management:locked_out_view")

        return super().form_invalid(form)

    def form_valid(self, form):
        user = form.get_user()
        login(self.request, user)
        # First, handle mandatory password change
        if user.must_change_password:
            messages.info(self.request, "You must change your password before proceeding.")
            return redirect("user_management:password_change_force")

        # If password is fine, proceed to home
        return redirect(reverse_lazy("home"))


def custom_lockout_view(request):
    # Retrieve lockout information from the session
    # The messages framework will handle displaying the error message from the session
    return render(request, "user_management/locked_out.html")


@method_decorator(login_required, name="dispatch")
class ForcePasswordChangeView(View):
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("home")
    form_class = PasswordChangeForm

    def get(self, request, *args, **kwargs):
        form = self.form_class(request.user)
        return render(request, self.template_name, {"form": form})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(
                request, user
            )  # Important to keep the user logged in
            user.must_change_password = False
            user.save()
            messages.success(request, "Your password has been changed successfully.")
            return redirect(self.success_url)
        return render(request, self.template_name, {"form": form})