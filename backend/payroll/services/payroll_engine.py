from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.db.models import Q as DQ
from django.utils import timezone

from attendance.models import Employee
from payroll.models import (
    Allowance,
    AttendanceDeductionPolicy,
    Bonus,
    Deduction,
    LeavePayrollImpact,
    OvertimeRecord,
    OvertimeRuleSet,
    Payroll,
    PayrollItem,
    PayrollPeriod,
    SalaryProfile,
)
from payroll.services.audit import log_payroll_action
from payroll.services.tax_engine import TaxEngine
from payroll.services.time_tracking import TimeTrackingEngine, minutes_to_hours


TWOPLACES = Decimal('0.01')
ZERO = Decimal('0.00')


class PayrollEngineError(Exception):
    pass


class PayrollEngine:
    def __init__(self):
        self.tax_engine = TaxEngine()

    def calculate_period(self, period, employees=None, actor=None, request=None, replace_existing=True):
        if period.status in {PayrollPeriod.Status.LOCKED, PayrollPeriod.Status.PAID}:
            raise PayrollEngineError('Cannot recalculate a locked or paid payroll period.')

        period.status = PayrollPeriod.Status.PROCESSING
        period.save(update_fields=['status', 'updated_at'])

        qs = employees or Employee.objects.filter(employment_status=Employee.EmploymentStatus.ACTIVE)
        if hasattr(qs, 'select_related'):
            qs = qs.select_related('department', 'salary_profile')

        leave_lookup = self._leave_impact_lookup()
        results = []
        for employee in qs:
            try:
                payroll = self.calculate_employee(
                    period=period, employee=employee,
                    leave_lookup=leave_lookup, actor=actor, request=request,
                    replace_existing=replace_existing,
                )
                if payroll:
                    results.append(payroll)
            except SalaryProfile.DoesNotExist:
                continue

        period.status = PayrollPeriod.Status.DRAFT
        period.save(update_fields=['status', 'updated_at'])
        log_payroll_action(
            action='CALCULATE',
            summary=f'Calculated payroll for {len(results)} employees in {period}',
            actor=actor, entity_type='PayrollPeriod', entity_id=period.pk,
            period=period, request=request,
            after_data={'count': len(results)},
        )
        return results

    @transaction.atomic
    def calculate_employee(self, period, employee, leave_lookup=None, actor=None, request=None, replace_existing=True):
        try:
            profile = employee.salary_profile
        except SalaryProfile.DoesNotExist:
            return None
        if not profile.is_active:
            return None

        existing = Payroll.objects.filter(period=period, employee=employee).first()
        if existing and not existing.is_modifiable:
            return existing
        if existing and replace_existing:
            existing.items.all().delete()
            OvertimeRecord.objects.filter(period=period, employee=employee).delete()
            payroll = existing
        else:
            payroll = Payroll(period=period, employee=employee)

        leave_lookup = leave_lookup or self._leave_impact_lookup()
        time_engine = TimeTrackingEngine(leave_impact_lookup=leave_lookup)
        time_summary = time_engine.summarize_period(
            employee=employee,
            start_date=period.start_date,
            end_date=period.end_date,
            expected_daily_hours=profile.expected_daily_hours,
            expected_monthly_hours=profile.expected_monthly_hours,
        )

        hourly_rate = self._resolve_hourly_rate(profile)
        daily_rate = self._resolve_daily_rate(profile, hourly_rate)
        basic_salary = self._resolve_basic(profile)
        attendance_salary = self._calculate_attendance_salary(basic_salary, time_summary)

        items = []
        sort_order = 0

        def add_item(**kwargs):
            nonlocal sort_order
            sort_order += 10
            items.append(PayrollItem(sort_order=sort_order, **kwargs))

        add_item(
            item_type=PayrollItem.ItemType.BASIC,
            direction=PayrollItem.Direction.EARNING,
            code='BASIC',
            description='Basic Salary',
            quantity=Decimal('1'),
            rate=basic_salary,
            amount=basic_salary,
            is_taxable=True,
        )

        if attendance_salary != basic_salary:
            add_item(
                item_type=PayrollItem.ItemType.BASIC,
                direction=PayrollItem.Direction.EARNING,
                code='ATTENDANCE_ADJ',
                description=f'Attendance Adjustment ({time_summary.worked_hours}h / {time_summary.expected_hours}h)',
                quantity=Decimal('1'),
                rate=attendance_salary - basic_salary,
                amount=attendance_salary - basic_salary,
                is_taxable=True,
            )

        total_allowances = ZERO
        for code, label, amount in [
            ('TRANSPORT', 'Transport Allowance', profile.transport_allowance),
            ('HOUSING', 'Housing Allowance', profile.housing_allowance),
            ('COMMUNICATION', 'Communication Allowance', profile.communication_allowance),
            ('MEAL', 'Meal Allowance', profile.meal_allowance),
            ('OTHER', 'Other Allowances', profile.other_allowances),
        ]:
            if amount and amount > 0:
                total_allowances += amount
                add_item(
                    item_type=PayrollItem.ItemType.ALLOWANCE,
                    direction=PayrollItem.Direction.EARNING,
                    code=code, description=label,
                    amount=amount, rate=amount, is_taxable=True,
                )

        for allowance in Allowance.objects.filter(employee=employee).filter(
            DQ(period=period)
            | DQ(is_recurring=True, period__isnull=True)
            | (DQ(period__isnull=True, effective_from__lte=period.end_date)
               & (DQ(effective_to__isnull=True) | DQ(effective_to__gte=period.start_date)))
        ):
            total_allowances += allowance.amount
            add_item(
                item_type=PayrollItem.ItemType.ALLOWANCE,
                direction=PayrollItem.Direction.EARNING,
                code=allowance.allowance_type, description=allowance.name,
                amount=allowance.amount, rate=allowance.amount,
                is_taxable=allowance.is_taxable, reference_id=allowance.pk,
            )

        total_bonuses = ZERO
        if profile.bonus_eligible:
            bonuses = Bonus.objects.filter(
                employee=employee, status=Bonus.Status.APPROVED,
            ).filter(
                DQ(period=period)
                | DQ(period__isnull=True, bonus_date__gte=period.start_date, bonus_date__lte=period.end_date)
            )
            for bonus in bonuses:
                total_bonuses += bonus.amount
                add_item(
                    item_type=PayrollItem.ItemType.BONUS,
                    direction=PayrollItem.Direction.EARNING,
                    code=bonus.bonus_type,
                    description=f'{bonus.get_bonus_type_display()}: {bonus.reason}',
                    amount=bonus.amount, rate=bonus.amount,
                    is_taxable=bonus.is_taxable, reference_id=bonus.pk,
                )

        ot_amount, ot_hours = self._calculate_overtime(
            period, employee, profile, time_summary, hourly_rate, add_item,
        )

        attendance_deduction = ZERO
        if profile.apply_attendance_deductions:
            attendance_deduction = self._calculate_attendance_deductions(
                profile, time_summary, hourly_rate, daily_rate, add_item,
            )

        total_company_deductions = ZERO
        total_penalties = ZERO
        deductions = Deduction.objects.filter(
            employee=employee,
            status__in=[Deduction.Status.APPROVED, Deduction.Status.APPLIED],
        ).filter(
            DQ(period=period)
            | DQ(period__isnull=True,
                 deduction_date__gte=period.start_date,
                 deduction_date__lte=period.end_date)
        )
        for ded in deductions:
            total_company_deductions += ded.amount
            item_type = (
                PayrollItem.ItemType.PENALTY
                if ded.deduction_type in {
                    Deduction.DeductionType.DISCIPLINARY,
                    Deduction.DeductionType.LATE_ARRIVAL,
                    Deduction.DeductionType.UNAUTHORIZED_ABSENCE,
                }
                else PayrollItem.ItemType.COMPANY_DEDUCTION
            )
            if item_type == PayrollItem.ItemType.PENALTY:
                total_penalties += ded.amount
            add_item(
                item_type=item_type,
                direction=PayrollItem.Direction.DEDUCTION,
                code=ded.deduction_type,
                description=f'{ded.get_deduction_type_display()}: {ded.reason}',
                amount=ded.amount, rate=ded.amount, reference_id=ded.pk,
            )

        unpaid_leave_deduction = ZERO
        policy = self._resolve_deduction_policy(profile)
        if policy and policy.unpaid_leave_deducts and time_summary.unpaid_leave_days > 0:
            unpaid_leave_deduction = (daily_rate * time_summary.unpaid_leave_days).quantize(TWOPLACES)
            if unpaid_leave_deduction > 0:
                attendance_deduction += unpaid_leave_deduction
                add_item(
                    item_type=PayrollItem.ItemType.ATTENDANCE_DEDUCTION,
                    direction=PayrollItem.Direction.DEDUCTION,
                    code='UNPAID_LEAVE',
                    description=f'Unpaid leave ({time_summary.unpaid_leave_days} days)',
                    quantity=time_summary.unpaid_leave_days,
                    rate=daily_rate, amount=unpaid_leave_deduction,
                )

        attendance_salary_field = attendance_salary.quantize(TWOPLACES)
        gross = (attendance_salary_field + total_allowances + total_bonuses + ot_amount).quantize(TWOPLACES)
        taxable = sum(
            (i.amount for i in items if i.direction == PayrollItem.Direction.EARNING and i.is_taxable),
            ZERO,
        ).quantize(TWOPLACES)

        tax_exempt = profile.tax_category == SalaryProfile.TaxCategory.EXEMPT
        tax_rule = profile.tax_rule_set or period.tax_rule_set
        tax_result = self.tax_engine.compute(
            taxable_income=taxable,
            basic_salary=attendance_salary_field,
            gross_salary=gross,
            rule_set=tax_rule,
            tax_exempt=tax_exempt,
            pension_eligible=profile.pension_eligible,
        )

        if tax_result.income_tax > 0:
            add_item(
                item_type=PayrollItem.ItemType.TAX,
                direction=PayrollItem.Direction.DEDUCTION,
                code='INCOME_TAX',
                description=f'Income Tax ({tax_result.bracket_label})',
                amount=tax_result.income_tax, rate=tax_result.income_tax,
            )
        for contrib in tax_result.employee_contributions:
            item_type = (
                PayrollItem.ItemType.PENSION_EMPLOYEE
                if 'PENSION' in contrib.contribution_type
                else PayrollItem.ItemType.GOVERNMENT
            )
            add_item(
                item_type=item_type,
                direction=PayrollItem.Direction.DEDUCTION,
                code=contrib.contribution_type,
                description=contrib.name,
                amount=contrib.amount, rate=contrib.amount,
            )
        for contrib in tax_result.employer_contributions:
            item_type = (
                PayrollItem.ItemType.PENSION_EMPLOYER
                if 'PENSION' in contrib.contribution_type
                else PayrollItem.ItemType.GOVERNMENT
            )
            add_item(
                item_type=item_type,
                direction=PayrollItem.Direction.EMPLOYER,
                code=contrib.contribution_type,
                description=contrib.name,
                amount=contrib.amount, rate=contrib.amount,
            )

        total_gov = (
            tax_result.income_tax + tax_result.pension_employee + tax_result.other_government
        ).quantize(TWOPLACES)
        for contrib in tax_result.employee_contributions:
            if 'PENSION' not in contrib.contribution_type and contrib.contribution_type != 'OTHER_GOVERNMENT':
                total_gov += contrib.amount
        total_gov = total_gov.quantize(TWOPLACES)

        net = (gross - total_gov - total_company_deductions - attendance_deduction).quantize(TWOPLACES)
        if net < 0:
            net = ZERO

        payroll.salary_profile = profile
        payroll.status = Payroll.Status.DRAFT
        payroll.currency = profile.currency
        payroll.basic_salary = attendance_salary_field
        payroll.total_allowances = total_allowances
        payroll.total_bonuses = total_bonuses
        payroll.total_overtime = ot_amount
        payroll.gross_salary = gross
        payroll.taxable_income = taxable
        payroll.income_tax = tax_result.income_tax
        payroll.pension_employee = tax_result.pension_employee
        payroll.pension_employer = tax_result.pension_employer
        payroll.other_government_deductions = tax_result.other_government
        payroll.total_government_deductions = total_gov
        payroll.total_company_deductions = total_company_deductions
        payroll.total_penalties = total_penalties
        payroll.attendance_deductions = attendance_deduction
        payroll.net_salary = net
        payroll.expected_hours = time_summary.expected_hours
        payroll.worked_hours = time_summary.worked_hours
        payroll.missing_hours = time_summary.missing_hours
        payroll.overtime_hours = ot_hours
        payroll.late_minutes = time_summary.late_minutes
        payroll.early_leave_minutes = time_summary.early_leave_minutes
        payroll.absent_days = time_summary.absent_days
        payroll.unpaid_leave_days = time_summary.unpaid_leave_days
        payroll.paid_leave_days = time_summary.paid_leave_days
        payroll.holiday_days = time_summary.holiday_days
        payroll.present_days = time_summary.present_days
        payroll.payment_method = profile.payment_method
        payroll.bank_account_number = profile.bank_account_number
        payroll.calculation_notes = (
            f'Time: worked={time_summary.worked_hours}h expected={time_summary.expected_hours}h '
            f'missing={time_summary.missing_hours}h OT={ot_hours}h '
            f'attendance_salary={attendance_salary_field}'
        )
        payroll.calculated_at = timezone.now()
        payroll.save()

        for item in items:
            item.payroll = payroll
        PayrollItem.objects.bulk_create(items)

        log_payroll_action(
            action='CALCULATE',
            summary=f'Calculated payroll for {employee} net={net}',
            actor=actor, entity_type='Payroll', entity_id=payroll.pk,
            period=period, payroll=payroll, request=request,
            after_data={'gross': str(gross), 'net': str(net), 'attendance_salary': str(attendance_salary_field)},
        )
        return payroll

    def _resolve_basic(self, profile):
        if profile.basic_salary > 0:
            return profile.basic_salary
        if profile.monthly_salary > 0:
            return profile.monthly_salary
        return profile.gross_salary

    def _calculate_attendance_salary(self, basic_salary, time_summary):
        if time_summary.expected_hours <= 0:
            return basic_salary.quantize(TWOPLACES)
        ratio = (time_summary.worked_hours / time_summary.expected_hours)
        return (basic_salary * ratio).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def _resolve_hourly_rate(self, profile):
        if profile.hourly_rate and profile.hourly_rate > 0:
            return profile.hourly_rate
        expected = profile.expected_monthly_hours or Decimal('160')
        if expected <= 0:
            expected = Decimal('160')
        basic = self._resolve_basic(profile)
        return (basic / expected).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    def _resolve_daily_rate(self, profile, hourly_rate):
        if profile.daily_rate and profile.daily_rate > 0:
            return profile.daily_rate
        return (hourly_rate * profile.expected_daily_hours).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def _resolve_ot_rules(self, profile, period):
        return (
            profile.overtime_rule_set
            or period.overtime_rule_set
            or OvertimeRuleSet.objects.filter(is_active=True, is_default=True).first()
            or OvertimeRuleSet.objects.filter(is_active=True).first()
        )

    def _resolve_deduction_policy(self, profile):
        return (
            profile.attendance_deduction_policy
            or AttendanceDeductionPolicy.objects.filter(is_active=True, is_default=True).first()
            or AttendanceDeductionPolicy.objects.filter(is_active=True).first()
        )

    def _multiplier(self, rule_set, ot_type, default):
        if not rule_set:
            return default
        rule = rule_set.rules.filter(overtime_type=ot_type, is_active=True).first()
        return rule.multiplier if rule else default

    def _calculate_overtime(self, period, employee, profile, time_summary, hourly_rate, add_item):
        if not profile.overtime_eligible:
            return ZERO, ZERO

        rule_set = self._resolve_ot_rules(profile, period)
        buckets = [
            ('WEEKDAY', time_summary.weekday_ot_minutes, Decimal('1.50')),
            ('WEEKEND', time_summary.weekend_ot_minutes, Decimal('2.00')),
            ('HOLIDAY', time_summary.holiday_ot_minutes, Decimal('2.50')),
            ('NIGHT', time_summary.night_ot_minutes, Decimal('1.75')),
        ]
        total_amount = ZERO
        total_hours = ZERO
        ot_records = []

        for ot_type, minutes, default_mult in buckets:
            if minutes <= 0:
                continue
            hours = minutes_to_hours(minutes)
            multiplier = self._multiplier(rule_set, ot_type, default_mult)
            amount = (hourly_rate * hours * multiplier).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            total_amount += amount
            total_hours += hours
            ot_records.append(
                OvertimeRecord(
                    employee=employee, period=period, work_date=period.end_date,
                    overtime_type=ot_type, minutes=minutes, multiplier=multiplier,
                    hourly_rate=hourly_rate, amount=amount,
                    notes=f'Aggregated {ot_type} OT for period',
                )
            )
            add_item(
                item_type=PayrollItem.ItemType.OVERTIME,
                direction=PayrollItem.Direction.EARNING,
                code=f'OT_{ot_type}',
                description=f'{ot_type.title()} Overtime ({hours}h × {multiplier})',
                quantity=hours, rate=hourly_rate * multiplier,
                amount=amount, is_taxable=True,
            )

        if ot_records:
            OvertimeRecord.objects.bulk_create(ot_records)
        return total_amount, total_hours.quantize(TWOPLACES)

    def _calculate_attendance_deductions(self, profile, time_summary, hourly_rate, daily_rate, add_item):
        policy = self._resolve_deduction_policy(profile)
        if not policy:
            if time_summary.missing_hours <= 0:
                return ZERO
            amount = (hourly_rate * time_summary.missing_hours).quantize(TWOPLACES)
            add_item(
                item_type=PayrollItem.ItemType.ATTENDANCE_DEDUCTION,
                direction=PayrollItem.Direction.DEDUCTION,
                code='MISSING_HOURS',
                description=f'Missing hours ({time_summary.missing_hours}h)',
                quantity=time_summary.missing_hours, rate=hourly_rate, amount=amount,
            )
            return amount

        total = ZERO
        rate = hourly_rate
        if policy.missing_hour_rate_source == 'GROSS_DIV_EXPECTED':
            expected = profile.expected_monthly_hours or Decimal('160')
            rate = (profile.gross_salary / expected) if expected else hourly_rate
        elif policy.missing_hour_rate_source == 'HOURLY_RATE':
            rate = hourly_rate

        grace_hours = minutes_to_hours(policy.grace_missing_minutes)
        missing = max(ZERO, time_summary.missing_hours - grace_hours)

        if policy.deduct_missing_hours and missing > 0:
            amount = (rate * missing).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            total += amount
            add_item(
                item_type=PayrollItem.ItemType.ATTENDANCE_DEDUCTION,
                direction=PayrollItem.Direction.DEDUCTION,
                code='MISSING_HOURS',
                description=f'Missing hours ({missing}h)',
                quantity=missing, rate=rate, amount=amount,
            )

        if policy.late_deduction_per_minute > 0 and time_summary.late_minutes > 0:
            amount = (policy.late_deduction_per_minute * time_summary.late_minutes).quantize(TWOPLACES)
            total += amount
            add_item(
                item_type=PayrollItem.ItemType.ATTENDANCE_DEDUCTION,
                direction=PayrollItem.Direction.DEDUCTION,
                code='LATE',
                description=f'Late arrival ({time_summary.late_minutes} min)',
                quantity=Decimal(time_summary.late_minutes),
                rate=policy.late_deduction_per_minute, amount=amount,
            )

        if policy.early_leave_deduction_per_minute > 0 and time_summary.early_leave_minutes > 0:
            amount = (policy.early_leave_deduction_per_minute * time_summary.early_leave_minutes).quantize(TWOPLACES)
            total += amount
            add_item(
                item_type=PayrollItem.ItemType.ATTENDANCE_DEDUCTION,
                direction=PayrollItem.Direction.DEDUCTION,
                code='EARLY_LEAVE',
                description=f'Early leave ({time_summary.early_leave_minutes} min)',
                quantity=Decimal(time_summary.early_leave_minutes),
                rate=policy.early_leave_deduction_per_minute, amount=amount,
            )

        if time_summary.absent_days > 0 and policy.absent_day_deduction_rate > 0:
            amount = (daily_rate * time_summary.absent_days * policy.absent_day_deduction_rate).quantize(TWOPLACES)
            total += amount
            add_item(
                item_type=PayrollItem.ItemType.ATTENDANCE_DEDUCTION,
                direction=PayrollItem.Direction.DEDUCTION,
                code='ABSENCE',
                description=f'Unauthorized absence ({time_summary.absent_days} days)',
                quantity=time_summary.absent_days,
                rate=daily_rate * policy.absent_day_deduction_rate, amount=amount,
            )

        return total

    @staticmethod
    def _leave_impact_lookup():
        return {
            row.leave_type: {'is_paid': row.is_paid, 'pay_percentage': row.pay_percentage}
            for row in LeavePayrollImpact.objects.all()
        }
