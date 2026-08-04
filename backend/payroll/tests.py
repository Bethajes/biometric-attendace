from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from attendance.models import AttendanceRecord, Employee
from organizations.models import Company, Department
from payroll.models import (
    AttendanceDeductionPolicy,
    ContributionRule,
    LeavePayrollImpact,
    OvertimeRule,
    OvertimeRuleSet,
    PayrollPeriod,
    SalaryProfile,
    TaxBracket,
    TaxRuleSet,
)
from payroll.services.payroll_engine import PayrollEngine, PayrollEngineError
from payroll.services.preview_service import PayrollPreviewService
from payroll.services.tax_engine import TaxEngine


User = get_user_model()


def create_ethiopian_defaults():
    rule_set, _ = TaxRuleSet.objects.get_or_create(
        name='Test ET Tax', defaults=dict(
            country_code='ET', currency='ETB', is_default=True,
        )
    )
    for order, lo, hi, rate, ded in [
        (0, Decimal('0'), Decimal('600'), Decimal('0'), Decimal('0')),
        (1, Decimal('601'), Decimal('1650'), Decimal('10'), Decimal('60')),
        (2, Decimal('1651'), Decimal('3200'), Decimal('15'), Decimal('142.50')),
        (3, Decimal('3201'), None, Decimal('20'), Decimal('302.50')),
    ]:
        TaxBracket.objects.get_or_create(
            rule_set=rule_set, order=order,
            defaults=dict(min_income=lo, max_income=hi, rate_percent=rate, deduction_constant=ded),
        )
    for ctype, name, rate, base in [
        ('PENSION_EMPLOYEE', 'Pension (Employee)', Decimal('7'), 'BASIC'),
        ('PENSION_EMPLOYER', 'Pension (Employer)', Decimal('11'), 'BASIC'),
    ]:
        ContributionRule.objects.get_or_create(
            rule_set=rule_set, contribution_type=ctype,
            defaults=dict(name=name, rate_percent=rate, base_amount=base, is_employer_paid=(ctype == 'PENSION_EMPLOYER')),
        )
    for lt, paid, pct in [
        ('ANNUAL', True, Decimal('100')), ('SICK', True, Decimal('100')),
        ('PERSONAL', True, Decimal('100')), ('UNPAID', False, Decimal('0')),
        ('MATERNITY', True, Decimal('100')), ('BEREAVEMENT', True, Decimal('100')),
        ('PUBLIC_HOLIDAY', True, Decimal('100')), ('WEEKEND', False, Decimal('0')),
    ]:
        LeavePayrollImpact.objects.get_or_create(leave_type=lt, defaults=dict(is_paid=paid, pay_percentage=pct))
    ot_set, _ = OvertimeRuleSet.objects.get_or_create(name='Test OT', defaults=dict(is_default=True))
    for otype, mult in [('WEEKDAY', Decimal('1.50')), ('WEEKEND', Decimal('2.00')), ('HOLIDAY', Decimal('2.50'))]:
        OvertimeRule.objects.get_or_create(rule_set=ot_set, overtime_type=otype, defaults=dict(multiplier=mult))
    AttendanceDeductionPolicy.objects.get_or_create(
        name='Test Policy',
        defaults=dict(is_default=True, deduct_missing_hours=True, missing_hour_rate_source='BASIC_DIV_EXPECTED', grace_missing_minutes=15),
    )
    return rule_set


class TaxEngineTests(TestCase):
    def setUp(self):
        self.rule_set = create_ethiopian_defaults()

    def test_progressive_bracket(self):
        tax, label = TaxEngine().calculate_income_tax(Decimal('1000'), self.rule_set)
        self.assertEqual(tax, Decimal('40.00'))
        self.assertIn('10.000%', label)

    def test_bracket_at_edge(self):
        tax, _ = TaxEngine().calculate_income_tax(Decimal('600'), self.rule_set)
        self.assertEqual(tax, Decimal('0.00'))

    def test_high_income_bracket(self):
        tax, _ = TaxEngine().calculate_income_tax(Decimal('10000'), self.rule_set)
        expected = Decimal('10000') * Decimal('0.20') - Decimal('302.50')
        self.assertEqual(tax, expected)

    def test_exempt(self):
        result = TaxEngine().compute(
            taxable_income=Decimal('5000'), basic_salary=Decimal('5000'),
            gross_salary=Decimal('5000'), rule_set=self.rule_set, tax_exempt=True,
        )
        self.assertEqual(result.income_tax, Decimal('0.00'))

    def test_pension_employee(self):
        result = TaxEngine().compute(
            taxable_income=Decimal('10000'), basic_salary=Decimal('10000'),
            gross_salary=Decimal('12000'), rule_set=self.rule_set,
        )
        self.assertEqual(result.pension_employee, Decimal('700.00'))
        self.assertEqual(result.pension_employer, Decimal('1100.00'))

    def test_pension_disabled(self):
        result = TaxEngine().compute(
            taxable_income=Decimal('10000'), basic_salary=Decimal('10000'),
            gross_salary=Decimal('12000'), rule_set=self.rule_set, pension_eligible=False,
        )
        self.assertEqual(result.pension_employee, Decimal('0.00'))
        self.assertEqual(result.pension_employer, Decimal('0.00'))

    def test_no_rules_found(self):
        empty_set = TaxRuleSet.objects.create(
            name='Empty', country_code='XX', currency='USD', is_default=False,
        )
        result = TaxEngine().compute(
            taxable_income=Decimal('5000'), basic_salary=Decimal('5000'),
            gross_salary=Decimal('5000'), rule_set=empty_set,
        )
        self.assertEqual(result.income_tax, Decimal('0.00'))


