from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('attendance.urls')),
    path('devices/', include('device_manager.urls')),
    path('payroll/', include('payroll.urls')),
]