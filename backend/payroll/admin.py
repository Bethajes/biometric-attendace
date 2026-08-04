from django.contrib import admin

from .models import (
    Allowance,
    AttendanceDeductionPolicy,
    Bonus,
    ContributionRule,
    Deduction,
    LeavePayrollImpact,
    OvertimeRecord,
    OvertimeRule,
    OvertimeRuleSet,
    Payroll,
    PayrollApproval,
    PayrollAudit,
    PayrollItem,
    PayrollPeriod,
    Payslip,
    SalaryProfile,
    TaxBracket,
    TaxRuleSet,
)


class TaxBracketInline(admin.TabularInline):
    model = TaxBracket
    extra = 0


class ContributionRuleInline(admin.TabularInline):
    model = ContributionRule
    extra = 0


@admin.register(TaxRuleSet)
class TaxRuleSetAdmin(admin.ModelAdmin):
    list_display = ('name', 'country_code', 'currency', 'is_default', 'is_active', 'effective_from')
    list_filter = ('country_code', 'is_default', 'is_active')
    inlines = [TaxBracketInline, ContributionRuleInline]


class OvertimeRuleInline(admin.TabularInline):
    model = OvertimeRule
    extra = 0


@admin.register(OvertimeRuleSet)
class OvertimeRuleSetAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_default', 'is_active')
    inlines = [OvertimeRuleInline]


@admin.register(AttendanceDeductionPolicy)
class AttendanceDeductionPolicyAdmin(admin.ModelAdmin):
    list_display = ('name', 'deduct_missing_hours', 'is_default', 'is_active')


@admin.register(LeavePayrollImpact)
class LeavePayrollImpactAdmin(admin.ModelAdmin):
    list_display = ('leave_type', 'is_paid', 'pay_percentage', 'affects_attendance_bonus')


@admin.register(SalaryProfile)
class SalaryProfileAdmin(admin.ModelAdmin):
    list_display = (
        'employee', 'payment_type', 'basic_salary', 'gross_salary',
        'currency', 'is_active', 'overtime_eligible', 'pension_eligible',
    )
    list_filter = ('payment_type', 'tax_category', 'is_active', 'currency')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
    raw_id_fields = ('employee',)


class PayrollItemInline(admin.TabularInline):
    model = PayrollItem
    extra = 0
    readonly_fields = (
        'item_type', 'direction', 'code', 'description', 'quantity', 'rate', 'amount', 'is_taxable',
    )


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'year', 'month', 'start_date', 'end_date', 'status', 'company')
    list_filter = ('status', 'year', 'month')
    search_fields = ('name',)


@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = (
        'employee', 'period', 'status', 'gross_salary', 'net_salary',
        'worked_hours', 'expected_hours', 'income_tax',
    )
    list_filter = ('status', 'period', 'currency')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
    inlines = [PayrollItemInline]
    readonly_fields = ('calculated_at', 'approved_at', 'paid_at')


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('payslip_number', 'employee_name', 'period_label', 'issued_at')
    search_fields = ('payslip_number', 'employee_name', 'employee_id')


@admin.register(Bonus)
class BonusAdmin(admin.ModelAdmin):
    list_display = ('employee', 'bonus_type', 'amount', 'status', 'bonus_date')
    list_filter = ('bonus_type', 'status')


@admin.register(Deduction)
class DeductionAdmin(admin.ModelAdmin):
    list_display = ('employee', 'deduction_type', 'amount', 'status', 'deduction_date')
    list_filter = ('deduction_type', 'status')


@admin.register(Allowance)
class AllowanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'allowance_type', 'name', 'amount', 'is_recurring')


@admin.register(OvertimeRecord)
class OvertimeRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'period', 'work_date', 'overtime_type', 'minutes', 'amount')
    list_filter = ('overtime_type', 'period')


@admin.register(PayrollApproval)
class PayrollApprovalAdmin(admin.ModelAdmin):
    list_display = ('stage', 'decision', 'actor', 'period', 'payroll', 'created_at')
    list_filter = ('stage', 'decision')


@admin.register(PayrollAudit)
class PayrollAuditAdmin(admin.ModelAdmin):
    list_display = ('action', 'summary', 'actor', 'entity_type', 'created_at')
    list_filter = ('action', 'entity_type')
    readonly_fields = (
        'actor', 'action', 'entity_type', 'entity_id', 'period', 'payroll',
        'summary', 'before_data', 'after_data', 'ip_address', 'user_agent', 'created_at',
    )
