from django.urls import path
from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),

    path('employees/', views.EmployeeListView.as_view(), name='employee_list'),
    path('employees/add/', views.EmployeeCreateView.as_view(), name='employee_add'),
    path('employees/<int:pk>/', views.EmployeeDetailView.as_view(), name='employee_detail'),
    path('employees/<int:pk>/edit/', views.EmployeeUpdateView.as_view(), name='employee_edit'),

    path('departments/', views.DepartmentListView.as_view(), name='department_list'),
    path('departments/add/', views.DepartmentCreateView.as_view(), name='department_add'),
    path('departments/<int:pk>/edit/', views.DepartmentUpdateView.as_view(), name='department_edit'),

    path('schedules/', views.ScheduleListView.as_view(), name='schedule_list'),
    path('schedules/add/', views.ScheduleCreateView.as_view(), name='schedule_add'),
    path('schedules/<int:pk>/edit/', views.ScheduleUpdateView.as_view(), name='schedule_edit'),

    path('templates/', views.ScheduleTemplateListView.as_view(), name='template_list'),
    path('templates/add/', views.ScheduleTemplateCreateView.as_view(), name='template_add'),
    path('templates/<int:pk>/edit/', views.ScheduleTemplateUpdateView.as_view(), name='template_edit'),

    path('shifts/', views.ShiftListView.as_view(), name='shift_list'),
    path('shifts/add/', views.ShiftCreateView.as_view(), name='shift_add'),
    path('shifts/<int:pk>/edit/', views.ShiftUpdateView.as_view(), name='shift_edit'),

    path('attendance/', views.AttendanceRecordListView.as_view(), name='attendance_records'),

    path('leave/', views.LeaveListView.as_view(), name='leave_list'),
    path('leave/add/', views.LeaveCreateView.as_view(), name='leave_add'),
    path('leave/<int:pk>/edit/', views.LeaveUpdateView.as_view(), name='leave_edit'),

    path('holidays/', views.HolidayListView.as_view(), name='holiday_list'),
    path('holidays/add/', views.HolidayCreateView.as_view(), name='holiday_add'),
    path('holidays/<int:pk>/edit/', views.HolidayUpdateView.as_view(), name='holiday_edit'),

    path('overtime/', views.OvertimeRequestListView.as_view(), name='overtime_list'),
    path('overtime/add/', views.OvertimeRequestCreateView.as_view(), name='overtime_add'),
    path('overtime/<int:pk>/edit/', views.OvertimeRequestUpdateView.as_view(), name='overtime_edit'),
    path('api/overtime/<int:pk>/approve/', views.overtime_approve_api, name='overtime_approve'),

    path('remote/', views.RemoteWorkLogListView.as_view(), name='remote_list'),
    path('remote/add/', views.RemoteWorkLogCreateView.as_view(), name='remote_add'),
    path('remote/<int:pk>/edit/', views.RemoteWorkLogUpdateView.as_view(), name='remote_edit'),

    path('sites/', views.SiteVisitListView.as_view(), name='site_list'),
    path('sites/add/', views.SiteVisitCreateView.as_view(), name='site_add'),
    path('sites/<int:pk>/edit/', views.SiteVisitUpdateView.as_view(), name='site_edit'),

    path('policies/', views.AttendancePolicyListView.as_view(), name='policy_list'),
    path('policies/add/', views.AttendancePolicyCreateView.as_view(), name='policy_add'),
    path('policies/<int:pk>/edit/', views.AttendancePolicyUpdateView.as_view(), name='policy_edit'),

    path('reports/', views.ReportsView.as_view(), name='reports'),
    path('notifications/', views.NotificationListView.as_view(), name='notification_list'),
    path('roles/', views.UserRolesView.as_view(), name='user_roles'),
    path('settings/', views.SystemSettingsView.as_view(), name='system_settings'),

    path('enroll/<int:enrollment_id>/scan/', views.enroll_scan_view, name='enroll_scan'),
    path('api/attendance/', views.attendance_api, name='attendance_api'),
    path('api/enrollment/next/', views.enrollment_next_api, name='enrollment_next_api'),
    path('api/enrollment/<int:request_id>/complete/', views.enrollment_complete_api, name='enrollment_complete_api'),
    path('api/enrollment/<int:request_id>/fail/', views.enrollment_fail_api, name='enrollment_fail_api'),

    # Time Tracking
    path('time-tracking/', views.TimeTrackingDashboardView.as_view(), name='time_tracking_dashboard'),
    path('time-tracking/employee/<int:pk>/', views.TimeTrackingEmployeeDetailView.as_view(), name='time_tracking_detail'),
    path('time-tracking/employee/<int:pk>/<int:year>/<int:month>/', views.TimeTrackingMonthlySummaryView.as_view(), name='time_tracking_monthly'),
    path('time-tracking/employee/<int:pk>/audit/', views.TimeTrackingAuditTrailView.as_view(), name='time_tracking_audit'),

    path('login/', views.SmartLoginView.as_view(), name='login'),
    path('logout/', views.SmartLogoutView.as_view(), name='logout'),
]
