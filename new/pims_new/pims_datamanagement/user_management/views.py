import base64
import io
import random
import logging # Import logging
from datetime import datetime, timedelta
from django.utils import timezone # Add this import

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.hashers import make_password # Import make_password
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.core.exceptions import ObjectDoesNotExist # Import ObjectDoesNotExist

from .models import CustomUser, PasswordHistory # Import PasswordHistory

logger = logging.getLogger(__name__) # Initialize logger

PASSWORD_HISTORY_LIMIT = 5

# Configuration for SMS OTP (for now, just logging)
ENABLE_SMS_OTP = True # Set to True to activate SMS OTP (logged to console)

class CustomLoginView(LoginView):
    template_name = "registration/login.html"

    def _send_sms_otp(self, user):
        """Generates, stores, and logs an OTP for the user."""
        otp_code = str(random.randint(100000, 999999))
        otp_expiry = timezone.now() + timedelta(minutes=10)

        self.request.session["otp_sms_code"] = otp_code
        self.request.session["otp_sms_expiry"] = otp_expiry.isoformat()
        self.request.session["otp_sms_user_id"] = user.id

        # Log the OTP for now instead of sending via Twilio
        # Assuming Staff model has a phone_number field and is linked to CustomUser
        try:
            staff = user.staff
            if staff.phone_number:
                logger.info(f"SMS OTP for {user.username} ({staff.phone_number}): {otp_code}")
                messages.info(self.request, f"An OTP has been sent to your phone number ending with {staff.phone_number[-4:]}.")
            else:
                logger.warning(f"SMS OTP generated for {user.username}: {otp_code}, but no phone number found for staff.")
                messages.warning(self.request, "An OTP has been generated, but no phone number is registered. Please contact support.")
        except ObjectDoesNotExist: # Import ObjectDoesNotExist if this path is taken
            logger.warning(f"SMS OTP generated for {user.username}: {otp_code}, but user is not associated with a staff profile.")
            messages.warning(self.request, "An OTP has been generated, but you are not associated with a staff profile. Please contact support.")


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
        # Log the user in temporarily to handle password changes or OTP
        login(self.request, user)

        # First, handle mandatory password change
        if user.must_change_password:
            messages.info(self.request, "You must change your password before proceeding.")
            return redirect("user_management:password_change_force")

        # If password is fine and SMS OTP is enabled, proceed with SMS OTP
        if ENABLE_SMS_OTP:
            self._send_sms_otp(user)
            return redirect("user_management:otp_sms_verify")
        
        # If no password change and no SMS OTP, proceed to home
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
            user = form.save(commit=False) # Don't save yet, need to handle password history
            new_password = form.cleaned_data['new_password1'] # Get the new password

            # Save the new password hash to history
            PasswordHistory.objects.create(user=user, password=make_password(new_password))

            # Clean up old password history entries (keep only the last N)
            history_entries = PasswordHistory.objects.filter(user=user).order_by('-timestamp')
            if history_entries.count() > PASSWORD_HISTORY_LIMIT:
                history_entries.last().delete() # Delete the oldest entry

            user.must_change_password = False
            user.last_password_change = timezone.now()
            user.save() # Now save the user object

            update_session_auth_hash(
                request, user
            )  # Important to keep the user logged in
            messages.success(request, "Your password has been changed successfully.")
            return redirect(self.success_url)
        return render(request, self.template_name, {"form": form})


class SMSOTPVerifyView(View):
    template_name = "registration/otp_sms_verify.html"

    def get(self, request, *args, **kwargs):
        # Ensure there's an OTP in session to verify
        if not request.session.get("otp_sms_user_id"):
            messages.error(request, "Invalid request. Please try logging in again.")
            return redirect("user_management:login")
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        user_id = request.session.get("otp_sms_user_id")
        otp_code_session = request.session.get("otp_sms_code")
        otp_expiry_session = request.session.get("otp_sms_expiry")
        user_token = request.POST.get("otp_token")

        if not all([user_id, otp_code_session, otp_expiry_session, user_token]):
            messages.error(request, "Invalid request. Please try logging in again.")
            return redirect("user_management:login")

        otp_expiry = datetime.fromisoformat(otp_expiry_session)

        if otp_expiry < timezone.now():
            messages.error(request, "OTP has expired. Please try again.")
            # Clean up session only if expired
            self.clean_otp_session(request)
            return redirect("user_management:login")

        if user_token != otp_code_session:
            messages.error(request, "Invalid OTP token.")
            return render(request, self.template_name)

        # OTP is valid, proceed
        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            messages.error(request, "User not found. Please try logging in again.")
            self.clean_otp_session(request)
            return redirect("user_management:login")

        messages.success(request, "Successfully logged in.")

        # Clean up session
        self.clean_otp_session(request)

        # Update last login IP (future session management task)
        # user.last_login_ip = self.request.META.get('REMOTE_ADDR') # Consider a more robust way to get client IP
        # user.save()

        return redirect(reverse_lazy("home"))

    def clean_otp_session(self, request):
        if "otp_sms_user_id" in request.session:
            del request.session["otp_sms_user_id"]
        if "otp_sms_code" in request.session:
            del request.session["otp_sms_code"]
        if "otp_sms_expiry" in request.session:
            del request.session["otp_sms_expiry"]