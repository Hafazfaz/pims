import base64
import io
import random
import logging # Import logging
from django.conf import settings # Add this import
from datetime import datetime, timedelta
from django.utils import timezone # Add this import

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.sessions.models import Session # Added for concurrent session control
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.hashers import make_password # Import make_password
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView # Added this import
from django.core.exceptions import ObjectDoesNotExist # Import ObjectDoesNotExist

from .models import CustomUser, PasswordHistory # Import PasswordHistory
from audit_log.utils import log_action # Import audit logging utility
from notifications.utils import create_notification, notify_admins_of_critical_event # Import notification utilities
from document_management.models import File, Document # Import for admin health dashboard
from audit_log.models import AuditLogEntry # Import for admin health dashboard

logger = logging.getLogger(__name__) # Initialize logger

PASSWORD_HISTORY_LIMIT = 5

# Configuration for SMS OTP (for now, just logging)
ENABLE_SMS_OTP = True # Set to True to activate SMS OTP (logged to console)

class CustomLoginView(LoginView):
    template_name = "registration/login.html"

    def _send_sms_otp(self, user):
        """Generates, stores, and logs an OTP for the user."""
        if settings.DEBUG:
            otp_code = "123456" # Hardcoded OTP for testing in development
            logger.info(f"DEBUG: Using hardcoded OTP for {user.username}: {otp_code}")
        else:
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
        except ObjectDoesNotExist: # Import ObjectDoesNotExist if this path is taken
            logger.warning(f"SMS OTP generated for {user.username}: {otp_code}, but user is not associated with a staff profile.")


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

        # Update last login IP
        user.last_login_ip = self.request.META.get('REMOTE_ADDR') # Simple way to get client IP
        
        # Concurrent session prevention
        if user.last_session_key and user.last_session_key != self.request.session.session_key:
            try:
                Session.objects.get(session_key=user.last_session_key).delete()
            except Session.DoesNotExist:
                pass # Old session already expired or deleted

        user.last_session_key = self.request.session.session_key
        user.save(update_fields=['last_login_ip', 'last_session_key']) # Update both fields

        # Log successful login
        log_action(self.request.user, 'LOGIN', request=self.request)

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

            log_action(user, 'PASSWORD_CHANGED', request=request) # Log password change

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


from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin, UserPassesTestMixin

class UserListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CustomUser
    template_name = 'user_management/user_list.html'
    context_object_name = 'users'
    permission_required = 'auth.view_user'

    def get_queryset(self):
        return CustomUser.objects.all().order_by('username')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context['locked_users'] = {user.pk for user in context['users'] if user.lockout_until and user.lockout_until > now}
        return context

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('user_management:login')
        messages.error(self.request, 'You do not have permission to view this page.')
        return redirect('home')


class UserUnlockView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'auth.change_user'

    def post(self, request, pk):
        user_to_unlock = get_object_or_404(CustomUser, pk=pk)
        user_to_unlock.failed_login_attempts = 0
        user_to_unlock.lockout_until = None
        user_to_unlock.save()
        log_action(self.request.user, 'ACCOUNT_UNLOCKED', request=self.request, obj=user_to_unlock) # Log account unlocked
        
        # In-app notification for unlocked user
        create_notification(
            user=user_to_unlock,
            message=f"Your account has been unlocked by an administrator.",
            obj=user_to_unlock
        )
        # Notify admins
        notify_admins_of_critical_event(
            message=f"User '{user_to_unlock.username}' account has been unlocked by {self.request.user.username}.",
            obj=user_to_unlock
        )
        messages.success(request, f"User '{user_to_unlock.username}' has been unlocked.")
        return redirect('user_management:user_list')

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('user_management:login')
        messages.error(self.request, 'You do not have permission to unlock users.')
        return redirect('user_management:user_list')


