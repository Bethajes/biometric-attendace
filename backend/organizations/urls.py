from django.urls import path
from . import views

app_name = 'organizations'

urlpatterns = [
    path('', views.CompanyListView.as_view(), name='company_list'),
    path('companies/<int:pk>/', views.CompanyDetailView.as_view(), name='company_detail'),
    path('branches/', views.BranchListView.as_view(), name='branch_list'),
    path('departments/', views.DepartmentListView.as_view(), name='department_list'),
    path('teams/', views.TeamListView.as_view(), name='team_list'),
]
