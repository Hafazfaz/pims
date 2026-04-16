from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from document_management.models import File, Document, ApprovalChain, ApprovalStep
from organization.models import Staff

class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.is_superuser:
                return redirect('user_management:admin_dashboard_health')
            try:
                staff = request.user.staff
                if staff.is_registry:
                    return redirect('document_management:registry')
                elif staff.is_executive or staff.is_hod or staff.is_unit_manager:
                    return redirect('document_management:executive_dashboard')
            except Staff.DoesNotExist:
                pass
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        try:
            staff = user.staff
        except Staff.DoesNotExist:
            staff = None

        context['user_name'] = user.get_full_name() or user.username
        context['staff'] = staff

        # Files owned or in custody
        owned_files = File.objects.filter(owner=staff) if staff else File.objects.none()
        custody_files = File.objects.filter(current_location=staff).exclude(owner=staff) if staff else File.objects.none()

        context['total_files'] = owned_files.count()
        context['active_files'] = owned_files.filter(status='active').count()
        context['pending_files'] = owned_files.filter(status='pending_activation').count()
        context['files_in_custody'] = custody_files.count()

        # Documents this month
        context['documents_this_month'] = Document.objects.filter(
            file__owner=staff, uploaded_at__gte=start_of_month
        ).count() if staff else 0

        # Pending approval steps for this user
        context['pending_approvals'] = ApprovalStep.objects.filter(
            approver=staff, status='pending'
        ).select_related('chain__file').order_by('chain__file__file_number') if staff else []

        # Files currently in custody (incoming dispatches)
        context['custody_list'] = custody_files.select_related('owner__user', 'department').order_by('-created_at')[:5]

        # Recent activity on owned files
        context['recent_documents'] = Document.objects.filter(
            file__owner=staff
        ).select_related('file', 'uploaded_by').order_by('-uploaded_at')[:5] if staff else []

        # Personal file
        context['personal_file'] = owned_files.filter(file_type='personal').first()

        return context
