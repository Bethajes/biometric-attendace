from django.urls import path

from . import views

urlpatterns = [
    # Page views
    path('', views.DeviceDashboardView.as_view(), name='device_dashboard'),
    path('devices/', views.DeviceListView.as_view(), name='device_list'),
    path('devices/<int:pk>/', views.DeviceDetailView.as_view(), name='device_detail'),
    path('enrollment/', views.EnrollmentPanelView.as_view(), name='enrollment_panel'),
    path('logs/', views.DeviceLogsView.as_view(), name='device_logs'),

    # AJAX API — device control
    path('api/devices/<int:device_id>/connect/', views.api_connect_device, name='api_device_connect'),
    path('api/devices/<int:device_id>/disconnect/', views.api_disconnect_device, name='api_device_disconnect'),
    path('api/devices/<int:device_id>/status/', views.api_device_status, name='api_device_status'),
    path('api/devices/<int:device_id>/restart/', views.api_restart_device, name='api_device_restart'),
    path('api/devices/<int:device_id>/request-status/', views.api_request_status, name='api_request_status'),
    path('api/devices/<int:device_id>/return-attendance/', views.api_return_to_attendance, name='api_return_to_attendance'),

    # AJAX API — enrollment
    path('api/enrollment/start/', views.api_start_enrollment, name='api_start_enrollment'),
    path('api/enrollment/<int:enrollment_id>/progress/', views.api_enrollment_progress, name='api_enrollment_progress'),
    path('api/enrollment/list/', views.api_enrollment_list, name='api_enrollment_list'),

    # AJAX API — fingerprint management
    path('api/fingerprint/delete/', views.api_delete_fingerprint, name='api_delete_fingerprint'),

    # AJAX API — logs / events
    path('api/events/recent/', views.api_recent_events, name='api_recent_events'),

    # Bridge push endpoint
    path('api/devices/<int:device_id>/message/', views.api_process_arduino_message, name='api_process_message'),
]
