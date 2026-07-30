import logging
from datetime import datetime, time

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import AttendanceLog, AttendancePolicy, Employee
from attendance.services.attendance_engine import AttendanceEngine

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Apply auto-checkout for employees who have not checked out today.'

    def handle(self, *args, **options):
        today = timezone.localdate()
        engine = AttendanceEngine()
        count = 0

        policies = AttendancePolicy.objects.filter(
            auto_checkout_enabled=True,
            is_active=True,
            auto_checkout_time__isnull=False,
        )

        for policy in policies:
            if not policy.auto_checkout_time:
                continue

            auto_dt = timezone.make_aware(datetime.combine(today, policy.auto_checkout_time))
            if timezone.now() < auto_dt:
                continue

            employees = Employee.objects.filter(
                employment_status=Employee.EmploymentStatus.ACTIVE,
                attendance_policy=policy,
            )
            for employee in employees:
                last_scan = (
                    AttendanceLog.objects
                    .filter(employee=employee, timestamp__date=today)
                    .order_by('-timestamp')
                    .first()
                )
                if last_scan and last_scan.scan_type == 'IN':
                    engine.calculate_employee_day(employee, today)
                    count += 1

        employees_no_policy = Employee.objects.filter(
            employment_status=Employee.EmploymentStatus.ACTIVE,
            attendance_policy__isnull=True,
        )
        default_policy = AttendancePolicy.objects.filter(is_active=True).first()
        if default_policy and default_policy.auto_checkout_enabled and default_policy.auto_checkout_time:
            auto_dt = timezone.make_aware(datetime.combine(today, default_policy.auto_checkout_time))
            if timezone.now() >= auto_dt:
                for employee in employees_no_policy:
                    last_scan = (
                        AttendanceLog.objects
                        .filter(employee=employee, timestamp__date=today)
                        .order_by('-timestamp')
                        .first()
                    )
                    if last_scan and last_scan.scan_type == 'IN':
                        engine.calculate_employee_day(employee, today)
                        count += 1

        self.stdout.write(self.style.SUCCESS(f'Auto-checkout processed {count} employees for {today}'))
