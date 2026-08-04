"""
Time Tracking Engine.

Consumes AttendanceRecord data produced by the Attendance Engine.
Never talks to biometric hardware.
Produces hour aggregates and overtime classification for the Payroll Engine.
"""

from dataclasses import dataclass, field
from datetime import date, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db.models import Sum

from attendance.models import AttendanceRecord, Employee, Holiday, LeaveRequest


TWOPLACES = Decimal('0.01')
MINUTES_PER_HOUR = Decimal('60')


def minutes_to_hours(minutes: int | Decimal) -> Decimal:
    return (Decimal(minutes) / MINUTES_PER_HOUR).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass
class DayTimeSummary:
    work_date: date
    status: str
    check_in: Optional[object] = None
    check_out: Optional[object] = None
    worked_minutes: int = 0
    break_minutes: int = 0
    lunch_minutes: int = 0
    late_minutes: int = 0
    early_leave_minutes: int = 0
    overtime_minutes: int = 0
    expected_minutes: int = 0
    missing_minutes: int = 0
    is_weekend: bool = False
    is_holiday: bool = False
    is_night_shift: bool = False
    night_minutes: int = 0
    weekend_minutes: int = 0
    holiday_minutes: int = 0
    on_leave: bool = False
    leave_type: str = ''
    leave_is_paid: bool = True


@dataclass
class PeriodTimeSummary:
    employee: Employee
    start_date: date
    end_date: date
    expected_hours: Decimal = Decimal('0.00')
    worked_hours: Decimal = Decimal('0.00')
    missing_hours: Decimal = Decimal('0.00')
    overtime_hours: Decimal = Decimal('0.00')
    break_hours: Decimal = Decimal('0.00')
    lunch_hours: Decimal = Decimal('0.00')
    late_minutes: int = 0
    early_leave_minutes: int = 0
    night_hours: Decimal = Decimal('0.00')
    weekend_hours: Decimal = Decimal('0.00')
    holiday_hours: Decimal = Decimal('0.00')
    present_days: Decimal = Decimal('0.00')
    absent_days: Decimal = Decimal('0.00')
    unpaid_leave_days: Decimal = Decimal('0.00')
    paid_leave_days: Decimal = Decimal('0.00')
    holiday_days: Decimal = Decimal('0.00')
    weekend_days: Decimal = Decimal('0.00')
    weekday_ot_minutes: int = 0
    weekend_ot_minutes: int = 0
    holiday_ot_minutes: int = 0
    night_ot_minutes: int = 0
    days: list = field(default_factory=list)


