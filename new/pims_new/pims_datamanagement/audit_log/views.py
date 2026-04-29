from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, View
from django.shortcuts import render
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
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


class MyActivityReportView(LoginRequiredMixin, View):
    """Personal activity report — aggregates the user's own audit log into meaningful sections."""

    # Action groups
    APPROVAL_ACTIONS = {'DOCUMENT_APPROVED', 'CHAIN_STEP_APPROVED'}
    REJECTION_ACTIONS = {'DOCUMENT_REJECTED', 'CHAIN_STEP_REJECTED'}
    ACCESS_GRANTED_ACTIONS = {'ACCESS_REQUEST_APPROVED'}
    ACCESS_DENIED_ACTIONS = {'ACCESS_REQUEST_REJECTED'}
    FILE_MOVEMENT_ACTIONS = {'FILE_SENT', 'DOCUMENT_FORWARDED', 'MOVEMENT_CLOSED'}
    FILE_ACTIONS = {'FILE_CREATED', 'FILE_UPDATED', 'FILE_CLOSED', 'FILE_ARCHIVED', 'FILE_ACTIVATED'}

    def get(self, request):
        user = request.user
        days = int(request.GET.get('days', 30))
        since = timezone.now() - timedelta(days=days)

        qs = AuditLogEntry.objects.filter(user=user, timestamp__gte=since).order_by('-timestamp')

        def group(actions):
            return qs.filter(action__in=actions)

        # Summary counts
        summary = {
            'approvals': group(self.APPROVAL_ACTIONS).count(),
            'rejections': group(self.REJECTION_ACTIONS).count(),
            'access_granted': group(self.ACCESS_GRANTED_ACTIONS).count(),
            'access_denied': group(self.ACCESS_DENIED_ACTIONS).count(),
            'files_moved': group(self.FILE_MOVEMENT_ACTIONS).count(),
            'file_actions': group(self.FILE_ACTIONS).count(),
            'total': qs.count(),
        }

        # Action breakdown for chart
        breakdown = (
            qs.values('action')
            .annotate(count=Count('action'))
            .order_by('-count')[:10]
        )

        return render(request, 'audit_log/my_activity_report.html', {
            'summary': summary,
            'breakdown': breakdown,
            'approvals': group(self.APPROVAL_ACTIONS).select_related('user')[:20],
            'rejections': group(self.REJECTION_ACTIONS).select_related('user')[:20],
            'access_granted': group(self.ACCESS_GRANTED_ACTIONS).select_related('user')[:20],
            'access_denied': group(self.ACCESS_DENIED_ACTIONS).select_related('user')[:20],
            'file_movements': group(self.FILE_MOVEMENT_ACTIONS).select_related('user')[:20],
            'days': days,
        })


class MyActivityReportView(LoginRequiredMixin, View):
    """
    Personal activity report for the requesting user.
    Registry can also view any user's report via ?user_id=<pk>.
    """

    APPROVAL_ACTIONS = {'DOCUMENT_APPROVED', 'CHAIN_STEP_APPROVED'}
    REJECTION_ACTIONS = {'DOCUMENT_REJECTED', 'CHAIN_STEP_REJECTED'}
    ACCESS_GRANTED_ACTIONS = {'ACCESS_REQUEST_APPROVED'}
    ACCESS_DENIED_ACTIONS = {'ACCESS_REQUEST_REJECTED'}
    FILE_MOVEMENT_ACTIONS = {'FILE_SENT', 'DOCUMENT_FORWARDED', 'MOVEMENT_CLOSED'}
    FILE_ACTIONS = {'FILE_CREATED', 'FILE_UPDATED', 'FILE_CLOSED', 'FILE_ARCHIVED', 'FILE_ACTIVATED'}

    def get(self, request):
        staff = getattr(request.user, 'staff', None)
        is_registry = staff and staff.is_registry

        # Registry: default to all users; can filter by searched user
        target_user = None if is_registry else request.user
        viewed_user = None
        search_q = request.GET.get('q', '').strip()
        user_id = request.GET.get('user_id')

        if user_id:
            try:
                target_user = CustomUser.objects.get(pk=user_id)
                viewed_user = target_user
            except CustomUser.DoesNotExist:
                pass
        elif search_q and is_registry:
            from django.db.models import Q as DQ
            match = CustomUser.objects.filter(
                DQ(first_name__icontains=search_q) |
                DQ(last_name__icontains=search_q) |
                DQ(email__icontains=search_q) |
                DQ(username__icontains=search_q)
            ).first()
            if match:
                target_user = match
                viewed_user = match
        elif not is_registry:
            target_user = request.user

        days = int(request.GET.get('days', 30))
        since = timezone.now() - timedelta(days=days)

        qs = AuditLogEntry.objects.filter(timestamp__gte=since).order_by('-timestamp')
        if target_user:
            qs = qs.filter(user=target_user)

        def group(actions):
            return qs.filter(action__in=actions)

        summary = {
            'approvals': group(self.APPROVAL_ACTIONS).count(),
            'rejections': group(self.REJECTION_ACTIONS).count(),
            'access_granted': group(self.ACCESS_GRANTED_ACTIONS).count(),
            'access_denied': group(self.ACCESS_DENIED_ACTIONS).count(),
            'files_moved': group(self.FILE_MOVEMENT_ACTIONS).count(),
            'file_actions': group(self.FILE_ACTIONS).count(),
            'total': qs.count(),
        }

        breakdown = (
            qs.values('action')
            .annotate(count=Count('action'))
            .order_by('-count')[:10]
        )

        all_users = CustomUser.objects.all().order_by('username') if is_registry else None

        viewed_user_staff = None
        if viewed_user:
            try:
                viewed_user_staff = viewed_user.staff
            except Exception:
                pass

        return render(request, 'audit_log/my_activity_report.html', {
            'summary': summary,
            'breakdown': breakdown,
            'approvals': group(self.APPROVAL_ACTIONS)[:20],
            'rejections': group(self.REJECTION_ACTIONS)[:20],
            'access_granted': group(self.ACCESS_GRANTED_ACTIONS)[:20],
            'access_denied': group(self.ACCESS_DENIED_ACTIONS)[:20],
            'file_movements': group(self.FILE_MOVEMENT_ACTIONS)[:20],
            'days': days,
            'is_registry': is_registry,
            'all_users': all_users,
            'viewed_user': viewed_user,
            'viewed_user_staff': viewed_user_staff,
            'search_q': search_q,
        })