class PayrollEngineTests(TestCase):
    def setUp(self):
        self.tax_set = create_ethiopian_defaults()
        self.company = Company.objects.create(name='Test Co', slug='test-co', default_currency='ETB')
        self.dept = Department.objects.create(company=self.company, name='Ops', code='OPS')
        self.employee = Employee.objects.create(
            organization_id='E001', first_name='Ada', last_name='Lovelace',
            job_title='Engineer', department=self.dept,
        )
        self.profile = SalaryProfile.objects.create(
            employee=self.employee, basic_salary=Decimal('10000'),
            monthly_salary=Decimal('10000'), gross_salary=Decimal('12000'),
            transport_allowance=Decimal('1000'), housing_allowance=Decimal('1000'),
            expected_daily_hours=Decimal('8'), expected_weekly_hours=Decimal('40'),
            expected_monthly_hours=Decimal('160'), currency='ETB', tax_rule_set=self.tax_set,
        )
        self.today = timezone.localdate()
        start = self.today.replace(day=1)
        self.period = PayrollPeriod.objects.create(
            name=f'{self.today:%B %Y}', year=self.today.year, month=self.today.month,
            start_date=start, end_date=self.today, company=self.company,
        )

    def _create_attendance(self, worked_minutes, date=None):
        d = date or self.today
        AttendanceRecord.objects.create(
            employee=self.employee, date=d,
            status='PRESENT', worked_minutes=worked_minutes,
            first_check_in=timezone.make_aware(
                timezone.datetime(d.year, d.month, d.day, 8, 0)
            ),
            last_check_out=timezone.make_aware(
                timezone.datetime(d.year, d.month, d.day, 8 + worked_minutes // 60, worked_minutes % 60)
            ),
        )

    def test_full_time_employee_gets_full_salary(self):
        for i in range(20):
            d = self.today.replace(day=1) + timezone.timedelta(days=i)
            if d <= self.today:
                self._create_attendance(480, d)
        payroll = PayrollEngine().calculate_employee(self.period, self.employee)
        self.assertIsNotNone(payroll)
        self.assertGreater(payroll.gross_salary, Decimal('0'))
        self.assertGreaterEqual(payroll.net_salary, Decimal('0'))
        self.assertTrue(payroll.items.exists())
        self.assertGreater(payroll.worked_hours, Decimal('0'))

    def test_zero_attendance_means_zero_attendance_salary(self):
        payroll = PayrollEngine().calculate_employee(self.period, self.employee)
        self.assertIsNotNone(payroll)
        self.assertEqual(payroll.basic_salary, Decimal('0.00'))
        self.assertEqual(payroll.worked_hours, Decimal('0'))

    def test_partial_attendance_prorates_basic_salary(self):
        self._create_attendance(480)
        payroll = PayrollEngine().calculate_employee(self.period, self.employee)
        self.assertIsNotNone(payroll)
        expected_hours = self.profile.expected_monthly_hours
        worked_hours = Decimal('8')
        expected_ratio = worked_hours / expected_hours
        expected_salary = (self.profile.basic_salary * expected_ratio).quantize(Decimal('0.01'))
        self.assertEqual(payroll.basic_salary, expected_salary)
        self.assertGreater(payroll.worked_hours, Decimal('0'))

    def test_calculation_with_allowances(self):
        self._create_attendance(480)
        payroll = PayrollEngine().calculate_employee(self.period, self.employee)
        self.assertIn(payroll.total_allowances, (Decimal('2000.00'), Decimal('0.00')))

    def test_multiple_calculations_same_period_replaces(self):
        self._create_attendance(480)
        p1 = PayrollEngine().calculate_employee(self.period, self.employee)
        p2 = PayrollEngine().calculate_employee(self.period, self.employee)
        self.assertEqual(p1.pk, p2.pk)

    def test_calculate_period_returns_list(self):
        self._create_attendance(480)
        results = PayrollEngine().calculate_period(self.period)
        self.assertIsInstance(results, list)

    def test_locked_period_raises_error(self):
        self.period.status = PayrollPeriod.Status.LOCKED
        self.period.save()
        with self.assertRaises(PayrollEngineError):
            PayrollEngine().calculate_period(self.period)


class PayrollPreviewServiceTests(TestCase):
    def setUp(self):
        create_ethiopian_defaults()

    def test_preview_full_attendance(self):
        svc = PayrollPreviewService()
        result = svc.preview(
            basic_salary=Decimal('10000'), worked_hours=Decimal('160'),
            expected_hours=Decimal('160'), total_allowances=Decimal('2000'),
        )
        self.assertEqual(result.attendance_salary, Decimal('10000.00'))
        self.assertEqual(result.attendance_percent, Decimal('100.00'))
        self.assertEqual(result.gross_salary, Decimal('12000.00'))
        self.assertGreater(result.net_salary, Decimal('0'))

    def test_preview_half_attendance(self):
        svc = PayrollPreviewService()
        result = svc.preview(
            basic_salary=Decimal('10000'), worked_hours=Decimal('80'),
            expected_hours=Decimal('160'),
        )
        self.assertEqual(result.attendance_salary, Decimal('5000.00'))
        self.assertEqual(result.attendance_percent, Decimal('50.00'))

    def test_preview_zero_attendance(self):
        svc = PayrollPreviewService()
        result = svc.preview(
            basic_salary=Decimal('10000'), worked_hours=Decimal('0'),
            expected_hours=Decimal('160'),
        )
        self.assertEqual(result.attendance_salary, Decimal('0.00'))
        self.assertEqual(result.net_salary, Decimal('0.00'))

    def test_preview_with_overtime(self):
        svc = PayrollPreviewService()
        result = svc.preview(
            basic_salary=Decimal('10000'), worked_hours=Decimal('160'),
            expected_hours=Decimal('160'), overtime_hours=Decimal('10'),
            overtime_multiplier=Decimal('1.50'), hourly_rate=Decimal('62.50'),
        )
        self.assertGreater(result.overtime_amount, Decimal('0'))
        self.assertEqual(result.overtime_amount, Decimal('937.50'))

    def test_preview_net_salary_never_negative(self):
        svc = PayrollPreviewService()
        result = svc.preview(
            basic_salary=Decimal('1000'), worked_hours=Decimal('0'),
            expected_hours=Decimal('160'), total_company_deductions=Decimal('5000'),
        )
        self.assertEqual(result.net_salary, Decimal('0.00'))

    def test_preview_tax_exempt(self):
        svc = PayrollPreviewService()
        result = svc.preview(
            basic_salary=Decimal('10000'), worked_hours=Decimal('160'),
            expected_hours=Decimal('160'), tax_exempt=True,
        )
        self.assertEqual(result.income_tax, Decimal('0.00'))

    def test_preview_pension_disabled(self):
        svc = PayrollPreviewService()
        result = svc.preview(
            basic_salary=Decimal('10000'), worked_hours=Decimal('160'),
            expected_hours=Decimal('160'), pension_eligible=False,
        )
        self.assertEqual(result.pension_employee, Decimal('0.00'))

    def test_preview_to_dict_serializable(self):
        svc = PayrollPreviewService()
        result = svc.preview(
            basic_salary=Decimal('10000'), worked_hours=Decimal('160'),
            expected_hours=Decimal('160'), total_allowances=Decimal('2000'),
        )
        d = svc.to_dict(result)
        self.assertIn('gross_salary', d)
        self.assertIsInstance(d['gross_salary'], str)
        self.assertEqual(d['gross_salary'], '12000.00')


class PayrollEngineErrorTests(TestCase):
    def test_no_salary_profile_returns_none(self):
        company = Company.objects.create(name='Test Co', slug='test-co')
        dept = Department.objects.create(company=company, name='Ops', code='OPS')
        employee = Employee.objects.create(
            organization_id='E002', first_name='Bob', last_name='Smith',
            job_title='Dev', department=dept,
        )
        period = PayrollPeriod.objects.create(
            name='Test Period', year=2026, month=7,
            start_date=timezone.localdate().replace(day=1),
            end_date=timezone.localdate(), company=company,
        )
        result = PayrollEngine().calculate_employee(period, employee)
        self.assertIsNone(result)
