"""
Seed Ethiopian payroll configuration tables.

Rates are stored in the database so administrators can update them when
regulations change — they are NOT hardcoded in the Payroll Engine.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from payroll.models import (
    AttendanceDeductionPolicy,
    ContributionRule,
    LeavePayrollImpact,
    OvertimeRule,
    OvertimeRuleSet,
    TaxBracket,
    TaxRuleSet,
)


class Command(BaseCommand):
    help = 'Seed configurable Ethiopian tax brackets, pension, OT rules, and leave impacts'

    def handle(self, *args, **options):
        self.seed_tax()
        self.seed_overtime()
        self.seed_deduction_policy()
        self.seed_leave_impacts()
        self.stdout.write(self.style.SUCCESS('Ethiopian payroll configuration seeded.'))

    def seed_tax(self):
        rule_set, created = TaxRuleSet.objects.get_or_create(
            name='Ethiopia Employment Income Tax',
            defaults={
                'country_code': 'ET',
                'currency': 'ETB',
                'description': (
                    'Progressive employment income tax brackets for Ethiopia. '
                    'Update bracket rows when regulations change — no code deploy required.'
                ),
                'is_default': True,
                'is_active': True,
                'effective_from': timezone.localdate().replace(month=1, day=1),
            },
        )
        if not created and not rule_set.is_default:
            rule_set.is_default = True
            rule_set.save(update_fields=['is_default'])

        # Reference brackets commonly used for Ethiopian employment income tax.
        # Administrators must verify against current law and update via admin.
        brackets = [
            (0, Decimal('0'), Decimal('600'), Decimal('0'), Decimal('0')),
            (1, Decimal('601'), Decimal('1650'), Decimal('10'), Decimal('60')),
            (2, Decimal('1651'), Decimal('3200'), Decimal('15'), Decimal('142.50')),
            (3, Decimal('3201'), Decimal('5250'), Decimal('20'), Decimal('302.50')),
            (4, Decimal('5251'), Decimal('7800'), Decimal('25'), Decimal('565')),
            (5, Decimal('7801'), Decimal('10900'), Decimal('30'), Decimal('955')),
            (6, Decimal('10901'), None, Decimal('35'), Decimal('1500')),
        ]
        if not rule_set.brackets.exists():
            TaxBracket.objects.bulk_create([
                TaxBracket(
                    rule_set=rule_set,
                    order=order,
                    min_income=lo,
                    max_income=hi,
                    rate_percent=rate,
                    deduction_constant=const,
                )
                for order, lo, hi, rate, const in brackets
            ])

        contributions = [
            (
                ContributionRule.ContributionType.PENSION_EMPLOYEE,
                'Employee Pension Contribution',
                Decimal('7'),
                ContributionRule.BaseAmount.BASIC,
                False,
            ),
            (
                ContributionRule.ContributionType.PENSION_EMPLOYER,
                'Employer Pension Contribution',
                Decimal('11'),
                ContributionRule.BaseAmount.BASIC,
                True,
            ),
        ]
        for ctype, name, rate, base, employer in contributions:
            ContributionRule.objects.get_or_create(
                rule_set=rule_set,
                contribution_type=ctype,
                defaults={
                    'name': name,
                    'rate_percent': rate,
                    'base_amount': base,
                    'is_employer_paid': employer,
                    'is_active': True,
                },
            )
        self.stdout.write(f'Tax rule set: {rule_set.name}')

    def seed_overtime(self):
        rule_set, _ = OvertimeRuleSet.objects.get_or_create(
            name='Standard Ethiopian OT Multipliers',
            defaults={
                'description': 'Configurable weekday/weekend/holiday/night overtime multipliers.',
                'is_default': True,
                'is_active': True,
            },
        )
        defaults = [
            (OvertimeRule.OvertimeType.WEEKDAY, Decimal('1.50')),
            (OvertimeRule.OvertimeType.WEEKEND, Decimal('2.00')),
            (OvertimeRule.OvertimeType.HOLIDAY, Decimal('2.50')),
            (OvertimeRule.OvertimeType.NIGHT, Decimal('1.75')),
        ]
        for ot_type, mult in defaults:
            OvertimeRule.objects.get_or_create(
                rule_set=rule_set,
                overtime_type=ot_type,
                defaults={'multiplier': mult, 'is_active': True},
            )
        self.stdout.write(f'Overtime rule set: {rule_set.name}')

    def seed_deduction_policy(self):
        AttendanceDeductionPolicy.objects.get_or_create(
            name='Standard Attendance Deduction',
            defaults={
                'description': 'Deduct missing hours and unauthorized absences from salary.',
                'is_default': True,
                'is_active': True,
                'deduct_missing_hours': True,
                'missing_hour_rate_source': 'BASIC_DIV_EXPECTED',
                'absent_day_deduction_rate': Decimal('1.00'),
                'unpaid_leave_deducts': True,
                'grace_missing_minutes': 15,
            },
        )

    def seed_leave_impacts(self):
        defaults = [
            ('ANNUAL', True, Decimal('100')),
            ('SICK', True, Decimal('100')),
            ('PERSONAL', True, Decimal('100')),
            ('UNPAID', False, Decimal('0')),
            ('MATERNITY', True, Decimal('100')),
            ('PATERNITY', True, Decimal('100')),
            ('BEREAVEMENT', True, Decimal('100')),
            ('COMPOFF', True, Decimal('100')),
            ('PUBLIC_HOLIDAY', True, Decimal('100')),
            ('COMPANY_HOLIDAY', True, Decimal('100')),
            ('WEEKEND', True, Decimal('100')),
        ]
        for leave_type, is_paid, pct in defaults:
            LeavePayrollImpact.objects.get_or_create(
                leave_type=leave_type,
                defaults={
                    'is_paid': is_paid,
                    'pay_percentage': pct,
                    'affects_attendance_bonus': leave_type in {'UNPAID', 'PERSONAL'},
                },
            )
