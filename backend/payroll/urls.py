from django.urls import path

from . import views

urlpatterns = [
    path('', views.PayrollDashboardView.as_view(), name='payroll_dashboard'),

    path('salaries/', views.SalaryProfileListView.as_view(), name='payroll_salary_list'),
    path('salaries/add/', views.SalaryProfileCreateView.as_view(), name='payroll_salary_add'),
    path('salaries/<int:pk>/', views.SalaryProfileDetailView.as_view(), name='payroll_salary_detail'),
    path('salaries/<int:pk>/edit/', views.SalaryProfileUpdateView.as_view(), name='payroll_salary_edit'),

    path('periods/', views.PayrollPeriodListView.as_view(), name='payroll_period_list'),
    path('periods/add/', views.PayrollPeriodCreateView.as_view(), name='payroll_period_add'),
    path('periods/<int:pk>/', views.PayrollPeriodDetailView.as_view(), name='payroll_period_detail'),
    path('periods/<int:pk>/process/', views.PayrollProcessView.as_view(), name='payroll_period_process'),
    path('periods/<int:pk>/action/', views.PeriodApprovalActionView.as_view(), name='payroll_period_action'),

    path('runs/', views.PayrollListView.as_view(), name='payroll_list'),
    path('runs/<int:pk>/', views.PayrollDetailView.as_view(), name='payroll_detail'),
    path('runs/<int:pk>/action/', views.PayrollApprovalActionView.as_view(), name='payroll_action'),

    path('payslips/<int:pk>/', views.PayslipDetailView.as_view(), name='payroll_payslip'),

    path('bonuses/', views.BonusListView.as_view(), name='payroll_bonus_list'),
    path('bonuses/add/', views.BonusCreateView.as_view(), name='payroll_bonus_add'),

    path('deductions/', views.DeductionListView.as_view(), name='payroll_deduction_list'),
    path('deductions/add/', views.DeductionCreateView.as_view(), name='payroll_deduction_add'),

    path('allowances/', views.AllowanceListView.as_view(), name='payroll_allowance_list'),
    path('allowances/add/', views.AllowanceCreateView.as_view(), name='payroll_allowance_add'),

    path('reports/', views.PayrollReportsView.as_view(), name='payroll_reports'),
    path('audit/', views.PayrollAuditListView.as_view(), name='payroll_audit'),
    path('preview/', views.PayrollPreviewJsonView.as_view(), name='payroll_preview_json'),
]
