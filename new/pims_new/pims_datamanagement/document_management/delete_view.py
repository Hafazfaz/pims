from audit_log.utils import log_action
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import View

from .models import Document, FileAccessRequest


class DocumentDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Delete a document from a file.
    Only Registry or users with active Read-Write access can delete documents.
    """
    
    def test_func(self):
        document = get_object_or_404(Document, pk=self.kwargs['pk'])
        file_obj = document.file
        user = self.request.user
        
        # Registry can always delete
        try:
            if user.staff.is_registry:
                return True
        except AttributeError:
            pass
        
        # Check for active read-write access
        active_access = FileAccessRequest.objects.filter(
            file=file_obj,
            requested_by=user,
            status='approved',
            access_type='read_write'
        ).first()
        
        if active_access and active_access.is_active:
            return True
        
        return False
    
    def post(self, request, pk):
        document = get_object_or_404(Document, pk=pk)
        file_obj = document.file
        
        # Log the deletion
        log_action(
            request.user,
            "DOCUMENT_DELETED",
            request=request,
            obj=document,
            details={"file": file_obj.file_number, "title": document.title or "Untitled"}
        )
        
        # Delete the document
        document.delete()
        
        messages.success(request, "Document deleted successfully.")
        return redirect('document_management:file_detail', pk=file_obj.pk)
