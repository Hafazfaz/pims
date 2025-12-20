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
# from django_otp import user_has_device, verify_token
# from django_otp.decorators import otp_required
# from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
# from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import CustomUser  # Import CustomUser


class CustomLoginView(LoginView):
    template_name = "registration/login.html"

    # def _send_email_otp(self, user):
    #     """Generates, stores, and sends an OTP to the user's email."""
    #     otp_code = str(random.randint(100000, 999999))
    #     otp_expiry = datetime.now() + timedelta(minutes=10)

    #     self.request.session["otp_code"] = otp_code
    #     self.request.session["otp_expiry"] = otp_expiry.isoformat()
    #     self.request.session["otp_user_id"] = user.id

    #     send_mail(
    #         "Your PIMS Login OTP",
    #         f"Your One-Time Password is: {otp_code}",
    #         "noreply@pims.local",
    #         [user.email],
    #         fail_silently=False,
    #     )

    def form_valid(self, form):
        user = form.get_user()
        login(self.request, user)
        # First, handle mandatory password change
        if user.must_change_password:
            # login(self.request, user)
            messages.info(self.request, "You must change your password before proceeding.")
            return redirect("user_management:password_change_force")

        return redirect(reverse_lazy("home"))

        # If password is fine, proceed with OTP
        # self._send_email_otp(user)
        # messages.info(self.request, "An OTP has been sent to your email.")
        # return redirect("user_management:otp_verify_email")


# class EmailOTPVerifyView(View):
#     template_name = "registration/otp_verify.html"

#     def get(self, request, *args, **kwargs):
#         return render(request, self.template_name)

#     def post(self, request, *args, **kwargs):
#         user_id = request.session.get("otp_user_id")
#         otp_code_session = request.session.get("otp_code")
#         otp_expiry_session = request.session.get("otp_expiry")
#         user_token = request.POST.get("otp_token")

#         if not all([user_id, otp_code_session, otp_expiry_session, user_token]):
#             messages.error(request, "Invalid request. Please try logging in again.")
#             return redirect("user_management:login")

#         otp_expiry = datetime.fromisoformat(otp_expiry_session)

#         if otp_expiry < datetime.now():
#             messages.error(request, "OTP has expired. Please try again.")
#             return redirect("user_management:login")

#         if user_token != otp_code_session:
#             messages.error(request, "Invalid OTP token.")
#             return render(request, self.template_name)

#         # OTP is valid, log the user in
#         try:
#             user = CustomUser.objects.get(id=user_id)
#         except CustomUser.DoesNotExist:
#             messages.error(request, "User not found. Please try logging in again.")
#             return redirect("user_management:login")

#         login(request, user)
#         messages.success(request, "Successfully logged in.")

#         # Clean up session
#         del request.session["otp_user_id"]
#         del request.session["otp_code"]
#         del request.session["otp_expiry"]

#         return redirect(reverse_lazy("home"))


def custom_lockout_view(request, credentials, *args, **kwargs):
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