class UserSuspendView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'auth.change_user' # Can suspend users if can change user

    def post(self, request, pk):
        user_to_suspend = get_object_or_404(CustomUser, pk=pk)
        if user_to_suspend.is_superuser:
            messages.error(request, "Cannot suspend a superuser.")
            return redirect('user_management:user_list')
        
        user_to_suspend.is_active = False
        user_to_suspend.save()
        log_action(self.request.user, 'USER_SUSPENDED', request=self.request, obj=user_to_suspend, details={'username': user_to_suspend.username})
        
        # In-app notification for suspended user
        create_notification(
            user=user_to_suspend,
            message=f"Your account has been suspended by an administrator. Please contact support.",
            obj=user_to_suspend
        )
        # Notify admins
        notify_admins_of_critical_event(
            message=f"User '{user_to_suspend.username}' account has been suspended by {self.request.user.username}.",
            obj=user_to_suspend
        )
        messages.success(request, f"User '{user_to_suspend.username}' has been suspended.")
        return redirect('user_management:user_list')

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('user_management:login')
        messages.error(self.request, 'You do not have permission to suspend users.')
        return redirect('user_management:user_list')

class UserDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'auth.delete_user' # Can delete users

    def post(self, request, pk):
        user_to_delete = get_object_or_404(CustomUser, pk=pk)
        if user_to_delete.is_superuser:
            messages.error(request, "Cannot delete a superuser.")
            return redirect('user_management:user_list')
        
        username_deleted = user_to_delete.username # Capture username before deletion
        user_to_delete.delete()
        log_action(self.request.user, 'USER_DELETED', request=self.request, details={'username': username_deleted})
        
        # Notify admins about user deletion
        notify_admins_of_critical_event(
            message=f"User '{username_deleted}' account has been deleted by {self.request.user.username}.",
            obj=None # User object no longer exists
        )
        messages.success(request, f"User '{username_deleted}' has been deleted.")
        return redirect('user_management:user_list')

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('user_management:login')
        messages.error(self.request, 'You do not have permission to delete users.')
        return redirect('user_management:user_list')


class AdminDashboardHealthView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    template_name = 'user_management/admin_dashboard_health.html'
    context_object_name = 'stats' # Will pass a dictionary of stats

    def test_func(self):
        # Only superusers can access this dashboard
        return self.request.user.is_superuser

    def get_queryset(self):
        # No queryset needed for ListView as we are passing context manually
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # User Statistics
        total_users = CustomUser.objects.count()
        active_users = CustomUser.objects.filter(is_active=True).count()
        inactive_users = CustomUser.objects.filter(is_active=False).count()
        locked_users = CustomUser.objects.filter(lockout_until__gt=timezone.now()).count()

        # File Statistics
        total_files = File.objects.count()
        active_files = File.objects.filter(status='active').count()
        closed_files = File.objects.filter(status='closed').count()
        archived_files = File.objects.filter(status='archived').count()

        # Document Statistics
        total_documents = Document.objects.count()

        # Recent Audit Log Entries
        recent_failed_logins = AuditLogEntry.objects.filter(action='LOGIN_FAILED').order_by('-timestamp')[:5]
        recent_locked_accounts = AuditLogEntry.objects.filter(action='ACCOUNT_LOCKED').order_by('-timestamp')[:5]
        recent_unlocked_accounts = AuditLogEntry.objects.filter(action='ACCOUNT_UNLOCKED').order_by('-timestamp')[:5]

        context['stats'] = {
            'users': {
                'total': total_users,
                'active': active_users,
                'inactive': inactive_users,
                'locked': locked_users,
            },
            'files': {
                'total': total_files,
                'active': active_files,
                'closed': closed_files,
                'archived': archived_files,
            },
            'documents': {
                'total': total_documents,
            },
            'recent_failed_logins': recent_failed_logins,
            'recent_locked_accounts': recent_locked_accounts,
            'recent_unlocked_accounts': recent_unlocked_accounts,
        }
        return context

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('user_management:login')
        messages.error(self.request, 'You do not have permission to access the admin health dashboard.')
        return redirect('home')