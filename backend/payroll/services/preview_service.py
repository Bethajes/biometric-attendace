"""
Payroll Preview Service.

Provides live calculation preview without persisting to database.
Used by the salary form live preview panel and AJAX endpoint.
"""

from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field, asdict
from typing import Optional

from payroll.models import (
    TaxRuleSet,
    TaxBracket,
    ContributionRule,
    OvertimeRuleSet,
    OvertimeRule,
    AttendanceDeductionPolicy,
    LeavePayrollImpact,
)
from payroll.services.tax_engine import TaxEngine


TWOPLACES = Decimal('0.01')
ZERO = Decimal('0.00')


@dataclass
class PayrollPreviewResult:
    basic_salary: Decimal = ZERO
    attendance_salary: Decimal = ZERO
    worked_hours: Decimal = ZERO
    expected_hours: Decimal = ZERO
    attendance_percent: Decimal = ZERO
    hourly_rate: Decimal = ZERO
    daily_rate: Decimal = ZERO
    overtime_hours: Decimal = ZERO
    overtime_amount: Decimal = ZERO
    total_bonuses: Decimal = ZERO
    total_allowances: Decimal = ZERO
    gross_salary: Decimal = ZERO
    income_tax: Decimal = ZERO
    pension_employee: Decimal = ZERO
    pension_employer: Decimal = ZERO
    other_government_deductions: Decimal = ZERO
    total_government_deductions: Decimal = ZERO
    total_company_deductions: Decimal = ZERO
    attendance_deductions: Decimal = ZERO
    net_salary: Decimal = ZERO
    currency: str = 'ETB'
    bracket_label: str = ''
    missing_hours: Decimal = ZERO


class PayrollPreviewService:
    """Computes a full payroll preview in memory (no DB writes)."""

    def __init__(self):
        self.tax_engine = TaxEngine()

    def preview(
        self,
        basic_salary: Decimal,
        worked_hours: Decimal,
        expected_hours: Decimal,
        hourly_rate: Optional[Decimal] = None,
        daily_rate: Optional[Decimal] = None,
        overtime_hours: Decimal = ZERO,
        overtime_multiplier: Decimal = Decimal('1.50'),
        total_bonuses: Decimal = ZERO,
        total_allowances: Decimal = ZERO,
        total_company_deductions: Decimal = ZERO,
        attendance_deductions: Decimal = ZERO,
        currency: str = 'ETB',
        tax_rule_set_id: Optional[int] = None,
        overtime_rule_set_id: Optional[int] = None,
        pension_eligible: bool = True,
        tax_exempt: bool = False,
    ) -> PayrollPreviewResult:
        expected = expected_hours if expected_hours > 0 else Decimal('160')
        hr = hourly_rate or ZERO
        dr = daily_rate or ZERO

        if hr <= 0 and basic_salary > 0 and expected > 0:
            hr = (basic_salary / expected).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        if dr <= 0 and hr > 0:
            dr = (hr * Decimal('8')).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        attendance_pct = ZERO
        attendance_salary = basic_salary
        if expected > 0:
            attendance_pct = (worked_hours / expected * Decimal('100')).quantize(TWOPLACES)
            attendance_salary = (basic_salary * worked_hours / expected).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        ot_amount = ZERO
        if overtime_hours > 0 and hr > 0:
            ot_amount = (overtime_hours * hr * overtime_multiplier).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        gross = (attendance_salary + total_allowances + total_bonuses + ot_amount).quantize(TWOPLACES)
        taxable = (attendance_salary + total_allowances + total_bonuses + ot_amount).quantize(TWOPLACES)

        tax_result = self.tax_engine.compute(
            taxable_income=taxable,
            basic_salary=attendance_salary,
            gross_salary=gross,
            rule_set_id=tax_rule_set_id,
            tax_exempt=tax_exempt,
            pension_eligible=pension_eligible,
        )

        total_gov = (tax_result.income_tax + tax_result.pension_employee + tax_result.other_government).quantize(TWOPLACES)
        net = (gross - total_gov - total_company_deductions - attendance_deductions).quantize(TWOPLACES)
        if net < 0:
            net = ZERO

        missing_hours = max(ZERO, expected - worked_hours).quantize(TWOPLACES)

        return PayrollPreviewResult(
            basic_salary=basic_salary.quantize(TWOPLACES),
            attendance_salary=attendance_salary,
            worked_hours=worked_hours.quantize(TWOPLACES),
            expected_hours=expected,
            attendance_percent=attendance_pct,
            hourly_rate=hr,
            daily_rate=dr,
            overtime_hours=overtime_hours.quantize(TWOPLACES),
            overtime_amount=ot_amount,
            total_bonuses=total_bonuses.quantize(TWOPLACES),
            total_allowances=total_allowances.quantize(TWOPLACES),
            gross_salary=gross,
            income_tax=tax_result.income_tax,
            pension_employee=tax_result.pension_employee,
            pension_employer=tax_result.pension_employer,
            other_government_deductions=tax_result.other_government,
            total_government_deductions=total_gov,
            total_company_deductions=total_company_deductions.quantize(TWOPLACES),
            attendance_deductions=attendance_deductions.quantize(TWOPLACES),
            net_salary=net,
            currency=currency,
            bracket_label=tax_result.bracket_label,
            missing_hours=missing_hours,
        )

    def to_dict(self, result: PayrollPreviewResult) -> dict:
        d = asdict(result)
        return {k: str(v) if isinstance(v, Decimal) else v for k, v in d.items()}
