"""
Configurable Tax Engine.

All rates and brackets come from TaxRuleSet / TaxBracket / ContributionRule tables.
No Ethiopian (or any) tax rates are hardcoded in calculation logic.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from payroll.models import ContributionRule, TaxBracket, TaxRuleSet


TWOPLACES = Decimal('0.01')
HUNDRED = Decimal('100')


@dataclass
class ContributionResult:
    name: str
    contribution_type: str
    amount: Decimal
    is_employer_paid: bool
    rate_percent: Decimal


@dataclass
class TaxComputation:
    taxable_income: Decimal
    income_tax: Decimal
    bracket_label: str = ''
    employee_contributions: list = field(default_factory=list)
    employer_contributions: list = field(default_factory=list)
    total_employee_government: Decimal = Decimal('0.00')
    total_employer_government: Decimal = Decimal('0.00')
    pension_employee: Decimal = Decimal('0.00')
    pension_employer: Decimal = Decimal('0.00')
    other_government: Decimal = Decimal('0.00')


class TaxEngine:
    def resolve_rule_set(self, rule_set: Optional[TaxRuleSet] = None) -> Optional[TaxRuleSet]:
        if rule_set and rule_set.is_active:
            return rule_set
        return (
            TaxRuleSet.objects.filter(is_active=True, is_default=True)
            .prefetch_related('brackets', 'contributions')
            .first()
            or TaxRuleSet.objects.filter(is_active=True)
            .prefetch_related('brackets', 'contributions')
            .first()
        )

    def calculate_income_tax(self, taxable_income: Decimal, rule_set: TaxRuleSet) -> tuple[Decimal, str]:
        taxable = max(Decimal('0.00'), Decimal(taxable_income)).quantize(TWOPLACES)
        brackets = list(rule_set.brackets.all())
        if not brackets:
            return Decimal('0.00'), 'No brackets configured'

        for bracket in brackets:
            upper = bracket.max_income
            in_range = taxable >= bracket.min_income and (upper is None or taxable <= upper)
            if not in_range:
                continue
            # Ethiopian-style: tax = (income * rate%) - deduction_constant
            tax = (taxable * bracket.rate_percent / HUNDRED) - bracket.deduction_constant
            tax = max(Decimal('0.00'), tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            label = f'{bracket.min_income}–{upper or "∞"} @ {bracket.rate_percent}%'
            return tax, label

        # Fallback: use highest bracket if income exceeds all configured maxes
        last = brackets[-1]
        tax = (taxable * last.rate_percent / HUNDRED) - last.deduction_constant
        tax = max(Decimal('0.00'), tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return tax, f'Fallback {last.rate_percent}%'

    def calculate_contributions(
        self,
        rule_set: TaxRuleSet,
        basic_salary: Decimal,
        gross_salary: Decimal,
        taxable_income: Decimal,
        pension_eligible: bool = True,
    ) -> list[ContributionResult]:
        results = []
        for rule in rule_set.contributions.filter(is_active=True):
            if 'PENSION' in rule.contribution_type and not pension_eligible:
                continue
            base = {
                ContributionRule.BaseAmount.BASIC: basic_salary,
                ContributionRule.BaseAmount.GROSS: gross_salary,
                ContributionRule.BaseAmount.TAXABLE: taxable_income,
            }.get(rule.base_amount, basic_salary)
            amount = (Decimal(base) * rule.rate_percent / HUNDRED).quantize(
                TWOPLACES, rounding=ROUND_HALF_UP
            )
            results.append(
                ContributionResult(
                    name=rule.name,
                    contribution_type=rule.contribution_type,
                    amount=amount,
                    is_employer_paid=rule.is_employer_paid,
                    rate_percent=rule.rate_percent,
                )
            )
        return results

    def compute(
        self,
        taxable_income: Decimal,
        basic_salary: Decimal,
        gross_salary: Decimal,
        rule_set: Optional[TaxRuleSet] = None,
        rule_set_id: Optional[int] = None,
        tax_exempt: bool = False,
        pension_eligible: bool = True,
    ) -> TaxComputation:
        if rule_set_id and not rule_set:
            rule_set = TaxRuleSet.objects.filter(pk=rule_set_id, is_active=True).prefetch_related('brackets', 'contributions').first()
        resolved = self.resolve_rule_set(rule_set)
        taxable = max(Decimal('0.00'), Decimal(taxable_income)).quantize(TWOPLACES)
        result = TaxComputation(taxable_income=taxable, income_tax=Decimal('0.00'))

        if not resolved:
            return result

        if not tax_exempt:
            result.income_tax, result.bracket_label = self.calculate_income_tax(taxable, resolved)

        contributions = self.calculate_contributions(
            resolved, basic_salary, gross_salary, taxable, pension_eligible=pension_eligible
        )
        for contrib in contributions:
            if contrib.is_employer_paid:
                result.employer_contributions.append(contrib)
                result.total_employer_government += contrib.amount
                if 'PENSION' in contrib.contribution_type:
                    result.pension_employer += contrib.amount
            else:
                result.employee_contributions.append(contrib)
                result.total_employee_government += contrib.amount
                if 'PENSION' in contrib.contribution_type:
                    result.pension_employee += contrib.amount
                elif contrib.contribution_type == ContributionRule.ContributionType.OTHER_GOVERNMENT:
                    result.other_government += contrib.amount

        result.total_employee_government += result.income_tax
        return result
