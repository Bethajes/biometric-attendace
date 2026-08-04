"""
Enterprise Payroll Management models.

Architecture boundary:
  Biometric devices → attendance events only
  Attendance Engine → attendance classification
  Time Tracking Engine → worked hours aggregation
  Payroll Engine → salary calculation (this app)
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class SalaryProfile(models.Model):
    """Per-employee compensation profile used by the Payroll Engine."""

    class PaymentType(models.TextChoices):
        MONTHLY = 'MONTHLY', 'Monthly'
        HOURLY = 'HOURLY', 'Hourly'
        DAILY = 'DAILY', 'Daily'

    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        CASH = 'CASH', 'Cash'
        MOBILE_MONEY = 'MOBILE_MONEY', 'Mobile Money'
        CHEQUE = 'CHEQUE', 'Cheque'

    class TaxCategory(models.TextChoices):
        STANDARD = 'STANDARD', 'Standard Employment'
        EXEMPT = 'EXEMPT', 'Tax Exempt'
        NON_RESIDENT = 'NON_RESIDENT', 'Non-Resident'
        CONTRACTOR = 'CONTRACTOR', 'Contractor'

    employee = models.OneToOneField(
        'attendance.Employee',
        on_delete=models.CASCADE,
        related_name='salary_profile',
    )
    payment_type = models.CharField(
        max_length=20, choices=PaymentType.choices, default=PaymentType.MONTHLY, db_index=True
    )
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.BANK_TRANSFER
    )
    tax_category = models.CharField(
        max_length=20, choices=TaxCategory.choices, default=TaxCategory.STANDARD
    )

    basic_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    gross_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    monthly_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    hourly_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    daily_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    transport_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    housing_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    communication_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    meal_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    other_allowances = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    expected_daily_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('8.00'), verbose_name='Hours Per Day')
    expected_weekly_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('40.00'))
    expected_monthly_hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('160.00'))
    days_per_week = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('5.00'))
    break_duration = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name='Break Duration (minutes)')

    bank_name = models.CharField(max_length=120, blank=True)
    bank_account_number = models.CharField(max_length=64, blank=True)
    bank_branch = models.CharField(max_length=120, blank=True)
    mobile_money_number = models.CharField(max_length=40, blank=True)

    currency = models.CharField(max_length=3, default='ETB')
    tax_rule_set = models.ForeignKey(
        'TaxRuleSet', on_delete=models.SET_NULL, null=True, blank=True, related_name='salary_profiles'
    )
    overtime_rule_set = models.ForeignKey(
        'OvertimeRuleSet', on_delete=models.SET_NULL, null=True, blank=True, related_name='salary_profiles'
    )
    attendance_deduction_policy = models.ForeignKey(
        'AttendanceDeductionPolicy',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salary_profiles',
    )

    bonus_eligible = models.BooleanField(default=True)
    overtime_eligible = models.BooleanField(default=True)
    pension_eligible = models.BooleanField(default=True)
    apply_attendance_deductions = models.BooleanField(default=True)

    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['employee__first_name', 'employee__last_name']
        verbose_name = 'Salary Profile'
        verbose_name_plural = 'Salary Profiles'
        permissions = [
            ('view_payroll_sensitive', 'Can view sensitive payroll data'),
            ('export_payroll', 'Can export payroll data'),
            ('approve_payroll', 'Can approve payroll'),
            ('unlock_payroll', 'Can unlock locked payroll'),
        ]

    def __str__(self):
        return f'Salary: {self.employee} ({self.currency} {self.gross_salary})'

    def clean(self):
        if self.payment_type == self.PaymentType.MONTHLY and self.monthly_salary <= 0 and self.basic_salary <= 0:
            raise ValidationError('Monthly profiles require a monthly or basic salary.')
        if self.payment_type == self.PaymentType.HOURLY and self.hourly_rate <= 0:
            raise ValidationError('Hourly profiles require an hourly rate.')
        if self.payment_type == self.PaymentType.DAILY and self.daily_rate <= 0:
            raise ValidationError('Daily profiles require a daily rate.')

    @property
    def total_fixed_allowances(self) -> Decimal:
        return (
            self.transport_allowance
            + self.housing_allowance
            + self.communication_allowance
            + self.meal_allowance
            + self.other_allowances
        )

    @property
    def resolved_basic(self) -> Decimal:
        if self.basic_salary > 0:
            return self.basic_salary
        if self.monthly_salary > 0:
            return self.monthly_salary
        return self.gross_salary

    def get_absolute_url(self):
        return reverse('payroll_salary_detail', kwargs={'pk': self.pk})


class TaxRuleSet(models.Model):
    """Named tax configuration (e.g. Ethiopian Employment Income Tax 2024)."""

    name = models.CharField(max_length=160, unique=True)
    country_code = models.CharField(max_length=3, default='ET')
    currency = models.CharField(max_length=3, default='ETB')
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False, db_index=True)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', 'name']
        verbose_name = 'Tax Rule Set'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            TaxRuleSet.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class TaxBracket(models.Model):
    """Progressive income tax bracket — fully configurable, never hardcode rates in engine."""

    rule_set = models.ForeignKey(TaxRuleSet, on_delete=models.CASCADE, related_name='brackets')
    min_income = models.DecimalField(max_digits=14, decimal_places=2)
    max_income = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Leave blank for unlimited upper bound.',
    )
    rate_percent = models.DecimalField(
        max_digits=6, decimal_places=3, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    deduction_constant = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text='Fixed amount subtracted after applying rate (Ethiopian style).',
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'min_income']
        verbose_name = 'Tax Bracket'

    def __str__(self):
        upper = self.max_income if self.max_income is not None else '∞'
        return f'{self.min_income}–{upper} @ {self.rate_percent}%'


class ContributionRule(models.Model):
    """Pension / social / employer / employee contribution rates."""

    class ContributionType(models.TextChoices):
        PENSION_EMPLOYEE = 'PENSION_EMPLOYEE', 'Pension (Employee)'
        PENSION_EMPLOYER = 'PENSION_EMPLOYER', 'Pension (Employer)'
        SOCIAL_EMPLOYEE = 'SOCIAL_EMPLOYEE', 'Social Security (Employee)'
        SOCIAL_EMPLOYER = 'SOCIAL_EMPLOYER', 'Social Security (Employer)'
        OTHER_GOVERNMENT = 'OTHER_GOVERNMENT', 'Other Government Deduction'

    class BaseAmount(models.TextChoices):
        BASIC = 'BASIC', 'Basic Salary'
        GROSS = 'GROSS', 'Gross Salary'
        TAXABLE = 'TAXABLE', 'Taxable Income'

    rule_set = models.ForeignKey(TaxRuleSet, on_delete=models.CASCADE, related_name='contributions')
    contribution_type = models.CharField(max_length=30, choices=ContributionType.choices)
    name = models.CharField(max_length=120)
    rate_percent = models.DecimalField(
        max_digits=6, decimal_places=3, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    base_amount = models.CharField(max_length=20, choices=BaseAmount.choices, default=BaseAmount.BASIC)
    is_employer_paid = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['contribution_type']
        verbose_name = 'Contribution Rule'

    def __str__(self):
        return f'{self.name} ({self.rate_percent}%)'


class OvertimeRuleSet(models.Model):
    name = models.CharField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            OvertimeRuleSet.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class OvertimeRule(models.Model):
    class OvertimeType(models.TextChoices):
        WEEKDAY = 'WEEKDAY', 'Weekday Overtime'
        WEEKEND = 'WEEKEND', 'Weekend Overtime'
        HOLIDAY = 'HOLIDAY', 'Holiday Overtime'
        NIGHT = 'NIGHT', 'Night Shift Overtime'

    rule_set = models.ForeignKey(OvertimeRuleSet, on_delete=models.CASCADE, related_name='rules')
    overtime_type = models.CharField(max_length=20, choices=OvertimeType.choices)
    multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('1.50'),
        validators=[MinValueValidator(Decimal('1.00'))],
    )
    night_start = models.TimeField(null=True, blank=True)
    night_end = models.TimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('rule_set', 'overtime_type')]
        ordering = ['overtime_type']

    def __str__(self):
        return f'{self.get_overtime_type_display()} ×{self.multiplier}'


class AttendanceDeductionPolicy(models.Model):
    """Maps missing hours / late / absence into monetary deductions."""

    name = models.CharField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    deduct_missing_hours = models.BooleanField(default=True)
    missing_hour_rate_source = models.CharField(
        max_length=20,
        choices=[
            ('HOURLY_RATE', 'Employee Hourly Rate'),
            ('BASIC_DIV_EXPECTED', 'Basic ÷ Expected Monthly Hours'),
            ('GROSS_DIV_EXPECTED', 'Gross ÷ Expected Monthly Hours'),
        ],
        default='BASIC_DIV_EXPECTED',
    )
    late_deduction_per_minute = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0.00'))
    early_leave_deduction_per_minute = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('0.00')
    )
    absent_day_deduction_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('1.00'),
        help_text='Multiplier of daily rate deducted per unauthorized absence day.',
    )
    unpaid_leave_deducts = models.BooleanField(default=True)
    grace_missing_minutes = models.PositiveIntegerField(
        default=0, help_text='Missing minutes below this threshold are not deducted.'
    )

    class Meta:
        verbose_name = 'Attendance Deduction Policy'
        verbose_name_plural = 'Attendance Deduction Policies'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            AttendanceDeductionPolicy.objects.filter(is_default=True).exclude(pk=self.pk).update(
                is_default=False
            )
        super().save(*args, **kwargs)


class LeavePayrollImpact(models.Model):
    """Configures whether each leave type affects payroll (paid vs unpaid)."""

    class LeaveType(models.TextChoices):
        ANNUAL = 'ANNUAL', 'Annual Leave'
        SICK = 'SICK', 'Sick Leave'
        PERSONAL = 'PERSONAL', 'Personal Leave'
        UNPAID = 'UNPAID', 'Unpaid Leave'
        MATERNITY = 'MATERNITY', 'Maternity Leave'
        PATERNITY = 'PATERNITY', 'Paternity Leave'
        BEREAVEMENT = 'BEREAVEMENT', 'Bereavement Leave'
        COMPOFF = 'COMPOFF', 'Compensatory Off'
        PUBLIC_HOLIDAY = 'PUBLIC_HOLIDAY', 'Public Holiday'
        COMPANY_HOLIDAY = 'COMPANY_HOLIDAY', 'Company Holiday'
        WEEKEND = 'WEEKEND', 'Weekend'

    leave_type = models.CharField(max_length=30, choices=LeaveType.choices, unique=True)
    is_paid = models.BooleanField(default=True)
    pay_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('100.00'),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    affects_attendance_bonus = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['leave_type']
        verbose_name = 'Leave Payroll Impact'

    def __str__(self):
        paid = 'Paid' if self.is_paid else 'Unpaid'
        return f'{self.get_leave_type_display()} — {paid} ({self.pay_percentage}%)'


class Allowance(models.Model):
    """Ad-hoc or recurring allowance assigned to an employee for a period."""

    class AllowanceType(models.TextChoices):
        TRANSPORT = 'TRANSPORT', 'Transport'
        HOUSING = 'HOUSING', 'Housing'
        COMMUNICATION = 'COMMUNICATION', 'Communication'
        MEAL = 'MEAL', 'Meal'
        OTHER = 'OTHER', 'Other'

    employee = models.ForeignKey(
        'attendance.Employee', on_delete=models.CASCADE, related_name='payroll_allowances'
    )
    allowance_type = models.CharField(max_length=20, choices=AllowanceType.choices)
    name = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_taxable = models.BooleanField(default=True)
    is_recurring = models.BooleanField(default=False)
    period = models.ForeignKey(
        'PayrollPeriod', on_delete=models.CASCADE, null=True, blank=True, related_name='allowances'
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_allowances',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name}: {self.amount} ({self.employee})'


class Bonus(models.Model):
    class BonusType(models.TextChoices):
        PERFORMANCE = 'PERFORMANCE', 'Performance Bonus'
        ATTENDANCE = 'ATTENDANCE', 'Attendance Bonus'
        HOLIDAY = 'HOLIDAY', 'Holiday Bonus'
        MONTHLY = 'MONTHLY', 'Monthly Bonus'
        ANNUAL = 'ANNUAL', 'Annual Bonus'
        PROJECT = 'PROJECT', 'Project Bonus'
        REFERRAL = 'REFERRAL', 'Referral Bonus'
        CUSTOM = 'CUSTOM', 'Custom Bonus'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        PAID = 'PAID', 'Paid'

    employee = models.ForeignKey(
        'attendance.Employee', on_delete=models.CASCADE, related_name='payroll_bonuses'
    )
    bonus_type = models.CharField(max_length=20, choices=BonusType.choices)
    reason = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_taxable = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    period = models.ForeignKey(
        'PayrollPeriod', on_delete=models.SET_NULL, null=True, blank=True, related_name='bonuses'
    )
    bonus_date = models.DateField(default=timezone.localdate)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_bonuses',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-bonus_date', '-id']
        verbose_name_plural = 'Bonuses'

    def __str__(self):
        return f'{self.get_bonus_type_display()}: {self.amount} ({self.employee})'


class Deduction(models.Model):
    class DeductionType(models.TextChoices):
        LATE_ARRIVAL = 'LATE_ARRIVAL', 'Late Arrival'
        MISSING_CHECKOUT = 'MISSING_CHECKOUT', 'Missing Checkout'
        UNAUTHORIZED_ABSENCE = 'UNAUTHORIZED_ABSENCE', 'Unauthorized Absence'
        DAMAGE_RECOVERY = 'DAMAGE_RECOVERY', 'Damage Recovery'
        LOAN_DEDUCTION = 'LOAN_DEDUCTION', 'Loan Deduction'
        ADVANCE_RECOVERY = 'ADVANCE_RECOVERY', 'Advance Salary Recovery'
        DISCIPLINARY = 'DISCIPLINARY', 'Disciplinary Penalty'
        ATTENDANCE = 'ATTENDANCE', 'Attendance Deduction'
        OTHER = 'OTHER', 'Other Deduction'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        APPLIED = 'APPLIED', 'Applied'

    employee = models.ForeignKey(
        'attendance.Employee', on_delete=models.CASCADE, related_name='payroll_deductions'
    )
    deduction_type = models.CharField(max_length=30, choices=DeductionType.choices)
    reason = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    period = models.ForeignKey(
        'PayrollPeriod', on_delete=models.SET_NULL, null=True, blank=True, related_name='deductions'
    )
    deduction_date = models.DateField(default=timezone.localdate)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_deductions',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_system_generated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-deduction_date', '-id']

    def __str__(self):
        return f'{self.get_deduction_type_display()}: {self.amount} ({self.employee})'


class OvertimeRecord(models.Model):
    """Payroll-facing OT hours classified by type (from Time Tracking Engine)."""

    class OvertimeType(models.TextChoices):
        WEEKDAY = 'WEEKDAY', 'Weekday'
        WEEKEND = 'WEEKEND', 'Weekend'
        HOLIDAY = 'HOLIDAY', 'Holiday'
        NIGHT = 'NIGHT', 'Night Shift'

    employee = models.ForeignKey(
        'attendance.Employee', on_delete=models.CASCADE, related_name='payroll_overtime_records'
    )
    period = models.ForeignKey(
        'PayrollPeriod', on_delete=models.CASCADE, related_name='overtime_records'
    )
    work_date = models.DateField(db_index=True)
    overtime_type = models.CharField(max_length=20, choices=OvertimeType.choices)
    minutes = models.PositiveIntegerField(default=0)
    multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.50'))
    hourly_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    source_attendance_record = models.ForeignKey(
        'attendance.AttendanceRecord', on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['work_date']
        indexes = [models.Index(fields=['employee', 'period'])]

    def __str__(self):
        return f'{self.employee} {self.work_date} {self.overtime_type} {self.minutes}m'


class PayrollPeriod(models.Model):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        PROCESSING = 'PROCESSING', 'Processing'
        DRAFT = 'DRAFT', 'Draft'
        HR_REVIEW = 'HR_REVIEW', 'HR Review'
        FINANCE_REVIEW = 'FINANCE_REVIEW', 'Finance Review'
        APPROVED = 'APPROVED', 'Approved'
        LOCKED = 'LOCKED', 'Locked'
        PAID = 'PAID', 'Paid'
        CANCELLED = 'CANCELLED', 'Cancelled'

    name = models.CharField(max_length=120)
    year = models.PositiveIntegerField(db_index=True)
    month = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)], db_index=True
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    company = models.ForeignKey(
        'organizations.Company', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_periods',
    )
    tax_rule_set = models.ForeignKey(
        TaxRuleSet, on_delete=models.SET_NULL, null=True, blank=True, related_name='periods'
    )
    overtime_rule_set = models.ForeignKey(
        OvertimeRuleSet, on_delete=models.SET_NULL, null=True, blank=True, related_name='periods'
    )
    payment_date = models.DateField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='locked_payroll_periods',
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_payroll_periods',
    )

    class Meta:
        ordering = ['-year', '-month']
        unique_together = [('year', 'month', 'company')]
        verbose_name = 'Payroll Period'
        permissions = [
            ('process_payroll_period', 'Can process payroll for a period'),
        ]

    def __str__(self):
        return self.name or f'{self.year}-{self.month:02d}'

    @property
    def is_modifiable(self) -> bool:
        return self.status in {
            self.Status.OPEN,
            self.Status.PROCESSING,
            self.Status.DRAFT,
            self.Status.HR_REVIEW,
            self.Status.FINANCE_REVIEW,
        }

    @property
    def is_locked(self) -> bool:
        return self.status in {self.Status.LOCKED, self.Status.PAID, self.Status.APPROVED}

    def get_absolute_url(self):
        return reverse('payroll_period_detail', kwargs={'pk': self.pk})


class Payroll(models.Model):
    """Calculated payroll result for one employee in one period."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        HR_REVIEW = 'HR_REVIEW', 'HR Review'
        FINANCE_REVIEW = 'FINANCE_REVIEW', 'Finance Review'
        APPROVED = 'APPROVED', 'Approved'
        LOCKED = 'LOCKED', 'Locked'
        PAID = 'PAID', 'Paid'
        CANCELLED = 'CANCELLED', 'Cancelled'

    period = models.ForeignKey(PayrollPeriod, on_delete=models.CASCADE, related_name='payrolls')
    employee = models.ForeignKey(
        'attendance.Employee', on_delete=models.CASCADE, related_name='payrolls'
    )
    salary_profile = models.ForeignKey(
        SalaryProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='payrolls'
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    currency = models.CharField(max_length=3, default='ETB')

    basic_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_allowances = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_bonuses = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_overtime = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    gross_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    taxable_income = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    income_tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    pension_employee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    pension_employer = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    other_government_deductions = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    total_government_deductions = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    total_company_deductions = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    total_penalties = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    attendance_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    net_salary = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    expected_hours = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    worked_hours = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    missing_hours = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    late_minutes = models.PositiveIntegerField(default=0)
    early_leave_minutes = models.PositiveIntegerField(default=0)
    absent_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    unpaid_leave_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    paid_leave_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    holiday_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    present_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))

    payment_method = models.CharField(max_length=20, blank=True)
    bank_account_number = models.CharField(max_length=64, blank=True)
    calculation_notes = models.TextField(blank=True)
    calculated_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('period', 'employee')]
        ordering = ['employee__first_name', 'employee__last_name']
        verbose_name = 'Payroll'
        verbose_name_plural = 'Payrolls'
        indexes = [
            models.Index(fields=['period', 'status']),
            models.Index(fields=['employee', 'status']),
        ]

    def __str__(self):
        return f'Payroll {self.employee} — {self.period}'

    @property
    def is_modifiable(self) -> bool:
        return self.status in {
            self.Status.DRAFT,
            self.Status.HR_REVIEW,
            self.Status.FINANCE_REVIEW,
        } and self.period.is_modifiable

    def get_absolute_url(self):
        return reverse('payroll_detail', kwargs={'pk': self.pk})


