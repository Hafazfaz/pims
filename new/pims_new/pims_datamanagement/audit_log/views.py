from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView
from django.db.models import Q
from .models import AuditLogEntry
from user_management.models import CustomUser

class AuditLogListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = AuditLogEntry
    template_name = 'audit_log/audit_log_list.html'
    context_object_name = 'log_entries'
    paginate_by = 20

    def test_func(self):
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return True
        return user.groups.filter(name__iexact="Executives").exists()

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filtering
        user_id = self.request.GET.get('user')
        action = self.request.GET.get('action')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        search_query = self.request.GET.get('q')

        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if action:
            queryset = queryset.filter(action=action)
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        if search_query:
            queryset = queryset.filter(
                Q(details__icontains=search_query) |
                Q(action__icontains=search_query) |
                Q(user__username__icontains=search_query) |
                Q(ip_address__icontains=search_query) |
                Q(user_agent__icontains=search_query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['all_users'] = CustomUser.objects.all().order_by('username')
        context['all_actions'] = sorted(list(set(AuditLogEntry.objects.values_list('action', flat=True))))
        
        user_id = self.request.GET.get('user', '')
        context['selected_user'] = int(user_id) if user_id.isdigit() else ''
        
        context['selected_action'] = self.request.GET.get('action', '')
        context['selected_start_date'] = self.request.GET.get('start_date', '')
        context['selected_end_date'] = self.request.GET.get('end_date', '')
        context['search_query'] = self.request.GET.get('q', '')
        
        # Preserve query parameters for pagination
        params = self.request.GET.copy()
        if 'page' in params:
            del params['page']
        context['query_params'] = '&' + params.urlencode() if params else ''
        
        return context
