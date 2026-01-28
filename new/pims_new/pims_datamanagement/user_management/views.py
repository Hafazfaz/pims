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
from django.db.models import Q

from .models import CustomUser, PasswordHistory # Import PasswordHistory
from audit_log.utils import log_action # Import audit logging utility
from notifications.utils import create_notification, notify_admins_of_critical_event # Import notification utilities
from document_management.models import File, Document # Import for admin health dashboard
from audit_log.models import AuditLogEntry # Import for admin health dashboard
from .otp_utils import generate_otp, send_otp_email, set_otp_in_session, verify_otp_in_session, clear_otp_session # Import OTP utilities
from organization.models import Department, Unit, Designation # Added Designation for filtering

logger = logging.getLogger(__name__) # Initialize logger

PASSWORD_HISTORY_LIMIT = 5

# Configuration for Email OTP
ENABLE_EMAIL_OTP = True

class CustomLoginView(LoginView):
    template_name = "registration/signin.html"

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

        # If password is fine and Email OTP is enabled, proceed with Email OTP
        if ENABLE_EMAIL_OTP:
            otp = generate_otp()
            send_otp_email(user, otp)
            set_otp_in_session(self.request, user.id, otp)
            messages.info(self.request, f"A 6-digit OTP has been sent to your email address.")
            return redirect("user_management:otp_email_verify")
        
        # If no password change and no OTP, proceed to home
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


class EmailOTPVerifyView(View):
    template_name = "registration/otp_email_verify.html"

    def get(self, request, *args, **kwargs):
        # Ensure there's an OTP in session to verify
        if not request.session.get("pending_otp_user_id"):
            messages.error(request, "OTP session not found. Please log in again.")
            return redirect("user_management:login")
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        otp_input = request.POST.get("otp_token")
        if not otp_input:
            messages.error(request, "Please enter the OTP.")
            return render(request, self.template_name)

        user_id, error_message = verify_otp_in_session(request, otp_input)

        if error_message:
            messages.error(request, error_message)
            # If expired, verify_otp_in_session already cleared it, so redirect to login
            if "expired" in error_message.lower() or "not found" in error_message.lower():
                return redirect("user_management:login")
            return render(request, self.template_name)

        # Success
        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            messages.error(request, "User not found. Please log in again.")
            clear_otp_session(request)
            return redirect("user_management:login")

        messages.success(request, "Verify success. You are now logged in.")
        clear_otp_session(request)
        return redirect(reverse_lazy("home"))


from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin, UserPassesTestMixin

class UserListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CustomUser
    template_name = 'user_management/user_list.html'
    context_object_name = 'users'
    permission_required = 'auth.view_user'
    paginate_by = 20

    def get_queryset(self):
        queryset = CustomUser.objects.all().order_by('username')
        
        # Filtering
        dept_id = self.request.GET.get('department')
        unit_id = self.request.GET.get('unit')
        designation_id = self.request.GET.get('designation')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        search_query = self.request.GET.get('q')

        if dept_id:
            queryset = queryset.filter(staff__department_id=dept_id)
        if unit_id:
            queryset = queryset.filter(staff__unit_id=unit_id)
        if designation_id:
            queryset = queryset.filter(staff__designation_id=designation_id)
        if start_date:
            queryset = queryset.filter(date_joined__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date_joined__date__lte=end_date)
        if search_query:
            queryset = queryset.filter(
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context['locked_users'] = {user.pk for user in context['users'] if user.lockout_until and user.lockout_until > now}
        
        # Filter context
        context['all_departments'] = Department.objects.all().order_by('name')
        context['all_units'] = Unit.objects.all().order_by('name')
        context['all_designations'] = Designation.objects.all().order_by('level')
        context['selected_department'] = int(self.request.GET.get('department')) if self.request.GET.get('department', '').isdigit() else ''
        context['selected_unit'] = int(self.request.GET.get('unit')) if self.request.GET.get('unit', '').isdigit() else ''
        context['selected_designation'] = int(self.request.GET.get('designation')) if self.request.GET.get('designation', '').isdigit() else ''
        context['selected_start_date'] = self.request.GET.get('start_date', '')
        context['selected_end_date'] = self.request.GET.get('end_date', '')
        context['search_query'] = self.request.GET.get('q', '')

        # Preserve query parameters for pagination
        params = self.request.GET.copy()
        if 'page' in params:
            del params['page']
        context['query_params'] = '&' + params.urlencode() if params else ''
        
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
        
        # Capture username before deletion
        username_deleted = user_to_delete.username
        
        # Explicit cleanup for related objects to satisfy strict DB constraints (SQLite NO ACTION)
        # 1. Clear Many-to-Many relationships
        user_to_delete.groups.clear()
        user_to_delete.user_permissions.clear()
        
        # 2. Delete One-to-One and Related Models
        from .models import PasswordHistory
        PasswordHistory.objects.filter(user=user_to_delete).delete()
        
        from organization.models import Staff
        Staff.objects.filter(user=user_to_delete).delete()
        
        # 3. Handle models where User is SET_NULL (SQLite might still block if NO ACTION is enforced)
        from audit_log.models import AuditLogEntry
        AuditLogEntry.objects.filter(user=user_to_delete).update(user=None)
        
        from notifications.models import Notification
        Notification.objects.filter(user=user_to_delete).delete()
        
        # 4. Purge OTP devices (keep existing logic)
        from django_otp.plugins.otp_static.models import StaticDevice
        from django_otp.plugins.otp_totp.models import TOTPDevice
        StaticDevice.objects.filter(user=user_to_delete).delete()
        TOTPDevice.objects.filter(user=user_to_delete).delete()
        
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
        must_change_password_users = CustomUser.objects.filter(must_change_password=True).count()

        # Organization Statistics
        total_departments = Department.objects.count()
        total_units = Unit.objects.count()

        # File Statistics
        total_files = File.objects.count()
        inactive_files = File.objects.filter(status='inactive').count()
        pending_activation_files = File.objects.filter(status='pending_activation').count()
        active_files = File.objects.filter(status='active').count()
        in_transit_files = File.objects.filter(status='in_transit').count()
        closed_files = File.objects.filter(status='closed').count()
        archived_files = File.objects.filter(status='archived').count()

        # Document Statistics
        total_documents = Document.objects.count()

        # Recent Audit Log Entries
        recent_failed_logins = AuditLogEntry.objects.filter(action='LOGIN_FAILED').order_by('-timestamp')[:5]
        recent_locked_accounts = AuditLogEntry.objects.filter(action='ACCOUNT_LOCKED').order_by('-timestamp')[:5]
        recent_unlocked_accounts = AuditLogEntry.objects.filter(action='ACCOUNT_UNLOCKED').order_by('-timestamp')[:5]

        # Asset Breakdown for UI
        file_status_breakdown = [
            {'label': 'Inactive', 'count': inactive_files, 'color': 'slate'},
            {'label': 'Pending Activation', 'count': pending_activation_files, 'color': 'amber'},
            {'label': 'Active', 'count': active_files, 'color': 'green'},
            {'label': 'In Transit', 'count': in_transit_files, 'color': 'blue'},
            {'label': 'Closed', 'count': closed_files, 'color': 'orange'},
            {'label': 'Archived', 'count': archived_files, 'color': 'purple'},
        ]
        for item in file_status_breakdown:
            item['percentage'] = (item['count'] / total_files * 100) if total_files > 0 else 0

        context['stats'] = {
            'users': {
                'total': total_users,
                'active': active_users,
                'inactive': inactive_users,
                'locked': locked_users,
                'must_change_password': must_change_password_users,
            },
            'org': {
                'departments': total_departments,
                'units': total_units,
            },
            'files': {
                'total': total_files,
                'breakdown': file_status_breakdown,
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