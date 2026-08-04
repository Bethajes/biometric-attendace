from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.utils import timezone

from attendance.models import Employee
from organizations.models import Company, Department

from .models import (
    Allowance,
    AttendanceDeductionPolicy,
    Bonus,
    Deduction,
    OvertimeRuleSet,
    PayrollPeriod,
    SalaryProfile,
    TaxRuleSet,
)

WEEKS_PER_MONTH = Decimal('4.33333')


def compute_hours(hours_per_day, days_per_week, break_minutes):
    break_hours = (Decimal(str(break_minutes or 0)) / Decimal('60')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    effective_daily = Decimal(str(hours_per_day)) - break_hours
    weekly = (effective_daily * Decimal(str(days_per_week))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    monthly = (weekly * WEEKS_PER_MONTH).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    annual = (weekly * Decimal('52')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return effective_daily, weekly, monthly, annual


def compute_salary(payment_type, source_value, hours_per_day, days_per_week, break_minutes):
    effective_daily, weekly_hours, monthly_hours, annual_hours = compute_hours(
        hours_per_day, days_per_week, break_minutes
    )
    source = Decimal(str(source_value or 0))
    monthly = Decimal('0')
    hourly = Decimal('0')
    daily = Decimal('0')
    weekly = Decimal('0')

    if payment_type == 'MONTHLY':
        monthly = source
        if monthly_hours > 0:
            hourly = (source / monthly_hours).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if days_per_week > 0:
            daily_rate_val = source / (Decimal(str(days_per_week)) * WEEKS_PER_MONTH)
            daily = daily_rate_val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            weekly = (daily * Decimal(str(days_per_week))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    elif payment_type == 'HOURLY':
        hourly = source
        daily = (source * effective_daily).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        weekly = (daily * Decimal(str(days_per_week))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        monthly = (weekly * WEEKS_PER_MONTH).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    elif payment_type == 'DAILY':
        daily = source
        if effective_daily > 0:
            hourly = (source / effective_daily).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        weekly = (source * Decimal(str(days_per_week))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        monthly = (weekly * WEEKS_PER_MONTH).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return hourly, daily, weekly, monthly, monthly_hours, weekly_hours


class SalaryProfileForm(forms.ModelForm):
    class Meta:
        model = SalaryProfile
        fields = [
            'employee', 'payment_type', 'payment_method', 'tax_category',
            'basic_salary', 'gross_salary', 'monthly_salary', 'hourly_rate', 'daily_rate',
            'transport_allowance', 'housing_allowance', 'communication_allowance',
            'meal_allowance', 'other_allowances',
            'expected_daily_hours', 'expected_weekly_hours', 'expected_monthly_hours',
            'days_per_week', 'break_duration',
            'bank_name', 'bank_account_number', 'bank_branch', 'mobile_money_number',
            'currency', 'tax_rule_set', 'overtime_rule_set', 'attendance_deduction_policy',
            'bonus_eligible', 'overtime_eligible', 'pension_eligible', 'apply_attendance_deductions',
            'effective_from', 'effective_to', 'is_active', 'notes',
        ]
        widgets = {
            'expected_weekly_hours': forms.NumberInput(attrs={'readonly': True}),
            'expected_monthly_hours': forms.NumberInput(attrs={'readonly': True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        not_required = [
            'basic_salary', 'gross_salary', 'monthly_salary', 'hourly_rate', 'daily_rate',
            'transport_allowance', 'housing_allowance', 'communication_allowance',
            'meal_allowance', 'other_allowances',
            'bank_name', 'bank_account_number', 'bank_branch', 'mobile_money_number',
            'tax_rule_set', 'overtime_rule_set', 'attendance_deduction_policy',
            'effective_to', 'notes',
        ]
        for fname in not_required:
            if fname in self.fields:
                self.fields[fname].required = False

    def clean(self):
        cleaned = super().clean()
        payment_type = cleaned.get('payment_type')
        hours_per_day = cleaned.get('expected_daily_hours') or Decimal('8')
        days_per_week = cleaned.get('days_per_week') or Decimal('5')
        break_minutes = cleaned.get('break_duration') or Decimal('0')

        hourly, daily, weekly, monthly, monthly_hours, weekly_hours = compute_salary(
            payment_type,
            cleaned.get('monthly_salary') or Decimal('0'),
            hours_per_day,
            days_per_week,
            break_minutes,
        )

        effective_daily_hours, _, _, _ = compute_hours(hours_per_day, days_per_week, break_minutes)

        if payment_type == 'MONTHLY':
            cleaned['hourly_rate'] = hourly
            cleaned['daily_rate'] = daily
            cleaned['basic_salary'] = monthly
            cleaned['gross_salary'] = monthly
        elif payment_type == 'HOURLY':
            cleaned['daily_rate'] = daily
            cleaned['monthly_salary'] = monthly
            cleaned['basic_salary'] = monthly
            cleaned['gross_salary'] = monthly
        elif payment_type == 'DAILY':
            cleaned['hourly_rate'] = hourly
            cleaned['monthly_salary'] = monthly
            cleaned['basic_salary'] = monthly
            cleaned['gross_salary'] = monthly

        cleaned['expected_weekly_hours'] = weekly_hours
        cleaned['expected_monthly_hours'] = monthly_hours

        return cleaned


class PayrollPeriodForm(forms.ModelForm):
    class Meta:
        model = PayrollPeriod
        fields = [
            'name', 'year', 'month', 'start_date', 'end_date',
            'company', 'tax_rule_set', 'overtime_rule_set', 'payment_date', 'notes',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            today = timezone.localdate()
            last_day = monthrange(today.year, today.month)[1]
            self.fields['year'].initial = today.year
            self.fields['month'].initial = today.month
            self.fields['start_date'].initial = date(today.year, today.month, 1)
            self.fields['end_date'].initial = date(today.year, today.month, last_day)
            self.fields['name'].initial = today.strftime('%B %Y Payroll')


class BonusForm(forms.ModelForm):
    class Meta:
        model = Bonus
        fields = [
            'employee', 'bonus_type', 'reason', 'amount', 'is_taxable',
            'status', 'period', 'bonus_date', 'notes',
        ]


class DeductionForm(forms.ModelForm):
    class Meta:
        model = Deduction
        fields = [
            'employee', 'deduction_type', 'reason', 'amount',
            'status', 'period', 'deduction_date', 'notes',
        ]


class AllowanceForm(forms.ModelForm):
    class Meta:
        model = Allowance
        fields = [
            'employee', 'allowance_type', 'name', 'amount', 'is_taxable',
            'is_recurring', 'period', 'effective_from', 'effective_to', 'notes',
        ]


class PayrollProcessForm(forms.Form):
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True),
        required=False,
        empty_label='All departments',
    )
    replace_existing = forms.BooleanField(required=False, initial=True)


class ApprovalActionForm(forms.Form):
    comments = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
