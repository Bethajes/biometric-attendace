from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Optional

from django.db.models import Q
from django.utils import timezone

from attendance.models import (
    AttendanceBreak,
    AttendanceLog,
    AttendanceRecord,
    AttendancePolicy,
    Employee,
    EmployeeSchedule,
    Holiday,
    LeaveRequest,
    RemoteWorkLog,
    SiteVisit,
)


@dataclass(frozen=True)
class PolicyThresholds:
    grace_period_minutes: int = 5
    late_threshold_minutes: int = 15
    absent_threshold_minutes: int = 120
    early_checkout_threshold_minutes: int = 15
    overtime_starts_after_minutes: int = 30
    minimum_overtime_minutes: int = 30
    max_overtime_minutes: int = 480
    duplicate_scan_prevention: bool = True
    duplicate_scan_cooldown_seconds: int = 60
    auto_checkout_enabled: bool = False
    auto_checkout_time: Optional[time] = None
    allow_remote_checkin: bool = False
    require_location: bool = False
    geo_fence_enforcement: bool = False
    break_deducted: bool = True
    lunch_deducted: bool = True


@dataclass(frozen=True)
class AttendanceDecision:
    status: str
    minutes_late: int = 0
    minutes_early_leave: int = 0
    overtime_minutes: int = 0
    worked_minutes: int = 0
    break_minutes: int = 0
    lunch_minutes: int = 0
    total_attendance_minutes: int = 0
    auto_checkout: bool = False
    notes: str = ''


