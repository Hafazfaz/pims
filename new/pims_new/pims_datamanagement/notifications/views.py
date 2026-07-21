from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import ListView, View

from .models import Notification


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = "notifications/notification_list.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user).order_by("-timestamp")
        filter_param = self.request.GET.get("filter")
        if filter_param == "unread":
            qs = qs.filter(is_read=False)
        elif filter_param == "read":
            qs = qs.filter(is_read=True)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_notifications = Notification.objects.filter(user=self.request.user)
        context["unread_count"] = user_notifications.filter(is_read=False).count()
        context["read_count"] = user_notifications.filter(is_read=True).count()
        context["total_count"] = user_notifications.count()
        context["current_filter"] = self.request.GET.get("filter", "all")
        return context


class NotificationMarkAsReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notification = Notification.objects.filter(user=request.user, pk=pk).first()
        if notification:
            notification.mark_as_read()
        return redirect("notifications:notification_list")

    def get(self, request, pk):
        notification = Notification.objects.filter(user=request.user, pk=pk).first()
        if notification:
            notification.mark_as_read()
            target = notification.get_link()
            if target:
                return redirect(target)
        return redirect("notifications:notification_list")


class NotificationMarkAllAsReadView(LoginRequiredMixin, View):
    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        messages.success(request, "All notifications marked as read.")
        return redirect("notifications:notification_list")
