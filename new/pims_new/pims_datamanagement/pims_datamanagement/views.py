from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
import datetime # Import for month calculation
from django.utils import timezone
from document_management.models import File, Document
from organization.models import Staff # Import the Staff model

class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            from django.shortcuts import redirect
            return redirect('user_management:admin_dashboard_health')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['user_name'] = user.get_full_name() or user.username

        document_queryset = Document.objects.all()

        if user.is_authenticated and not user.is_superuser:
            try:
                staff_user = user.staff
                if staff_user.is_hod and staff_user.department:
                    # HOD sees documents for files in their department
                    document_queryset = document_queryset.filter(file__department=staff_user.department)
                elif staff_user.is_registry and staff_user.unit:
                    # Registry sees documents for files in their unit
                    document_queryset = document_queryset.filter(file__owner__unit=staff_user.unit)
                else:
                    # Regular staff see only documents for files they own or are currently holding
                    document_queryset = document_queryset.filter(file__owner=staff_user) | \
                                        document_queryset.filter(file__current_location=staff_user)
            except Staff.DoesNotExist:
                # If user is authenticated but not a staff member, show no documents
                document_queryset = Document.objects.none()
        elif not user.is_authenticated:
            # Unauthenticated users see no documents
            document_queryset = Document.objects.none()
        
        # Calculate counts from the filtered queryset
        context['total_documents'] = document_queryset.count()

        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        context['documents_this_month'] = document_queryset.filter(uploaded_at__gte=start_of_month).count()

        # Existing file counts (will apply to user's context, or global for superuser)
        file_queryset = File.objects.all()
        if user.is_authenticated and not user.is_superuser:
            try:
                staff_user = user.staff
                if staff_user.is_hod and staff_user.department:
                    file_queryset = file_queryset.filter(department=staff_user.department)
                elif staff_user.is_registry and staff_user.unit:
                    file_queryset = file_queryset.filter(owner__unit=staff_user.unit)
                else:
                    file_queryset = file_queryset.filter(owner=staff_user) | \
                                    file_queryset.filter(current_location=staff_user)
            except Staff.DoesNotExist:
                file_queryset = File.objects.none()
        elif not user.is_authenticated:
            file_queryset = File.objects.none()

        context['total_files'] = file_queryset.count()
        context['pending_files'] = file_queryset.filter(status='pending_activation').count()

        return context