class PayrollItem(models.Model):
    """Line-item breakdown of a payroll calculation."""

    class ItemType(models.TextChoices):
        BASIC = 'BASIC', 'Basic Salary'
        ALLOWANCE = 'ALLOWANCE', 'Allowance'
        BONUS = 'BONUS', 'Bonus'
        OVERTIME = 'OVERTIME', 'Overtime'
        TAX = 'TAX', 'Income Tax'
        PENSION_EMPLOYEE = 'PENSION_EMPLOYEE', 'Pension (Employee)'
        PENSION_EMPLOYER = 'PENSION_EMPLOYER', 'Pension (Employer)'
        GOVERNMENT = 'GOVERNMENT', 'Government Deduction'
        COMPANY_DEDUCTION = 'COMPANY_DEDUCTION', 'Company Deduction'
        PENALTY = 'PENALTY', 'Penalty'
        ATTENDANCE_DEDUCTION = 'ATTENDANCE_DEDUCTION', 'Attendance Deduction'
        OTHER_EARNING = 'OTHER_EARNING', 'Other Earning'
        OTHER_DEDUCTION = 'OTHER_DEDUCTION', 'Other Deduction'

    class Direction(models.TextChoices):
        EARNING = 'EARNING', 'Earning'
        DEDUCTION = 'DEDUCTION', 'Deduction'
        EMPLOYER = 'EMPLOYER', 'Employer Contribution'

    payroll = models.ForeignKey(Payroll, on_delete=models.CASCADE, related_name='items')
    item_type = models.CharField(max_length=30, choices=ItemType.choices)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    code = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    rate = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.00'))
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    is_taxable = models.BooleanField(default=False)
    reference_id = models.PositiveIntegerField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'{self.description}: {self.amount}'


