"""
Payslip Generator — builds Payslip snapshots from calculated Payroll rows.
"""

from django.db import transaction
from django.utils import timezone

from payroll.models import Payslip, Payroll, PayrollItem
from payroll.services.audit import log_payroll_action


class PayslipGenerator:
    def generate(self, payroll: Payroll, actor=None, request=None) -> Payslip:
        with transaction.atomic():
            payslip, _created = Payslip.objects.get_or_create(
                payroll=payroll,
                defaults=self._build_defaults(payroll),
            )
            if not _created:
                for key, value in self._build_defaults(payroll).items():
                    setattr(payslip, key, value)
                payslip.save()

            log_payroll_action(
                action='GENERATE_PAYSLIP',
                summary=f'Generated payslip {payslip.payslip_number}',
                actor=actor,
                entity_type='Payslip',
                entity_id=payslip.pk,
                period=payroll.period,
                payroll=payroll,
                request=request,
            )
            return payslip

    def generate_for_period(self, period, actor=None, request=None) -> list[Payslip]:
        slips = []
        for payroll in period.payrolls.exclude(status=Payroll.Status.CANCELLED):
            slips.append(self.generate(payroll, actor=actor, request=request))
        return slips

    def _build_defaults(self, payroll: Payroll) -> dict:
        employee = payroll.employee
        company = None
        if employee.department_id and employee.department.company_id:
            company = employee.department.company
        elif payroll.period.company_id:
            company = payroll.period.company

        earnings = []
        deductions = []
        employer = []
        for item in payroll.items.all():
            row = {
                'type': item.item_type,
                'description': item.description,
                'quantity': str(item.quantity),
                'rate': str(item.rate),
                'amount': str(item.amount),
            }
            if item.direction == PayrollItem.Direction.EARNING:
                earnings.append(row)
            elif item.direction == PayrollItem.Direction.EMPLOYER:
                employer.append(row)
            else:
                deductions.append(row)

        payslip_number = f'PS-{payroll.period.year}{payroll.period.month:02d}-{employee.organization_id}'
        return {
            'payslip_number': payslip_number,
            'company_name': company.name if company else 'SmartAttend Enterprise',
            'company_address': company.address if company else '',
            'company_tax_id': company.tax_id if company else '',
            'employee_name': employee.full_name,
            'employee_id': employee.organization_id,
            'department_name': employee.department.name if employee.department_id else '',
            'job_title': employee.job_title,
            'period_label': str(payroll.period),
            'issued_at': timezone.now(),
            'qr_payload': '',
            'digital_signature': '',
            'snapshot_json': {
                'currency': payroll.currency,
                'basic_salary': str(payroll.basic_salary),
                'total_allowances': str(payroll.total_allowances),
                'total_bonuses': str(payroll.total_bonuses),
                'total_overtime': str(payroll.total_overtime),
                'gross_salary': str(payroll.gross_salary),
                'taxable_income': str(payroll.taxable_income),
                'income_tax': str(payroll.income_tax),
                'pension_employee': str(payroll.pension_employee),
                'pension_employer': str(payroll.pension_employer),
                'total_government_deductions': str(payroll.total_government_deductions),
                'total_company_deductions': str(payroll.total_company_deductions),
                'attendance_deductions': str(payroll.attendance_deductions),
                'total_penalties': str(payroll.total_penalties),
                'net_salary': str(payroll.net_salary),
                'expected_hours': str(payroll.expected_hours),
                'worked_hours': str(payroll.worked_hours),
                'missing_hours': str(payroll.missing_hours),
                'overtime_hours': str(payroll.overtime_hours),
                'late_minutes': payroll.late_minutes,
                'early_leave_minutes': payroll.early_leave_minutes,
                'present_days': str(payroll.present_days),
                'absent_days': str(payroll.absent_days),
                'paid_leave_days': str(payroll.paid_leave_days),
                'unpaid_leave_days': str(payroll.unpaid_leave_days),
                'holiday_days': str(payroll.holiday_days),
                'payment_method': payroll.payment_method,
                'bank_account_number': payroll.bank_account_number,
                'earnings': earnings,
                'deductions': deductions,
                'employer_contributions': employer,
            },
        }
