from django.apps import AppConfig


class DeviceManagerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'device_manager'
    verbose_name = 'Device Manager'

    def ready(self):
        import attendance.consumers  # noqa: F401