class Payslip(models.Model):
    payroll = models.OneToOneField(Payroll, on_delete=models.CASCADE, related_name='payslip')
    payslip_number = models.CharField(max_length=40, unique=True)
    company_name = models.CharField(max_length=200, blank=True)
    company_address = models.TextField(blank=True)
    company_tax_id = models.CharField(max_length=100, blank=True)
    employee_name = models.CharField(max_length=200)
    employee_id = models.CharField(max_length=50)
    department_name = models.CharField(max_length=150, blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    period_label = models.CharField(max_length=120)
    issued_at = models.DateTimeField(default=timezone.now)
    pdf_generated = models.BooleanField(default=False)
    qr_payload = models.CharField(max_length=255, blank=True, help_text='Reserved for future QR verification')
    digital_signature = models.TextField(blank=True, help_text='Reserved for future digital signature')
    snapshot_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return self.payslip_number

    def get_absolute_url(self):
        return reverse('payroll_payslip', kwargs={'pk': self.pk})


class PayrollApproval(models.Model):
    class Stage(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        HR_REVIEW = 'HR_REVIEW', 'HR Review'
        FINANCE_REVIEW = 'FINANCE_REVIEW', 'Finance Review'
        APPROVED = 'APPROVED', 'Approved'
        LOCKED = 'LOCKED', 'Locked'
        PAID = 'PAID', 'Paid'
        REJECTED = 'REJECTED', 'Rejected'
        UNLOCKED = 'UNLOCKED', 'Unlocked'

    class Decision(models.TextChoices):
        SUBMIT = 'SUBMIT', 'Submit'
        APPROVE = 'APPROVE', 'Approve'
        REJECT = 'REJECT', 'Reject'
        LOCK = 'LOCK', 'Lock'
        UNLOCK = 'UNLOCK', 'Unlock'
        MARK_PAID = 'MARK_PAID', 'Mark Paid'

    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, null=True, blank=True, related_name='approvals'
    )
    payroll = models.ForeignKey(
        Payroll, on_delete=models.CASCADE, null=True, blank=True, related_name='approvals'
    )
    stage = models.CharField(max_length=20, choices=Stage.choices)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_approvals',
    )
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        target = self.payroll or self.period
        return f'{self.decision} @ {self.stage} — {target}'


