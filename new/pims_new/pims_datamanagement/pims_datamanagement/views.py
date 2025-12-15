from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from document_management.models import File # Import the File model

class HomeView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_name'] = self.request.user.get_full_name() or self.request.user.username

        # Fetch data for dashboard
        context['total_files'] = File.objects.all().count()
        context['pending_files'] = File.objects.filter(status='pending_activation').count() # Using pending_activation as a proxy for pending approvals
        
        return context