class TimeTrackingEngine:
    """Aggregates attendance into payroll-ready hour summaries."""

    NIGHT_START = time(22, 0)
    NIGHT_END = time(6, 0)

    PAID_LEAVE_TYPES = {
        'ANNUAL', 'SICK', 'PERSONAL', 'MATERNITY', 'PATERNITY', 'BEREAVEMENT', 'COMPOFF',
    }
    UNPAID_LEAVE_TYPES = {'UNPAID'}

    def __init__(self, leave_impact_lookup: Optional[dict] = None):
        """
        leave_impact_lookup: optional {leave_type: {'is_paid': bool, 'pay_percentage': Decimal}}
        Loaded from LeavePayrollImpact when provided by Payroll Engine.
        """
        self.leave_impact_lookup = leave_impact_lookup or {}

    def summarize_period(
        self,
        employee: Employee,
        start_date: date,
        end_date: date,
        expected_daily_hours: Decimal = Decimal('8.00'),
        expected_monthly_hours: Optional[Decimal] = None,
    ) -> PeriodTimeSummary:
        records = {
            r.date: r
            for r in AttendanceRecord.objects.filter(
                employee=employee,
                date__gte=start_date,
                date__lte=end_date,
            ).select_related('shift', 'schedule')
        }
        holidays = {
            h.date: h
            for h in Holiday.objects.filter(date__gte=start_date, date__lte=end_date)
            if h.department_id is None or h.department_id == employee.department_id
        }
        leaves = list(
            LeaveRequest.objects.filter(
                employee=employee,
                status=LeaveRequest.Status.APPROVED,
                start_date__lte=end_date,
                end_date__gte=start_date,
            )
        )

        summary = PeriodTimeSummary(employee=employee, start_date=start_date, end_date=end_date)
        expected_daily_minutes = int(expected_daily_hours * 60)
        cursor = start_date

        while cursor <= end_date:
            day = self._summarize_day(
                employee=employee,
                work_date=cursor,
                record=records.get(cursor),
                holiday=holidays.get(cursor),
                leaves=leaves,
                expected_daily_minutes=expected_daily_minutes,
            )
            summary.days.append(day)
            self._accumulate(summary, day)
            cursor += timedelta(days=1)

        if expected_monthly_hours is not None:
            summary.expected_hours = Decimal(expected_monthly_hours).quantize(TWOPLACES)
        else:
            # Count expected hours only on scheduled / payable work days
            workday_count = sum(
                1 for d in summary.days
                if not d.is_weekend and not d.is_holiday and not d.on_leave
            )
            # Also include paid leave days as expected (employee is paid, hours "covered")
            paid_leave_count = sum(1 for d in summary.days if d.on_leave and d.leave_is_paid)
            holiday_paid = sum(1 for d in summary.days if d.is_holiday)
            payable_days = workday_count + paid_leave_count + holiday_paid
            summary.expected_hours = minutes_to_hours(payable_days * expected_daily_minutes)

        # Missing hours: expected minus worked, but do not count OT as filling missing
        # Paid leave / holidays already reduce the "need to work" via expected_hours logic;
        # worked_hours only counts actual presence.
        raw_missing = summary.expected_hours - summary.worked_hours - (
            (summary.paid_leave_days + summary.holiday_days) * expected_daily_hours
        )
        # Simpler approach: missing = max(0, expected_work_minutes - worked) from day totals
        total_missing_minutes = sum(d.missing_minutes for d in summary.days)
        summary.missing_hours = minutes_to_hours(total_missing_minutes)
        if raw_missing > summary.missing_hours:
            summary.missing_hours = max(Decimal('0.00'), raw_missing).quantize(TWOPLACES)

        return summary

    def _summarize_day(
        self,
        employee: Employee,
        work_date: date,
        record: Optional[AttendanceRecord],
        holiday: Optional[Holiday],
        leaves: list,
        expected_daily_minutes: int,
    ) -> DayTimeSummary:
        leave = self._leave_on(work_date, leaves)
        is_weekend = work_date.weekday() >= 5
        if record and record.schedule_id:
            is_weekend = not record.schedule.works_on(work_date)

        day = DayTimeSummary(
            work_date=work_date,
            status=record.status if record else ('HOLIDAY' if holiday else ('WEEKEND' if is_weekend else 'ABSENT')),
            is_weekend=is_weekend and not holiday,
            is_holiday=bool(holiday),
            expected_minutes=0 if (is_weekend or holiday or leave) else expected_daily_minutes,
        )

        if leave:
            day.on_leave = True
            day.leave_type = leave.leave_type
            day.leave_is_paid = self._is_leave_paid(leave.leave_type)
            day.status = 'ON_LEAVE'
            day.expected_minutes = 0
            return day

        if holiday:
            day.expected_minutes = 0
            if record and record.worked_minutes:
                # Worked on holiday
                day.worked_minutes = record.worked_minutes
                day.holiday_minutes = record.worked_minutes
                day.overtime_minutes = record.overtime_minutes or record.worked_minutes
                day.check_in = record.first_check_in
                day.check_out = record.last_check_out
            return day

        if is_weekend:
            day.expected_minutes = 0
            if record and record.worked_minutes:
                day.worked_minutes = record.worked_minutes
                day.weekend_minutes = record.worked_minutes
                day.overtime_minutes = record.overtime_minutes or record.worked_minutes
                day.check_in = record.first_check_in
                day.check_out = record.last_check_out
            return day

        if not record:
            day.status = 'ABSENT'
            # Full-day absence is tracked via absent_days; do not also count as missing hours.
            day.missing_minutes = 0
            return day

        day.check_in = record.first_check_in
        day.check_out = record.last_check_out
        day.worked_minutes = record.worked_minutes or 0
        day.break_minutes = record.break_minutes or 0
        day.lunch_minutes = record.lunch_minutes or 0
        day.late_minutes = record.minutes_late or 0
        day.early_leave_minutes = record.minutes_early_leave or 0
        day.overtime_minutes = record.overtime_minutes or 0
        day.status = record.status

        if record.shift_id and record.shift.is_overnight:
            day.is_night_shift = True
            day.night_minutes = day.worked_minutes

        if record.status == AttendanceRecord.Status.ABSENT or (
            day.worked_minutes == 0 and not record.first_check_in
        ):
            day.missing_minutes = 0
        else:
            day.missing_minutes = max(0, expected_daily_minutes - day.worked_minutes)

        return day

    def _accumulate(self, summary: PeriodTimeSummary, day: DayTimeSummary) -> None:
        summary.worked_hours += minutes_to_hours(day.worked_minutes)
        summary.break_hours += minutes_to_hours(day.break_minutes)
        summary.lunch_hours += minutes_to_hours(day.lunch_minutes)
        summary.late_minutes += day.late_minutes
        summary.early_leave_minutes += day.early_leave_minutes
        summary.overtime_hours += minutes_to_hours(day.overtime_minutes)
        summary.night_hours += minutes_to_hours(day.night_minutes)
        summary.weekend_hours += minutes_to_hours(day.weekend_minutes)
        summary.holiday_hours += minutes_to_hours(day.holiday_minutes)

        if day.on_leave:
            if day.leave_is_paid:
                summary.paid_leave_days += Decimal('1')
            else:
                summary.unpaid_leave_days += Decimal('1')
            return

        if day.is_holiday:
            summary.holiday_days += Decimal('1')
            if day.overtime_minutes:
                summary.holiday_ot_minutes += day.overtime_minutes
            return

        if day.is_weekend:
            summary.weekend_days += Decimal('1')
            if day.overtime_minutes:
                summary.weekend_ot_minutes += day.overtime_minutes
            return

        if day.status == 'ABSENT' or (day.worked_minutes == 0 and not day.check_in):
            summary.absent_days += Decimal('1')
            return

        summary.present_days += Decimal('1')
        if day.is_night_shift and day.overtime_minutes:
            summary.night_ot_minutes += day.overtime_minutes
        elif day.overtime_minutes:
            summary.weekday_ot_minutes += day.overtime_minutes

    def _leave_on(self, work_date: date, leaves: list) -> Optional[LeaveRequest]:
        for leave in leaves:
            if leave.start_date <= work_date <= leave.end_date:
                return leave
        return None

    def _is_leave_paid(self, leave_type: str) -> bool:
        if leave_type in self.leave_impact_lookup:
            return bool(self.leave_impact_lookup[leave_type].get('is_paid', True))
        if leave_type in self.UNPAID_LEAVE_TYPES:
            return False
        return leave_type in self.PAID_LEAVE_TYPES

    @staticmethod
    def period_totals_from_db(employee: Employee, start_date: date, end_date: date) -> dict:
        """Fast aggregate for dashboards without day-by-day classification."""
        agg = AttendanceRecord.objects.filter(
            employee=employee,
            date__gte=start_date,
            date__lte=end_date,
        ).aggregate(
            worked=Sum('worked_minutes'),
            overtime=Sum('overtime_minutes'),
            late=Sum('minutes_late'),
            early=Sum('minutes_early_leave'),
            breaks=Sum('break_minutes'),
            lunch=Sum('lunch_minutes'),
        )
        return {
            'worked_hours': minutes_to_hours(agg['worked'] or 0),
            'overtime_hours': minutes_to_hours(agg['overtime'] or 0),
            'late_minutes': agg['late'] or 0,
            'early_leave_minutes': agg['early'] or 0,
            'break_hours': minutes_to_hours(agg['breaks'] or 0),
            'lunch_hours': minutes_to_hours(agg['lunch'] or 0),
        }
