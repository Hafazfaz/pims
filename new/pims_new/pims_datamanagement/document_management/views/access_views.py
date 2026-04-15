from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, View
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from audit_log.utils import log_action
from notifications.utils import create_notification
from core.constants import ACCESS_REQUEST_DURATION_HOURS
from ..models import FileAccessRequest
from .base import RegistryRequiredMixin

DENY_REASONS = [
    ('Insufficient justification', 'Insufficient justification'),
    ('Unauthorised access level requested', 'Unauthorised access level requested'),
    ('File is classified / restricted', 'File is classified / restricted'),
    ('Requester lacks clearance', 'Requester lacks clearance'),
    ('Other', 'Other'),
]

class FileAccessRequestListView(RegistryRequiredMixin, ListView):
    model = FileAccessRequest
    template_name = "document_management/access_request_list.html"
    context_object_name = "requests"

    def get_queryset(self):
        return FileAccessRequest.objects.filter(status='pending').order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['deny_reasons'] = DENY_REASONS
        return context

class FileAccessRequestApproveView(RegistryRequiredMixin, View):

    def post(self, request, pk):
        access_req = get_object_or_404(FileAccessRequest, pk=pk)
        access_req.status = 'approved'
        access_req.approved_at = timezone.now()
        access_req.expires_at = timezone.now() + timedelta(hours=ACCESS_REQUEST_DURATION_HOURS)
        access_req.save()

        # Transfer custody to the requesting user
        file_obj = access_req.file
        try:
            file_obj.current_location = access_req.requested_by.staff
            file_obj.save()
        except Exception:
            pass

        log_action(request.user, "ACCESS_REQUEST_APPROVED", request=request, obj=access_req.file, details={'requested_by': access_req.requested_by.username})
        
        create_notification(
            user=access_req.requested_by,
            message=f"Your access request for file '{access_req.file.title}' has been approved. Access expires in {ACCESS_REQUEST_DURATION_HOURS} hours.",
            obj=access_req.file,
            link=access_req.file.get_absolute_url()
        )
        
        messages.success(request, f"Access request for {access_req.requested_by.username} approved.")
        return redirect('document_management:access_request_list')

class FileAccessRequestRejectView(RegistryRequiredMixin, View):

    def post(self, request, pk):
        access_req = get_object_or_404(FileAccessRequest, pk=pk)
        access_req.status = 'rejected'
        access_req.save()

        denial_reason = request.POST.get('denial_reason', '')
        if denial_reason == 'Other':
            denial_reason = request.POST.get('denial_reason_other', 'Other').strip() or 'Other'

        log_action(request.user, "ACCESS_REQUEST_REJECTED", request=request, obj=access_req.file, details={
            'requested_by': access_req.requested_by.username,
            'denial_reason': denial_reason,
        })
        
        create_notification(
            user=access_req.requested_by,
            message=f"Your access request for file '{access_req.file.title}' has been rejected.",
            obj=access_req.file
        )
        
        messages.success(request, f"Access request for {access_req.requested_by.username} rejected.")
        return redirect('document_management:access_request_list')
