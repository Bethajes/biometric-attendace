from django.apps import AppConfig


class PayrollConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payroll'
    verbose_name = 'Payroll Management'

    def ready(self):
        try:
            from . import signals  # noqa: F401
        except ImportError:
            pass
