from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.NotificationListView.as_view(), name='notification_list'),
    path('<int:pk>/mark-as-read/', views.NotificationMarkAsReadView.as_view(), name='mark_as_read'),
    path('mark-all-as-read/', views.NotificationMarkAllAsReadView.as_view(), name='mark_all_as_read'),
]
