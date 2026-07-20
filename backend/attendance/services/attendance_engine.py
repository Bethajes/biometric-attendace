from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from attendance.models import (
    AttendanceLog,
    AttendanceRecord,
    Employee,
    EmployeeSchedule,
    Holiday,
    LeaveRequest,
)


@dataclass(frozen=True)
class AttendanceDecision:
    status: str
    minutes_late: int = 0
    minutes_early_leave: int = 0
    overtime_minutes: int = 0
    worked_minutes: int = 0
    notes: str = ''


class AttendanceEngine:
    """Classifies raw biometric scans against schedules, leave, and holidays."""

    def calculate_employee_day(self, employee: Employee, date=None, persist=True):
        date = date or timezone.localdate()
        schedule = self.get_schedule(employee, date)
        holiday = self.get_holiday(employee, date)
        leave = self.get_leave(employee, date)
        logs = list(
            AttendanceLog.objects.filter(employee=employee, timestamp__date=date)
            .order_by('timestamp')
        )
        decision = self.classify(employee, date, schedule, holiday, leave, logs)

        if not persist:
            return decision

        record, _ = AttendanceRecord.objects.update_or_create(
            employee=employee,
            date=date,
            defaults={
                'schedule': schedule,
                'shift': schedule.shift if schedule else None,
                'first_check_in': self.first_check_in(logs),
                'last_check_out': self.last_check_out(logs),
                'status': decision.status,
                'minutes_late': decision.minutes_late,
                'minutes_early_leave': decision.minutes_early_leave,
                'overtime_minutes': decision.overtime_minutes,
                'worked_minutes': decision.worked_minutes,
                'notes': decision.notes,
            },
        )
        return record

    def calculate_date(self, date=None):
        date = date or timezone.localdate()
        employees = Employee.objects.filter(employment_status=Employee.EmploymentStatus.ACTIVE)
        return [self.calculate_employee_day(employee, date=date) for employee in employees]

    def classify(self, employee, date, schedule, holiday, leave, logs):
        check_in = self.first_check_in(logs)
        check_out = self.last_check_out(logs)

        if holiday:
            if logs:
                return AttendanceDecision(
                    AttendanceRecord.Status.UNEXPECTED,
                    worked_minutes=self.worked_minutes(check_in, check_out),
                    notes=f'Attendance recorded during holiday: {holiday.name}',
                )
            return AttendanceDecision(AttendanceRecord.Status.HOLIDAY, notes=holiday.name)

        if leave:
            if logs:
                return AttendanceDecision(
                    AttendanceRecord.Status.UNEXPECTED,
                    worked_minutes=self.worked_minutes(check_in, check_out),
                    notes=f'Attendance recorded during approved {leave.get_leave_type_display()} leave.',
                )
            return AttendanceDecision(AttendanceRecord.Status.ON_LEAVE, notes=leave.get_leave_type_display())

        if not schedule:
            if logs:
                return AttendanceDecision(
                    AttendanceRecord.Status.UNEXPECTED,
                    worked_minutes=self.worked_minutes(check_in, check_out),
                    notes='No active schedule for this date.',
                )
            return AttendanceDecision(AttendanceRecord.Status.ABSENT, notes='No active schedule.')

        if not schedule.works_on(date):
            if logs:
                return AttendanceDecision(
                    AttendanceRecord.Status.UNEXPECTED,
                    worked_minutes=self.worked_minutes(check_in, check_out),
                    notes='Attendance recorded on a non-working day.',
                )
            return AttendanceDecision(AttendanceRecord.Status.WEEKEND)

        if not check_in:
            return AttendanceDecision(AttendanceRecord.Status.ABSENT)

        shift = schedule.shift
        start_dt, end_dt = self.shift_window(date, schedule)
        minutes_late = max(0, int((check_in - start_dt).total_seconds() // 60))
        worked_minutes = self.worked_minutes(check_in, check_out)
        early_leave = 0
        overtime = 0

        if check_out:
            early_leave = max(0, int((end_dt - check_out).total_seconds() // 60))
            after_shift = max(0, int((check_out - end_dt).total_seconds() // 60))
            if after_shift >= shift.minimum_overtime_minutes:
                overtime = max(0, after_shift - shift.overtime_starts_after_minutes)

        if minutes_late >= shift.absent_threshold_minutes:
            status = AttendanceRecord.Status.ABSENT
        elif overtime:
            status = AttendanceRecord.Status.OVERTIME
        elif early_leave > shift.early_checkout_threshold_minutes:
            status = AttendanceRecord.Status.EARLY_LEAVE
        elif minutes_late > shift.grace_period_minutes:
            status = AttendanceRecord.Status.LATE
        else:
            status = AttendanceRecord.Status.PRESENT

        return AttendanceDecision(
            status=status,
            minutes_late=minutes_late if status in [AttendanceRecord.Status.LATE, AttendanceRecord.Status.ABSENT] else 0,
            minutes_early_leave=early_leave if status == AttendanceRecord.Status.EARLY_LEAVE else 0,
            overtime_minutes=overtime,
            worked_minutes=worked_minutes,
        )

    def get_schedule(self, employee, date):
        return (
            EmployeeSchedule.objects.select_related('shift', 'department')
            .filter(employee=employee, effective_start__lte=date)
            .filter(Q(effective_end__isnull=True) | Q(effective_end__gte=date))
            .order_by('-effective_start')
            .first()
        )

    def get_holiday(self, employee, date):
        return (
            Holiday.objects.filter(date=date)
            .filter(Q(department__isnull=True) | Q(department=employee.department))
            .filter(Q(office_location__isnull=True) | Q(office_location=employee.office_location))
            .first()
        )

    def get_leave(self, employee, date):
        return (
            LeaveRequest.objects.filter(
                employee=employee,
                status=LeaveRequest.Status.APPROVED,
                start_date__lte=date,
                end_date__gte=date,
            )
            .order_by('-created_at')
            .first()
        )

    def shift_window(self, date, schedule):
        shift = schedule.shift
        start_time = schedule.flexible_start_time if schedule.is_flexible and schedule.flexible_start_time else shift.start_time
        end_time = schedule.flexible_end_time if schedule.is_flexible and schedule.flexible_end_time else shift.end_time
        start_dt = timezone.make_aware(datetime.combine(date, start_time))
        end_dt = timezone.make_aware(datetime.combine(date, end_time))
        if shift.is_overnight or end_dt <= start_dt:
            end_dt += timedelta(days=1)
        return start_dt, end_dt

    @staticmethod
    def first_check_in(logs):
        return next((log.timestamp for log in logs if log.scan_type == 'IN'), None)

    @staticmethod
    def last_check_out(logs):
        outs = [log.timestamp for log in logs if log.scan_type == 'OUT']
        return outs[-1] if outs else None

    @staticmethod
    def worked_minutes(check_in, check_out):
        if not check_in or not check_out:
            return 0
        return max(0, int((check_out - check_in).total_seconds() // 60))
