from django.urls import path
from . import views

app_name = 'organization'

urlpatterns = [
    # Department
    path('departments/', views.DepartmentListView.as_view(), name='department_list'),
    path('departments/create/', views.DepartmentCreateView.as_view(), name='department_create'),
    path('departments/<int:pk>/', views.DepartmentDetailView.as_view(), name='department_detail'),
    path('departments/<int:pk>/edit/', views.DepartmentUpdateView.as_view(), name='department_edit'),
    path('departments/<int:pk>/delete/', views.DepartmentDeleteView.as_view(), name='department_delete'),

    # Unit
    path('units/', views.UnitListView.as_view(), name='unit_list'),
    path('units/create/', views.UnitCreateView.as_view(), name='unit_create'),
    path('units/<int:pk>/edit/', views.UnitUpdateView.as_view(), name='unit_edit'),
    path('units/<int:pk>/delete/', views.UnitDeleteView.as_view(), name='unit_delete'),
    path('units/by-department/', views.units_by_department, name='units_by_department'),

    # Designation
    path('designations/', views.DesignationListView.as_view(), name='designation_list'),
    path('designations/create/', views.DesignationCreateView.as_view(), name='designation_create'),
    path('designations/<int:pk>/edit/', views.DesignationUpdateView.as_view(), name='designation_edit'),
    path('designations/<int:pk>/delete/', views.DesignationDeleteView.as_view(), name='designation_delete'),

    # Division
    path('divisions/', views.DivisionListView.as_view(), name='division_list'),
    path('divisions/create/', views.DivisionCreateView.as_view(), name='division_create'),
    path('divisions/<int:pk>/edit/', views.DivisionUpdateView.as_view(), name='division_edit'),
    path('divisions/<int:pk>/delete/', views.DivisionDeleteView.as_view(), name='division_delete'),

    # Section
    path('sections/', views.SectionListView.as_view(), name='section_list'),
    path('sections/create/', views.SectionCreateView.as_view(), name='section_create'),
    path('sections/<int:pk>/edit/', views.SectionUpdateView.as_view(), name='section_edit'),
    path('sections/<int:pk>/delete/', views.SectionDeleteView.as_view(), name='section_delete'),
]
