"""
Time Tracking Engine — Bridge between Attendance Engine and Payroll Engine.

Consumes immutable AttendanceLog events (fingerprint/face scans).
Produces DailyTimeSummary (worked hours, overtime, late, breaks, etc.).
Aggregates into MonthlyTimeSummary for Payroll Engine consumption.

Never reads raw attendance events in Payroll — only reads MonthlyTimeSummary.
"""

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from attendance.models import (
    AttendanceLog,
    AttendanceRecord,
    DailyTimeSummary,
    Employee,
    EmployeeSchedule,
    Holiday,
    LeaveRequest,
    MonthlyTimeSummary,
    Shift,
)
from attendance.services.attendance_engine import AttendanceEngine
from payroll.services.audit import log_payroll_action


TWOPLACES = Decimal('0.01')
MINUTES_PER_HOUR = Decimal('60')


def minutes_to_hours(minutes: int | Decimal) -> Decimal:
    return (Decimal(minutes) / MINUTES_PER_HOUR).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def hours_to_minutes(hours: Decimal) -> int:
    return int((hours * MINUTES_PER_HOUR).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class DayCalculation:
    worked_minutes: int = 0
    expected_minutes: int = 0
    attendance_percentage: Decimal = Decimal('0.00')
    late_minutes: int = 0
    early_leave_minutes: int = 0
    break_minutes: int = 0
    lunch_minutes: int = 0
    missing_minutes: int = 0
    overtime_minutes: int = 0
    night_minutes: int = 0
    weekend_minutes: int = 0
    holiday_minutes: int = 0
    is_weekend: bool = False
    is_holiday: bool = False
    is_night_shift: bool = False
    on_leave: bool = False
    leave_type: str = ''
    leave_is_paid: bool = True


@dataclass
class MonthAggregation:
    expected_hours: Decimal = Decimal('0.00')
    worked_hours: Decimal = Decimal('0.00')
    attendance_percentage: Decimal = Decimal('0.00')
    late_minutes: int = 0
    missing_hours: Decimal = Decimal('0.00')
    overtime_hours: Decimal = Decimal('0.00')
    holiday_hours: Decimal = Decimal('0.00')
    weekend_hours: Decimal = Decimal('0.00')
    night_hours: Decimal = Decimal('0.00')
    approved_leave_hours: Decimal = Decimal('0.00')
    unpaid_leave_hours: Decimal = Decimal('0.00')
    paid_leave_hours: Decimal = Decimal('0.00')
    present_days: int = 0
    absent_days: int = 0
    paid_leave_days: int = 0
    unpaid_leave_days: int = 0


class TimeTrackingEngine:
    """
    Time Tracking Engine — converts immutable AttendanceLog events into
    worked-time summaries for Payroll.
    """

    NIGHT_START = time(22, 0)
    NIGHT_END = time(6, 0)

    PAID_LEAVE_TYPES = {
        'ANNUAL', 'SICK', 'PERSONAL', 'MATERNITY', 'PATERNITY', 'BEREAVEMENT', 'COMPOFF',
    }
    UNPAID_LEAVE_TYPES = {'UNPAID'}

    def __init__(
        self,
        leave_impact_lookup: Optional[dict] = None,
        actor=None,
        request=None,
    ):
        """
        leave_impact_lookup: {leave_type: {'is_paid': bool, 'pay_percentage': Decimal}}
        actor: User performing the calculation (for audit)
        request: HTTP request (for audit IP/UA)
        """
        self.leave_impact_lookup = leave_impact_lookup or {}
        self.actor = actor
        self.request = request
        self.attendance_engine = AttendanceEngine()

    # ---------------------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------------------

    def calculate_daily_summary(
        self,
        employee: Employee,
        work_date: date,
        persist: bool = True,
    ) -> DailyTimeSummary:
        """
        Calculate DailyTimeSummary for one employee on one date.
        Reads AttendanceLog events, classifies them, produces worked time.
        """
        schedule = self._get_schedule(employee, work_date)
        holiday = self._get_holiday(employee, work_date)
        leave = self._get_leave(employee, work_date)
        shift = schedule.shift if schedule else None
        policy = self.attendance_engine._resolve_policy(employee, shift)

        logs = list(
            AttendanceLog.objects.filter(employee=employee, timestamp__date=work_date)
            .order_by('timestamp')
        )

        calc = self._classify_day(
            employee=employee,
            work_date=work_date,
            schedule=schedule,
            holiday=holiday,
            leave=leave,
            logs=logs,
            policy=policy,
            shift=shift,
        )

        if persist:
            return self._persist_daily_summary(employee, work_date, calc, schedule, logs)
        return self._build_daily_summary_instance(employee, work_date, calc, schedule)

    def calculate_monthly_summary(
        self,
        employee: Employee,
        year: int,
        month: int,
        persist: bool = True,
    ) -> MonthlyTimeSummary:
        """
        Aggregate all DailyTimeSummary records for a month into MonthlyTimeSummary.
        """
        from calendar import monthrange

        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        daily_summaries = DailyTimeSummary.objects.filter(
            employee=employee,
            date__gte=start_date,
            date__lte=end_date,
        ).select_related('attendance_record')

        agg = self._aggregate_month(daily_summaries)

        if persist:
            return self._persist_monthly_summary(
                employee, year, month, agg, daily_summaries.count()
            )
        return self._build_monthly_summary_instance(employee, year, month, agg)

    def recalculate_employee_month(
        self,
        employee: Employee,
        year: int,
        month: int,
        actor=None,
        request=None,
    ) -> MonthlyTimeSummary:
        """
        Full recalculation: recalculate all daily summaries, then monthly.
        Logs audit trail for traceability.
        """
        actor = actor or self.actor
        request = request or self.request

        from calendar import monthrange
        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        daily_summaries = DailyTimeSummary.objects.filter(
            employee=employee,
            date__gte=start_date,
            date__lte=end_date,
        )

        before_data = {
            'daily_count': daily_summaries.count(),
            'summaries': [
                {
                    'date': str(ds.date),
                    'worked_minutes': ds.worked_minutes,
                    'overtime_minutes': ds.overtime_minutes,
                    'late_minutes': ds.late_minutes,
                    'recalculation_count': ds.recalculation_count,
                }
                for ds in daily_summaries
            ],
        }

        cursor = start_date
        while cursor <= end_date:
            self.calculate_daily_summary(employee, cursor, persist=True)
            cursor += timedelta(days=1)

        monthly = self.calculate_monthly_summary(employee, year, month, persist=True)

        after_data = {
            'daily_count': DailyTimeSummary.objects.filter(
                employee=employee, date__gte=start_date, date__lte=end_date
            ).count(),
            'monthly': {
                'worked_hours': str(monthly.worked_hours),
                'expected_hours': str(monthly.expected_hours),
                'overtime_hours': str(monthly.overtime_hours),
                'late_minutes': monthly.late_minutes,
                'recalculation_count': monthly.recalculation_count,
            },
        }

        log_payroll_action(
            action='CALCULATE',
            summary=f'Recalculated time tracking for {employee} - {year}-{month:02d}',
            actor=actor,
            entity_type='MonthlyTimeSummary',
            entity_id=monthly.pk,
            request=request,
            before_data=before_data,
            after_data=after_data,
        )

        return monthly

    def recalculate_employee_range(
        self,
        employee: Employee,
        start_date: date,
        end_date: date,
        actor=None,
        request=None,
    ) -> list[DailyTimeSummary]:
        """Recalculate daily summaries for a date range."""
        actor = actor or self.actor
        request = request or self.request

        results = []
        cursor = start_date
        while cursor <= end_date:
            ds = self.calculate_daily_summary(employee, cursor, persist=True)
            results.append(ds)
            cursor += timedelta(days=1)

        if results:
            first = results[0]
            last = results[-1]
            log_payroll_action(
                action='CALCULATE',
                summary=f'Recalculated daily time for {employee} {first.date} to {last.date}',
                actor=actor,
                entity_type='DailyTimeSummary',
                entity_id=first.pk,
                request=request,
                after_data={'count': len(results), 'start': str(first.date), 'end': str(last.date)},
            )
        return results

    def get_employee_timeline(
        self,
        employee: Employee,
        start_date: date,
        end_date: date,
    ) -> list[dict]:
        """
        Get full audit trail for an employee period:
        MonthlyTimeSummary -> DailyTimeSummary -> AttendanceRecord -> AttendanceLog
        Used by Payroll audit UI to trace Net Salary -> Fingerprint Events.
        """
        timeline = []

        monthly = MonthlyTimeSummary.objects.filter(
            employee=employee,
            year=start_date.year,
            month=start_date.month,
        ).first()
        if monthly:
            timeline.append({
                'level': 'monthly_summary',
                'label': f'Monthly Summary: {monthly.year}-{monthly.month:02d}',
                'data': {
                    'worked_hours': str(monthly.worked_hours),
                    'expected_hours': str(monthly.expected_hours),
                    'attendance_percentage': str(monthly.attendance_percentage),
                    'overtime_hours': str(monthly.overtime_hours),
                    'late_minutes': monthly.late_minutes,
                    'missing_hours': str(monthly.missing_hours),
                    'holiday_hours': str(monthly.holiday_hours),
                    'weekend_hours': str(monthly.weekend_hours),
                    'approved_leave_hours': str(monthly.approved_leave_hours),
                    'unpaid_leave_hours': str(monthly.unpaid_leave_hours),
                    'recalculation_count': monthly.recalculation_count,
                    'last_recalculated_at': monthly.last_recalculated_at,
                },
                'id': monthly.pk,
            })

        daily_summaries = DailyTimeSummary.objects.filter(
            employee=employee,
            date__gte=start_date,
            date__lte=end_date,
        ).select_related('attendance_record').order_by('date')

        for ds in daily_summaries:
            ar = ds.attendance_record
            timeline.append({
                'level': 'daily_summary',
                'label': f'Daily Summary: {ds.date}',
                'data': {
                    'worked_minutes': ds.worked_minutes,
                    'expected_minutes': ds.expected_minutes,
                    'attendance_percentage': str(ds.attendance_percentage),
                    'late_minutes': ds.late_minutes,
                    'early_leave_minutes': ds.early_leave_minutes,
                    'break_minutes': ds.break_minutes,
                    'lunch_minutes': ds.lunch_minutes,
                    'missing_minutes': ds.missing_minutes,
                    'overtime_minutes': ds.overtime_minutes,
                    'night_minutes': ds.night_minutes,
                    'weekend_minutes': ds.weekend_minutes,
                    'holiday_minutes': ds.holiday_minutes,
                    'is_weekend': ds.is_weekend,
                    'is_holiday': ds.is_holiday,
                    'is_night_shift': ds.is_night_shift,
                    'on_leave': ds.on_leave,
                    'leave_type': ds.leave_type,
                    'leave_is_paid': ds.leave_is_paid,
                    'calculated_at': ds.calculated_at,
                    'recalculation_count': ds.recalculation_count,
                },
                'id': ds.pk,
                'attendance_record_id': ar.pk if ar else None,
            })

            if ar:
                logs = AttendanceLog.objects.filter(
                    employee=employee, timestamp__date=ds.date
                ).order_by('timestamp')

                timeline.append({
                    'level': 'attendance_record',
                    'label': f'Attendance Record: {ar.date}',
                    'data': {
                        'status': ar.status,
                        'first_check_in': ar.first_check_in,
                        'last_check_out': ar.last_check_out,
                        'minutes_late': ar.minutes_late,
                        'minutes_early_leave': ar.minutes_early_leave,
                        'overtime_minutes': ar.overtime_minutes,
                        'worked_minutes': ar.worked_minutes,
                        'break_minutes': ar.break_minutes,
                        'lunch_minutes': ar.lunch_minutes,
                        'auto_checkout': ar.auto_checkout,
                        'notes': ar.notes,
                        'calculated_at': ar.calculated_at,
                    },
                    'id': ar.pk,
                    'events': [
                        {
                            'level': 'attendance_event',
                            'label': f'{log.get_event_type_display()} at {log.timestamp.strftime("%H:%M")}',
                            'data': {
                                'event_type': log.event_type,
                                'timestamp': log.timestamp.isoformat(),
                                'biometric_method': log.biometric_method,
                                'verification_status': log.verification_status,
                                'source': log.source,
                                'latitude': str(log.latitude) if log.latitude else None,
                                'longitude': str(log.longitude) if log.longitude else None,
                                'device': log.device.name if log.device_id else None,
                            },
                            'id': log.pk,
                        }
                        for log in logs
                    ],
                })

        return timeline

    # ---------------------------------------------------------------------
    # INTERNAL CALCULATION
    # ---------------------------------------------------------------------

    def _classify_day(
        self,
        employee: Employee,
        work_date: date,
        schedule: Optional[EmployeeSchedule],
        holiday: Optional[Holiday],
        leave: Optional[LeaveRequest],
        logs: list[AttendanceLog],
        policy,
        shift: Optional[Shift],
    ) -> DayCalculation:
        """Classify a single day's attendance logs into worked time metrics."""

        check_in = self._first_check_in(logs)
        check_out = self._last_check_out(logs)

        is_weekend = work_date.weekday() >= 5
        if schedule and schedule.shift_id:
            is_weekend = not schedule.works_on(work_date)

        calc = DayCalculation(
            is_weekend=is_weekend and not holiday,
            is_holiday=bool(holiday),
            on_leave=bool(leave),
            leave_type=leave.leave_type if leave else '',
            leave_is_paid=self._is_leave_paid(leave.leave_type) if leave else True,
        )

        if holiday:
            if check_in and check_out:
                worked = self._worked_minutes(check_in, check_out)
                calc = replace(
                    calc,
                    worked_minutes=worked,
                    holiday_minutes=worked,
                    overtime_minutes=worked,
                )
            return calc

        if leave:
            calc = replace(calc, expected_minutes=0)
            return calc

        if not schedule:
            if check_in and check_out:
                worked = self._worked_minutes(check_in, check_out)
                calc = replace(calc, worked_minutes=worked)
            calc = replace(calc, expected_minutes=0)
            return calc

        if not schedule.works_on(work_date):
            if check_in and check_out:
                worked = self._worked_minutes(check_in, check_out)
                calc = replace(
                    calc,
                    worked_minutes=worked,
                    weekend_minutes=worked,
                    overtime_minutes=worked,
                )
            calc = replace(calc, expected_minutes=0)
            return calc

        if not check_in:
            calc.expected_minutes = self._expected_minutes(schedule, work_date)
            return calc

        start_dt, end_dt = self._shift_window(work_date, schedule)
        calc.expected_minutes = max(0, int((end_dt - start_dt).total_seconds() // 60))

        minutes_late = max(0, int((check_in - start_dt).total_seconds() // 60))

        effective_checkout = check_out
        auto_checkout_flag = False

        if policy.auto_checkout_enabled and policy.auto_checkout_time and not check_out:
            auto_dt = timezone.make_aware(datetime.combine(work_date, policy.auto_checkout_time))
            if timezone.now() > auto_dt:
                effective_checkout = auto_dt
                auto_checkout_flag = True

        worked = self._worked_minutes(check_in, effective_checkout)

        break_minutes = self._sum_breaks(logs, 'BREAK')
        lunch_minutes = self._sum_breaks(logs, 'LUNCH')
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

        night_minutes = self._calculate_night_minutes(check_in, effective_checkout) if check_in and effective_checkout else 0

        if minutes_late >= policy.absent_threshold_minutes:
            status = 'ABSENT'
            minutes_late = 0
            early_leave = 0
            overtime = 0
            net_worked = 0
        elif overtime:
            status = 'OVERTIME'
        elif early_leave > policy.early_checkout_threshold_minutes:
            status = 'EARLY_LEAVE'
        elif minutes_late > policy.grace_period_minutes:
            status = 'LATE'
        else:
            status = 'PRESENT'

        missing_minutes = 0
        if status not in ('ABSENT', 'ON_LEAVE', 'HOLIDAY', 'WEEKEND') and worked > 0:
            missing_minutes = max(0, calc.expected_minutes - net_worked)

        calc = DayCalculation(
            worked_minutes=net_worked,
            expected_minutes=calc.expected_minutes,
            attendance_percentage=Decimal('0.00'),
            late_minutes=minutes_late if status in ('LATE', 'ABSENT') else 0,
            early_leave_minutes=early_leave if status == 'EARLY_LEAVE' else 0,
            break_minutes=break_minutes,
            lunch_minutes=lunch_minutes,
            missing_minutes=missing_minutes,
            overtime_minutes=overtime,
            night_minutes=night_minutes if shift and shift.is_overnight else 0,
            weekend_minutes=net_worked if calc.is_weekend else 0,
            holiday_minutes=net_worked if calc.is_holiday else 0,
            is_weekend=calc.is_weekend,
            is_holiday=calc.is_holiday,
            is_night_shift=shift.is_overnight if shift else False,
            on_leave=calc.on_leave,
            leave_type=calc.leave_type,
            leave_is_paid=calc.leave_is_paid,
        )

        if calc.expected_minutes > 0:
            pct = (Decimal(calc.worked_minutes) / Decimal(calc.expected_minutes) * 100).quantize(TWOPLACES)
            calc = replace(calc, attendance_percentage=min(pct, Decimal('100.00')))

        return calc

    def _aggregate_month(self, daily_summaries) -> MonthAggregation:
        agg = MonthAggregation()
        total_expected_minutes = 0
        total_worked_minutes = 0

        for ds in daily_summaries:
            agg.worked_hours += minutes_to_hours(ds.worked_minutes)
            agg.late_minutes += ds.late_minutes
            agg.overtime_hours += minutes_to_hours(ds.overtime_minutes)
            agg.night_hours += minutes_to_hours(ds.night_minutes)
            agg.weekend_hours += minutes_to_hours(ds.weekend_minutes)
            agg.holiday_hours += minutes_to_hours(ds.holiday_minutes)

            if ds.on_leave:
                if ds.leave_is_paid:
                    agg.paid_leave_days += 1
                    agg.paid_leave_hours += minutes_to_hours(ds.expected_minutes)
                    agg.approved_leave_hours += minutes_to_hours(ds.expected_minutes)
                else:
                    agg.unpaid_leave_days += 1
                    agg.unpaid_leave_hours += minutes_to_hours(ds.expected_minutes)
                continue

            if ds.is_holiday:
                agg.holiday_hours += minutes_to_hours(ds.worked_minutes)
                continue

            if ds.is_weekend:
                agg.weekend_hours += minutes_to_hours(ds.worked_minutes)
                if ds.worked_minutes > 0:
                    agg.present_days += 1
                continue

            if ds.worked_minutes == 0 and ds.expected_minutes > 0:
                agg.absent_days += 1
                continue

            if ds.worked_minutes > 0:
                agg.present_days += 1

            total_expected_minutes += ds.expected_minutes
            total_worked_minutes += ds.worked_minutes

        agg.expected_hours = minutes_to_hours(total_expected_minutes)
        agg.worked_hours = minutes_to_hours(total_worked_minutes)

        if agg.expected_hours > 0:
            agg.attendance_percentage = (
                (agg.worked_hours / agg.expected_hours * 100).quantize(TWOPLACES)
            )
        else:
            agg.attendance_percentage = Decimal('0.00')

        agg.missing_hours = minutes_to_hours(
            sum(ds.missing_minutes for ds in daily_summaries)
        )

        return agg

    # ---------------------------------------------------------------------
    # PERSISTENCE
    # ---------------------------------------------------------------------

    @transaction.atomic
    def _persist_daily_summary(
        self,
        employee: Employee,
        work_date: date,
        calc: DayCalculation,
        schedule: Optional[EmployeeSchedule],
        logs: list[AttendanceLog],
    ) -> DailyTimeSummary:
        ar = None
        if logs:
            ar = AttendanceRecord.objects.filter(employee=employee, date=work_date).first()

        ds, created = DailyTimeSummary.objects.update_or_create(
            employee=employee,
            date=work_date,
            defaults={
                'attendance_record': ar,
                'worked_minutes': calc.worked_minutes,
                'expected_minutes': calc.expected_minutes,
                'attendance_percentage': calc.attendance_percentage,
                'late_minutes': calc.late_minutes,
                'early_leave_minutes': calc.early_leave_minutes,
                'break_minutes': calc.break_minutes,
                'lunch_minutes': calc.lunch_minutes,
                'missing_minutes': calc.missing_minutes,
                'overtime_minutes': calc.overtime_minutes,
                'night_minutes': calc.night_minutes,
                'weekend_minutes': calc.weekend_minutes,
                'holiday_minutes': calc.holiday_minutes,
                'is_weekend': calc.is_weekend,
                'is_holiday': calc.is_holiday,
                'is_night_shift': calc.is_night_shift,
                'on_leave': calc.on_leave,
                'leave_type': calc.leave_type,
                'leave_is_paid': calc.leave_is_paid,
            },
        )

        if not created:
            ds.recalculation_count += 1
            ds.last_recalculated_at = timezone.now()
            ds.save(update_fields=['recalculation_count', 'last_recalculated_at'])

        return ds

    def _persist_monthly_summary(
        self,
        employee: Employee,
        year: int,
        month: int,
        agg: MonthAggregation,
        daily_count: int,
    ) -> MonthlyTimeSummary:
        monthly, created = MonthlyTimeSummary.objects.update_or_create(
            employee=employee,
            year=year,
            month=month,
            defaults={
                'expected_hours': agg.expected_hours,
                'worked_hours': agg.worked_hours,
                'attendance_percentage': agg.attendance_percentage,
                'late_minutes': agg.late_minutes,
                'missing_hours': agg.missing_hours,
                'overtime_hours': agg.overtime_hours,
                'holiday_hours': agg.holiday_hours,
                'weekend_hours': agg.weekend_hours,
                'night_hours': agg.night_hours,
                'approved_leave_hours': agg.approved_leave_hours,
                'unpaid_leave_hours': agg.unpaid_leave_hours,
                'paid_leave_hours': agg.paid_leave_hours,
                'present_days': agg.present_days,
                'absent_days': agg.absent_days,
                'paid_leave_days': agg.paid_leave_days,
                'unpaid_leave_days': agg.unpaid_leave_days,
            },
        )

        if not created:
            monthly.recalculation_count += 1
            monthly.last_recalculated_at = timezone.now()
            monthly.save(update_fields=['recalculation_count', 'last_recalculated_at'])

        return monthly

    def _build_daily_summary_instance(
        self,
        employee: Employee,
        work_date: date,
        calc: DayCalculation,
        schedule: Optional[EmployeeSchedule],
    ) -> DailyTimeSummary:
        ar = AttendanceRecord.objects.filter(employee=employee, date=work_date).first()
        return DailyTimeSummary(
            employee=employee,
            date=work_date,
            attendance_record=ar,
            worked_minutes=calc.worked_minutes,
            expected_minutes=calc.expected_minutes,
            attendance_percentage=calc.attendance_percentage,
            late_minutes=calc.late_minutes,
            early_leave_minutes=calc.early_leave_minutes,
            break_minutes=calc.break_minutes,
            lunch_minutes=calc.lunch_minutes,
            missing_minutes=calc.missing_minutes,
            overtime_minutes=calc.overtime_minutes,
            night_minutes=calc.night_minutes,
            weekend_minutes=calc.weekend_minutes,
            holiday_minutes=calc.holiday_minutes,
            is_weekend=calc.is_weekend,
            is_holiday=calc.is_holiday,
            is_night_shift=calc.is_night_shift,
            on_leave=calc.on_leave,
            leave_type=calc.leave_type,
            leave_is_paid=calc.leave_is_paid,
        )

    def _build_monthly_summary_instance(
        self,
        employee: Employee,
        year: int,
        month: int,
        agg: MonthAggregation,
    ) -> MonthlyTimeSummary:
        return MonthlyTimeSummary(
            employee=employee,
            year=year,
            month=month,
            expected_hours=agg.expected_hours,
            worked_hours=agg.worked_hours,
            attendance_percentage=agg.attendance_percentage,
            late_minutes=agg.late_minutes,
            missing_hours=agg.missing_hours,
            overtime_hours=agg.overtime_hours,
            holiday_hours=agg.holiday_hours,
            weekend_hours=agg.weekend_hours,
            night_hours=agg.night_hours,
            approved_leave_hours=agg.approved_leave_hours,
            unpaid_leave_hours=agg.unpaid_leave_hours,
            paid_leave_hours=agg.paid_leave_hours,
            present_days=agg.present_days,
            absent_days=agg.absent_days,
            paid_leave_days=agg.paid_leave_days,
            unpaid_leave_days=agg.unpaid_leave_days,
        )

    # ---------------------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------------------

    def _get_schedule(self, employee: Employee, work_date: date) -> Optional[EmployeeSchedule]:
        return (
            EmployeeSchedule.objects.select_related('shift', 'department')
            .filter(employee=employee, effective_start__lte=work_date)
            .filter(Q(effective_end__isnull=True) | Q(effective_end__gte=work_date))
            .order_by('-effective_start')
            .first()
        )

    def _get_holiday(self, employee: Employee, work_date: date) -> Optional[Holiday]:
        return (
            Holiday.objects.filter(date=work_date)
            .filter(Q(department__isnull=True) | Q(department=employee.department))
            .filter(Q(office_location__isnull=True) | Q(office_location=employee.office_location))
            .first()
        )

    def _get_leave(self, employee: Employee, work_date: date) -> Optional[LeaveRequest]:
        return (
            LeaveRequest.objects.filter(
                employee=employee,
                status=LeaveRequest.Status.APPROVED,
                start_date__lte=work_date,
                end_date__gte=work_date,
            )
            .order_by('-created_at')
            .first()
        )

    def _shift_window(self, work_date: date, schedule: EmployeeSchedule) -> tuple[datetime, datetime]:
        shift = schedule.shift
        start_time = schedule.flexible_start_time if schedule.is_flexible and schedule.flexible_start_time else shift.start_time
        end_time = schedule.flexible_end_time if schedule.is_flexible and schedule.flexible_end_time else shift.end_time
        start_dt = timezone.make_aware(datetime.combine(work_date, start_time))
        end_dt = timezone.make_aware(datetime.combine(work_date, end_time))
        if shift.is_overnight or end_dt <= start_dt:
            end_dt += timedelta(days=1)
        return start_dt, end_dt

    def _expected_minutes(self, schedule: EmployeeSchedule, work_date: date) -> int:
        start_dt, end_dt = self._shift_window(work_date, schedule)
        return max(0, int((end_dt - start_dt).total_seconds() // 60))

    @staticmethod
    def _first_check_in(logs: list[AttendanceLog]) -> Optional[datetime]:
        for log in logs:
            if log.scan_type == 'IN':
                return log.timestamp
        return None

    @staticmethod
    def _last_check_out(logs: list[AttendanceLog]) -> Optional[datetime]:
        outs = [log.timestamp for log in logs if log.scan_type == 'OUT']
        return outs[-1] if outs else None

    @staticmethod
    def _worked_minutes(check_in: Optional[datetime], check_out: Optional[datetime]) -> int:
        if not check_in or not check_out:
            return 0
        return max(0, int((check_out - check_in).total_seconds() // 60))

    def _sum_breaks(self, logs: list[AttendanceLog], break_type: str) -> int:
        total = 0
        start = None
        for log in logs:
            if log.event_type == f'{break_type}_START':
                start = log.timestamp
            elif log.event_type == f'{break_type}_END' and start:
                total += int((log.timestamp - start).total_seconds() // 60)
                start = None
        return total

    def _calculate_night_minutes(self, check_in: datetime, check_out: datetime) -> int:
        if not check_in or not check_out:
            return 0
        night_start = timezone.make_aware(datetime.combine(check_in.date(), self.NIGHT_START))
        night_end = timezone.make_aware(datetime.combine(check_out.date(), self.NIGHT_END))
        if night_end <= night_start:
            night_end += timedelta(days=1)

        overlap_start = max(check_in, night_start)
        overlap_end = min(check_out, night_end)
        if overlap_end > overlap_start:
            return int((overlap_end - overlap_start).total_seconds() // 60)
        return 0

    def _is_leave_paid(self, leave_type: str) -> bool:
        if leave_type in self.leave_impact_lookup:
            return bool(self.leave_impact_lookup[leave_type].get('is_paid', True))
        if leave_type in self.UNPAID_LEAVE_TYPES:
            return False
        return leave_type in self.PAID_LEAVE_TYPES

    # ---------------------------------------------------------------------
    # BULK OPERATIONS
    # ---------------------------------------------------------------------

    def calculate_all_employees_day(self, work_date: date = None) -> list[DailyTimeSummary]:
        work_date = work_date or timezone.localdate()
        employees = Employee.objects.filter(employment_status=Employee.EmploymentStatus.ACTIVE)
        results = []
        for emp in employees:
            try:
                ds = self.calculate_daily_summary(emp, work_date, persist=True)
                results.append(ds)
            except Exception:
                continue
        return results

    def calculate_all_employees_month(self, year: int, month: int) -> list[MonthlyTimeSummary]:
        employees = Employee.objects.filter(employment_status=Employee.EmploymentStatus.ACTIVE)
        results = []
        for emp in employees:
            try:
                ms = self.calculate_monthly_summary(emp, year, month, persist=True)
                results.append(ms)
            except Exception:
                continue
        return results

    @staticmethod
    def get_dashboard_stats(employee: Employee, work_date: date = None) -> dict:
        work_date = work_date or timezone.localdate()
        week_start = work_date - timedelta(days=work_date.weekday())
        month_start = work_date.replace(day=1)

        today_ds = DailyTimeSummary.objects.filter(employee=employee, date=work_date).first()
        week_ds = DailyTimeSummary.objects.filter(
            employee=employee, date__gte=week_start, date__lte=work_date
        )
        month_ds = DailyTimeSummary.objects.filter(
            employee=employee, date__gte=month_start, date__lte=work_date
        )

        def agg(qs):
            return qs.aggregate(
                worked=Sum('worked_minutes'),
                expected=Sum('expected_minutes'),
                late=Sum('late_minutes'),
                early=Sum('early_leave_minutes'),
                overtime=Sum('overtime_minutes'),
                missing=Sum('missing_minutes'),
            )

        today = agg(DailyTimeSummary.objects.filter(employee=employee, date=work_date))
        week = agg(week_ds)
        month = agg(month_ds)

        return {
            'today': {
                'worked_hours': minutes_to_hours(today['worked'] or 0),
                'expected_hours': minutes_to_hours(today['expected'] or 0),
                'late_minutes': today['late'] or 0,
                'early_leave_minutes': today['early'] or 0,
                'overtime_hours': minutes_to_hours(today['overtime'] or 0),
                'missing_hours': minutes_to_hours(today['missing'] or 0),
            },
            'week': {
                'worked_hours': minutes_to_hours(week['worked'] or 0),
                'expected_hours': minutes_to_hours(week['expected'] or 0),
                'late_minutes': week['late'] or 0,
                'early_leave_minutes': week['early'] or 0,
                'overtime_hours': minutes_to_hours(week['overtime'] or 0),
            },
            'month': {
                'worked_hours': minutes_to_hours(month['worked'] or 0),
                'expected_hours': minutes_to_hours(month['expected'] or 0),
                'late_minutes': month['late'] or 0,
                'early_leave_minutes': month['early'] or 0,
                'overtime_hours': minutes_to_hours(month['overtime'] or 0),
            },
        }