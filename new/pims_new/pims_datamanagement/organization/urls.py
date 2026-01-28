from django.urls import path
from . import views

app_name = 'organization'

urlpatterns = [
    path('departments/', views.DepartmentListView.as_view(), name='department_list'),
    path('departments/<int:pk>/', views.DepartmentDetailView.as_view(), name='department_detail'),
    path('units/', views.UnitListView.as_view(), name='unit_list'),
]