class PayrollAudit(models.Model):
    class Action(models.TextChoices):
        CREATE = 'CREATE', 'Create'
        UPDATE = 'UPDATE', 'Update'
        DELETE = 'DELETE', 'Delete'
        CALCULATE = 'CALCULATE', 'Calculate'
        APPROVE = 'APPROVE', 'Approve'
        REJECT = 'REJECT', 'Reject'
        LOCK = 'LOCK', 'Lock'
        UNLOCK = 'UNLOCK', 'Unlock'
        PAY = 'PAY', 'Pay'
        EXPORT = 'EXPORT', 'Export'
        VIEW = 'VIEW', 'View'
        GENERATE_PAYSLIP = 'GENERATE_PAYSLIP', 'Generate Payslip'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_audits',
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    entity_type = models.CharField(max_length=60)
    entity_id = models.PositiveIntegerField(null=True, blank=True)
    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.SET_NULL, null=True, blank=True, related_name='audits'
    )
    payroll = models.ForeignKey(
        Payroll, on_delete=models.SET_NULL, null=True, blank=True, related_name='audits'
    )
    summary = models.CharField(max_length=255)
    before_data = models.JSONField(default=dict, blank=True)
    after_data = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payroll Audit Log'

    def __str__(self):
        return f'{self.action}: {self.summary}'
