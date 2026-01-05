from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import ListView, View
from django.contrib import messages
from .models import Notification

class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-timestamp')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Mark all displayed notifications as read when the page is viewed
        # This will only mark those actually fetched by the queryset
        for notification in context['notifications']:
            if not notification.is_read:
                notification.is_read = True
                notification.save()
        return context

class NotificationMarkAsReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notification = Notification.objects.filter(user=request.user, pk=pk).first()
        if notification:
            notification.mark_as_read()
            messages.success(request, "Notification marked as read.")
        return redirect('notifications:notification_list')

class NotificationMarkAllAsReadView(LoginRequiredMixin, View):
    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        messages.success(request, "All notifications marked as read.")
        return redirect('notifications:notification_list')
