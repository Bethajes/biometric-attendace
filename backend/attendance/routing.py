from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/devices/(?P<device_id>\d+)/$', consumers.DeviceEventConsumer.as_asgi()),
    re_path(r'ws/enrollment/(?P<enrollment_id>\d+)/$', consumers.EnrollmentProgressConsumer.as_asgi()),
    re_path(r'ws/device-dashboard/$', consumers.DeviceDashboardConsumer.as_asgi()),
    re_path(r'ws/dashboard-live/$', consumers.DashboardLiveActivityConsumer.as_asgi()),
]