class AttendanceEngine:
    """Classifies raw biometric scans against schedules, policies, leave, and holidays.

    Threshold resolution order (highest priority wins):
        1. Employee.attendance_policy  (per-employee override)
        2. Shift model fields          (per-shift defaults)
        3. Hardcoded engine defaults   (fallback)
    """

    def _resolve_policy(self, employee: Employee, shift=None) -> PolicyThresholds:
        """Merge policy sources: attendance_policy > shift > defaults."""
        defaults = PolicyThresholds()

        if employee.attendance_policy:
            p = employee.attendance_policy
            return PolicyThresholds(
                grace_period_minutes=p.grace_period_minutes,
                late_threshold_minutes=p.late_threshold_minutes,
                absent_threshold_minutes=p.absent_threshold_minutes,
                early_checkout_threshold_minutes=p.early_checkout_threshold_minutes,
                overtime_starts_after_minutes=p.overtime_starts_after_minutes,
                minimum_overtime_minutes=p.minimum_overtime_minutes,
                max_overtime_minutes=p.max_overtime_minutes,
                duplicate_scan_prevention=p.duplicate_scan_prevention,
                duplicate_scan_cooldown_seconds=p.duplicate_scan_cooldown_seconds,
                auto_checkout_enabled=p.auto_checkout_enabled,
                auto_checkout_time=p.auto_checkout_time,
                allow_remote_checkin=p.allow_remote_checkin,
                require_location=p.require_location,
                geo_fence_enforcement=p.geo_fence_enforcement,
                break_deducted=p.break_deducted,
                lunch_deducted=p.lunch_deducted,
            )

        if shift:
            return PolicyThresholds(
                grace_period_minutes=shift.grace_period_minutes,
                late_threshold_minutes=shift.late_threshold_minutes,
                absent_threshold_minutes=shift.absent_threshold_minutes,
                early_checkout_threshold_minutes=shift.early_checkout_threshold_minutes,
                overtime_starts_after_minutes=shift.overtime_starts_after_minutes,
                minimum_overtime_minutes=shift.minimum_overtime_minutes,
                max_overtime_minutes=defaults.max_overtime_minutes,
                duplicate_scan_prevention=defaults.duplicate_scan_prevention,
                duplicate_scan_cooldown_seconds=defaults.duplicate_scan_cooldown_seconds,
                auto_checkout_enabled=defaults.auto_checkout_enabled,
                auto_checkout_time=defaults.auto_checkout_time,
                break_deducted=defaults.break_deducted,
                lunch_deducted=defaults.lunch_deducted,
            )

        return defaults

    def calculate_employee_day(self, employee: Employee, date=None, persist=True):
        date = date or timezone.localdate()
        schedule = self.get_schedule(employee, date)
        holiday = self.get_holiday(employee, date)
        leave = self.get_leave(employee, date)
        shift = schedule.shift if schedule else None
        policy = self._resolve_policy(employee, shift)

        logs = list(
            AttendanceLog.objects.filter(employee=employee, timestamp__date=date)
            .order_by('timestamp')
        )
        breaks = list(
            AttendanceBreak.objects.filter(
                attendance_record__employee=employee,
                attendance_record__date=date,
            )
        )
        decision = self.classify(employee, date, schedule, holiday, leave, logs, breaks, policy)

        if not persist:
            return decision

        first_in = self.first_check_in(logs)
        last_out = self.last_check_out(logs)

        record, _ = AttendanceRecord.objects.update_or_create(
            employee=employee,
            date=date,
            defaults={
                'schedule': schedule,
                'shift': shift,
                'first_check_in': first_in,
                'last_check_out': last_out,
                'status': decision.status,
                'minutes_late': decision.minutes_late,
                'minutes_early_leave': decision.minutes_early_leave,
                'overtime_minutes': decision.overtime_minutes,
                'worked_minutes': decision.worked_minutes,
                'break_minutes': decision.break_minutes,
                'lunch_minutes': decision.lunch_minutes,
                'total_attendance_minutes': decision.total_attendance_minutes,
                'auto_checkout': decision.auto_checkout,
                'notes': decision.notes,
            },
        )
        return record

    def calculate_date(self, date=None):
        date = date or timezone.localdate()
        employees = Employee.objects.filter(employment_status=Employee.EmploymentStatus.ACTIVE)
        return [self.calculate_employee_day(employee, date=date) for employee in employees]

    def classify(self, employee, date, schedule, holiday, leave, logs, breaks, policy):
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

        effective_checkout = check_out
        auto_checkout_flag = False

        if policy.auto_checkout_enabled and policy.auto_checkout_time and not check_out:
            auto_dt = timezone.make_aware(datetime.combine(date, policy.auto_checkout_time))
            if timezone.now() > auto_dt:
                effective_checkout = auto_dt
                auto_checkout_flag = True

        worked = self.worked_minutes(check_in, effective_checkout)

        break_minutes = sum(b.duration_minutes for b in breaks if b.break_type == AttendanceBreak.BreakType.BREAK)
        lunch_minutes = sum(b.duration_minutes for b in breaks if b.break_type == AttendanceBreak.BreakType.LUNCH)
        total_break = 0
        if policy.break_deducted:
            total_break += break_minutes
        if policy.lunch_deducted:
            total_break += lunch_minutes
        net_worked = max(0, worked - total_break)

        early_leave = 0
        overtime = 0
        if effective_checkout:
            early_leave = max(0, int((end_dt - effective_checkout).total_seconds() // 60))
            after_shift = max(0, int((effective_checkout - end_dt).total_seconds() // 60))
            if after_shift >= policy.minimum_overtime_minutes:
                overtime = min(
                    max(0, after_shift - policy.overtime_starts_after_minutes),
                    policy.max_overtime_minutes,
                )

        if minutes_late >= policy.absent_threshold_minutes:
            status = AttendanceRecord.Status.ABSENT
        elif overtime:
            status = AttendanceRecord.Status.OVERTIME
        elif early_leave > policy.early_checkout_threshold_minutes:
            status = AttendanceRecord.Status.EARLY_LEAVE
        elif minutes_late > policy.grace_period_minutes:
            status = AttendanceRecord.Status.LATE
        else:
            status = AttendanceRecord.Status.PRESENT

        notes_parts = []
        if auto_checkout_flag:
            notes_parts.append(f'Auto-checked out at {policy.auto_checkout_time}')
        if total_break > 0:
            notes_parts.append(f'Deducted {total_break}min for breaks/lunch')

        return AttendanceDecision(
            status=status,
            minutes_late=minutes_late if status in [AttendanceRecord.Status.LATE, AttendanceRecord.Status.ABSENT] else 0,
            minutes_early_leave=early_leave if status == AttendanceRecord.Status.EARLY_LEAVE else 0,
            overtime_minutes=overtime,
            worked_minutes=net_worked,
            break_minutes=break_minutes,
            lunch_minutes=lunch_minutes,
            total_attendance_minutes=net_worked,
            auto_checkout=auto_checkout_flag,
            notes='; '.join(notes_parts),
        )

    def is_scan_allowed(self, employee: Employee) -> tuple[bool, str]:
        """Check if a new scan is allowed based on duplicate scan prevention policy."""
        policy = self._resolve_policy(employee)
        if not policy.duplicate_scan_prevention:
            return True, ''

        last_scan = (
            AttendanceLog.objects
            .filter(employee=employee, timestamp__date=timezone.localdate())
            .order_by('-timestamp')
            .first()
        )
        if not last_scan:
            return True, ''

        elapsed = (timezone.now() - last_scan.timestamp).total_seconds()
        if elapsed < policy.duplicate_scan_cooldown_seconds:
            remaining = int(policy.duplicate_scan_cooldown_seconds - elapsed)
            return False, f'Scan cooldown active. Try again in {remaining}s.'
        return True, ''

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
