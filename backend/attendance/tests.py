from datetime import date, datetime, time

from django.test import TestCase
from django.utils import timezone
from organizations.models import Company, Department

from .models import (
    AttendanceLog,
    AttendanceRecord,
    Employee,
    EmployeeSchedule,
    Holiday,
    LeaveRequest,
    Shift,
)
from .services.attendance_engine import AttendanceEngine


class AttendanceEngineTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Corp', slug='test-corp')
        self.department = Department.objects.create(name='Engineering', code='ENG', company=self.company)
        self.employee = Employee.objects.create(
            organization_id='EMP-001',
            first_name='Maya',
            last_name='Chen',
            department=self.department,
            job_title='Engineer',
            fingerprint_id=101,
        )
        self.shift = Shift.objects.create(
            name='General',
            start_time=time(9, 0),
            end_time=time(17, 0),
            grace_period_minutes=5,
            late_threshold_minutes=15,
            absent_threshold_minutes=120,
            early_checkout_threshold_minutes=15,
            overtime_starts_after_minutes=15,
            minimum_overtime_minutes=30,
        )
        self.schedule = EmployeeSchedule.objects.create(
            employee=self.employee,
            department=self.department,
            shift=self.shift,
            effective_start=date(2026, 7, 1),
        )
        self.engine = AttendanceEngine()

    def log(self, day, hour, minute, scan_type):
        timestamp = timezone.make_aware(datetime.combine(day, time(hour, minute)))
        log = AttendanceLog.objects.create(employee=self.employee, scan_type=scan_type)
        AttendanceLog.objects.filter(pk=log.pk).update(timestamp=timestamp)
        log.refresh_from_db()
        return log

    def test_present_within_grace_period(self):
        day = date(2026, 7, 20)
        self.log(day, 9, 4, 'IN')
        self.log(day, 17, 0, 'OUT')

        record = self.engine.calculate_employee_day(self.employee, day)

        self.assertEqual(record.status, AttendanceRecord.Status.PRESENT)
        self.assertEqual(record.worked_minutes, 476)

    def test_late_after_grace_period(self):
        day = date(2026, 7, 20)
        self.log(day, 9, 12, 'IN')

        record = self.engine.calculate_employee_day(self.employee, day)

        self.assertEqual(record.status, AttendanceRecord.Status.LATE)
        self.assertEqual(record.minutes_late, 12)

    def test_absent_without_check_in(self):
        record = self.engine.calculate_employee_day(self.employee, date(2026, 7, 20))

        self.assertEqual(record.status, AttendanceRecord.Status.ABSENT)

    def test_weekend_without_logs(self):
        record = self.engine.calculate_employee_day(self.employee, date(2026, 7, 19))

        self.assertEqual(record.status, AttendanceRecord.Status.WEEKEND)

    def test_holiday_without_logs(self):
        day = date(2026, 7, 20)
        Holiday.objects.create(name='Founders Day', date=day)

        record = self.engine.calculate_employee_day(self.employee, day)

        self.assertEqual(record.status, AttendanceRecord.Status.HOLIDAY)

    def test_approved_leave_without_logs(self):
        day = date(2026, 7, 20)
        LeaveRequest.objects.create(
            employee=self.employee,
            leave_type=LeaveRequest.LeaveType.ANNUAL,
            start_date=day,
            end_date=day,
            status=LeaveRequest.Status.APPROVED,
            days=1,
        )

        record = self.engine.calculate_employee_day(self.employee, day)

        self.assertEqual(record.status, AttendanceRecord.Status.ON_LEAVE)

    def test_overtime_after_shift_rule(self):
        day = date(2026, 7, 20)
        self.log(day, 9, 0, 'IN')
        self.log(day, 17, 45, 'OUT')

        record = self.engine.calculate_employee_day(self.employee, day)

        self.assertEqual(record.status, AttendanceRecord.Status.OVERTIME)
        self.assertEqual(record.overtime_minutes, 30)

    def test_unexpected_attendance_on_weekend(self):
        day = date(2026, 7, 19)
        self.log(day, 10, 0, 'IN')

        record = self.engine.calculate_employee_day(self.employee, day)

        self.assertEqual(record.status, AttendanceRecord.Status.UNEXPECTED)
