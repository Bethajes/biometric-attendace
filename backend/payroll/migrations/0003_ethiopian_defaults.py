from decimal import Decimal
from django.db import migrations


ETHIOPIAN_TAX_BRACKETS = [
    {'order': 0, 'min_income': Decimal('0'), 'max_income': Decimal('600'), 'rate_percent': Decimal('0'), 'deduction_constant': Decimal('0')},
    {'order': 1, 'min_income': Decimal('600.01'), 'max_income': Decimal('1650'), 'rate_percent': Decimal('10'), 'deduction_constant': Decimal('60')},
    {'order': 2, 'min_income': Decimal('1650.01'), 'max_income': Decimal('3200'), 'rate_percent': Decimal('15'), 'deduction_constant': Decimal('142.50')},
    {'order': 3, 'min_income': Decimal('3200.01'), 'max_income': Decimal('5250'), 'rate_percent': Decimal('20'), 'deduction_constant': Decimal('302.50')},
    {'order': 4, 'min_income': Decimal('5250.01'), 'max_income': Decimal('7800'), 'rate_percent': Decimal('25'), 'deduction_constant': Decimal('565')},
    {'order': 5, 'min_income': Decimal('7800.01'), 'max_income': Decimal('10900'), 'rate_percent': Decimal('30'), 'deduction_constant': Decimal('955')},
    {'order': 6, 'min_income': Decimal('10900.01'), 'max_income': None, 'rate_percent': Decimal('35'), 'deduction_constant': Decimal('1500')},
]

ETHIOPIAN_CONTRIBUTIONS = [
    {'contribution_type': 'PENSION_EMPLOYEE', 'name': 'Pension (Employee)', 'rate_percent': Decimal('7'), 'base_amount': 'BASIC', 'is_employer_paid': False},
    {'contribution_type': 'PENSION_EMPLOYER', 'name': 'Pension (Employer)', 'rate_percent': Decimal('11'), 'base_amount': 'BASIC', 'is_employer_paid': True},
]

OT_RULES = [
    {'overtime_type': 'WEEKDAY', 'multiplier': Decimal('1.50')},
    {'overtime_type': 'WEEKEND', 'multiplier': Decimal('2.00')},
    {'overtime_type': 'HOLIDAY', 'multiplier': Decimal('2.50')},
    {'overtime_type': 'NIGHT', 'multiplier': Decimal('1.75'), 'night_start': '22:00:00', 'night_end': '06:00:00'},
]

LEAVE_IMPACTS = [
    {'leave_type': 'ANNUAL', 'is_paid': True, 'pay_percentage': Decimal('100.00')},
    {'leave_type': 'SICK', 'is_paid': True, 'pay_percentage': Decimal('100.00')},
    {'leave_type': 'PERSONAL', 'is_paid': True, 'pay_percentage': Decimal('100.00')},
    {'leave_type': 'UNPAID', 'is_paid': False, 'pay_percentage': Decimal('0.00')},
    {'leave_type': 'MATERNITY', 'is_paid': True, 'pay_percentage': Decimal('100.00')},
    {'leave_type': 'PATERNITY', 'is_paid': True, 'pay_percentage': Decimal('100.00')},
    {'leave_type': 'BEREAVEMENT', 'is_paid': True, 'pay_percentage': Decimal('100.00')},
    {'leave_type': 'COMPOFF', 'is_paid': True, 'pay_percentage': Decimal('100.00')},
    {'leave_type': 'PUBLIC_HOLIDAY', 'is_paid': True, 'pay_percentage': Decimal('100.00')},
    {'leave_type': 'COMPANY_HOLIDAY', 'is_paid': True, 'pay_percentage': Decimal('100.00')},
    {'leave_type': 'WEEKEND', 'is_paid': False, 'pay_percentage': Decimal('0.00')},
]

DEDUCTION_POLICY = {
    'name': 'Standard Ethiopian Attendance Policy',
    'deduct_missing_hours': True,
    'missing_hour_rate_source': 'BASIC_DIV_EXPECTED',
    'late_deduction_per_minute': Decimal('0.00'),
    'early_leave_deduction_per_minute': Decimal('0.00'),
    'absent_day_deduction_rate': Decimal('1.00'),
    'unpaid_leave_deducts': True,
    'grace_missing_minutes': 15,
}


def create_ethiopian_defaults(apps, schema_editor):
    TaxRuleSet = apps.get_model('payroll', 'TaxRuleSet')
    TaxBracket = apps.get_model('payroll', 'TaxBracket')
    ContributionRule = apps.get_model('payroll', 'ContributionRule')
    OvertimeRuleSet = apps.get_model('payroll', 'OvertimeRuleSet')
    OvertimeRule = apps.get_model('payroll', 'OvertimeRule')
    LeavePayrollImpact = apps.get_model('payroll', 'LeavePayrollImpact')
    AttendanceDeductionPolicy = apps.get_model('payroll', 'AttendanceDeductionPolicy')

    if TaxRuleSet.objects.filter(is_default=True).exists():
        return

    tax_set = TaxRuleSet.objects.create(
        name='Ethiopian Employment Income Tax 2024',
        country_code='ET',
        currency='ETB',
        description='Standard progressive tax brackets per Ethiopian tax law.',
        is_default=True,
        is_active=True,
    )
    for bracket in ETHIOPIAN_TAX_BRACKETS:
        TaxBracket.objects.create(rule_set=tax_set, **bracket)
    for contrib in ETHIOPIAN_CONTRIBUTIONS:
        ContributionRule.objects.create(rule_set=tax_set, **contrib)

    ot_set = OvertimeRuleSet.objects.create(
        name='Ethiopian Standard Overtime Rules',
        description='Standard overtime multipliers used in Ethiopia.',
        is_default=True,
        is_active=True,
    )
    for rule in OT_RULES:
        OvertimeRule.objects.create(rule_set=ot_set, **rule)

    for impact in LEAVE_IMPACTS:
        LeavePayrollImpact.objects.create(**impact)

    AttendanceDeductionPolicy.objects.create(is_default=True, **DEDUCTION_POLICY)


def reverse_defaults(apps, schema_editor):
    TaxRuleSet = apps.get_model('payroll', 'TaxRuleSet')
    OvertimeRuleSet = apps.get_model('payroll', 'OvertimeRuleSet')
    LeavePayrollImpact = apps.get_model('payroll', 'LeavePayrollImpact')
    AttendanceDeductionPolicy = apps.get_model('payroll', 'AttendanceDeductionPolicy')
    TaxRuleSet.objects.filter(name='Ethiopian Employment Income Tax 2024').delete()
    OvertimeRuleSet.objects.filter(name='Ethiopian Standard Overtime Rules').delete()
    LeavePayrollImpact.objects.all().delete()
    AttendanceDeductionPolicy.objects.filter(name='Standard Ethiopian Attendance Policy').delete()


class Migration(migrations.Migration):
    dependencies = [('payroll', '0002_salaryprofile_break_duration_and_more')]
    operations = [migrations.RunPython(create_ethiopian_defaults, reverse_defaults)]
