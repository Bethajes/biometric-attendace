import csv
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView
from django.views.generic.list import ListView

from attendance.models import Employee
from attendance.views import EnterpriseContextMixin, EnterpriseListMixin
from organizations.models import Department

from .forms import (
    AllowanceForm,
    ApprovalActionForm,
    BonusForm,
    DeductionForm,
    PayrollPeriodForm,
    PayrollProcessForm,
    SalaryProfileForm,
)
from .models import (
    Allowance,
    Bonus,
    Deduction,
    Payroll,
    PayrollApproval,
    PayrollAudit,
    PayrollPeriod,
    Payslip,
    SalaryProfile,
)
from .services.approval import ApprovalService
from .services.audit import log_payroll_action
from .services.payroll_engine import PayrollEngine, PayrollEngineError
from .services.payslip_generator import PayslipGenerator
from .services.preview_service import PayrollPreviewService


class PayrollNavMixin(EnterpriseContextMixin):
    """Payroll pages reuse the shared enterprise navigation."""

    pass


class PayrollPermissionMixin(UserPassesTestMixin):
    """Restrict payroll screens to staff / users with payroll permissions."""

    permission_required = None

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser or user.is_staff:
            return True
        if self.permission_required:
            return user.has_perm(self.permission_required)
        return user.has_perm('payroll.view_payroll') or user.has_perm('payroll.view_payroll_sensitive')

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={self.request.path}")
        raise PermissionDenied('You are not authorized to access payroll data.')


class PayrollDashboardView(PayrollPermissionMixin, PayrollNavMixin, TemplateView):
    template_name = 'payroll/dashboard.html'
    page_title = 'Payroll Dashboard'
    active_nav = 'payroll'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        profiles_ready = SalaryProfile.objects.filter(is_active=True).count()
        active_employees = Employee.objects.filter(employment_status='ACTIVE').count()
        pending = Payroll.objects.filter(
            status__in=[Payroll.Status.DRAFT, Payroll.Status.HR_REVIEW, Payroll.Status.FINANCE_REVIEW]
        )
        month_payrolls = Payroll.objects.filter(period__year=today.year, period__month=today.month)
        aggregates = month_payrolls.aggregate(
            cost=Sum('net_salary'),
            ot=Sum('total_overtime'),
            bonuses=Sum('total_bonuses'),
        )
        ded_agg = month_payrolls.aggregate(
            company=Sum('total_company_deductions'),
            attendance=Sum('attendance_deductions'),
            government=Sum('total_government_deductions'),
        )
        total_deductions = sum((ded_agg[k] or Decimal('0')) for k in ded_agg)

        context.update({
            'profiles_ready': profiles_ready,
            'employees_missing_profile': max(0, active_employees - profiles_ready),
            'pending_count': pending.count(),
            'pending_approvals': PayrollApproval.objects.select_related(
                'actor', 'period', 'payroll__employee'
            )[:8],
            'monthly_cost': aggregates['cost'] or Decimal('0'),
            'overtime_cost': aggregates['ot'] or Decimal('0'),
            'bonus_total': aggregates['bonuses'] or Decimal('0'),
            'deduction_total': total_deductions,
            'periods': PayrollPeriod.objects.all()[:6],
            'recent_payrolls': Payroll.objects.select_related('employee', 'period')[:10],
            'status_breakdown': list(
                month_payrolls.values('status').annotate(total=Count('id')).order_by('status')
            ),
            'today': today,
        })
        return context


class SalaryProfileListView(PayrollPermissionMixin, PayrollNavMixin, EnterpriseListMixin):
    model = SalaryProfile
    template_name = 'payroll/salary_list.html'
    page_title = 'Employee Salary Profiles'
    active_nav = 'payroll_salaries'
    search_fields = [
        'employee__first_name', 'employee__last_name',
        'employee__organization_id', 'bank_account_number',
    ]
    export_fields = [
        ('employee__organization_id', 'Employee ID'),
        ('employee__full_name', 'Employee'),
        ('payment_type', 'Payment Type'),
        ('basic_salary', 'Basic'),
        ('gross_salary', 'Gross'),
        ('currency', 'Currency'),
        ('is_active', 'Active'),
    ]
    export_filename = 'salary-profiles'
    default_ordering = 'employee__first_name'

    def get_queryset(self):
        qs = super().get_queryset().select_related('employee', 'employee__department')
        dept = self.request.GET.get('department')
        if dept:
            qs = qs.filter(employee__department_id=dept)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['departments'] = Department.objects.filter(is_active=True)
        return context


class SalaryProfileDetailView(PayrollPermissionMixin, PayrollNavMixin, DetailView):
    model = SalaryProfile
    template_name = 'payroll/salary_detail.html'
    page_title = 'Salary Profile'
    active_nav = 'payroll_salaries'


class SalaryProfileCreateView(PayrollPermissionMixin, PayrollNavMixin, CreateView):
    model = SalaryProfile
    form_class = SalaryProfileForm
    template_name = 'payroll/salary_form.html'
    page_title = 'Add Salary Profile'
    active_nav = 'payroll_salaries'
    success_url = reverse_lazy('payroll_salary_list')
    permission_required = 'payroll.add_salaryprofile'

    def get_initial(self):
        initial = super().get_initial()
        initial['days_per_week'] = 5
        initial['expected_daily_hours'] = 8
        initial['break_duration'] = 0
        initial['payment_type'] = 'MONTHLY'
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        log_payroll_action(
            action='CREATE',
            summary=f'Created salary profile for {self.object.employee}',
            request=self.request,
            entity_type='SalaryProfile',
            entity_id=self.object.pk,
        )
        messages.success(self.request, 'Salary profile created.')
        return response


class SalaryProfileUpdateView(PayrollPermissionMixin, PayrollNavMixin, UpdateView):
    model = SalaryProfile
    form_class = SalaryProfileForm
    template_name = 'payroll/salary_form.html'
    page_title = 'Edit Salary Profile'
    active_nav = 'payroll_salaries'
    success_url = reverse_lazy('payroll_salary_list')
    permission_required = 'payroll.change_salaryprofile'

    def form_valid(self, form):
        response = super().form_valid(form)
        log_payroll_action(
            action='UPDATE',
            summary=f'Updated salary profile for {self.object.employee}',
            request=self.request,
            entity_type='SalaryProfile',
            entity_id=self.object.pk,
        )
        messages.success(self.request, 'Salary profile updated.')
        return response


class PayrollPeriodListView(PayrollPermissionMixin, PayrollNavMixin, EnterpriseListMixin):
    model = PayrollPeriod
    template_name = 'payroll/period_list.html'
    page_title = 'Payroll Periods'
    active_nav = 'payroll'
    search_fields = ['name']
    export_fields = [
        ('name', 'Name'), ('year', 'Year'), ('month', 'Month'),
        ('start_date', 'Start'), ('end_date', 'End'), ('status', 'Status'),
    ]
    export_filename = 'payroll-periods'
    default_ordering = '-year'


class PayrollPeriodCreateView(PayrollPermissionMixin, PayrollNavMixin, CreateView):
    model = PayrollPeriod
    form_class = PayrollPeriodForm
    template_name = 'attendance/form.html'
    page_title = 'Create Payroll Period'
    active_nav = 'payroll'
    success_url = reverse_lazy('payroll_period_list')
    permission_required = 'payroll.add_payrollperiod'

    def form_valid(self, form):
        form.instance.created_by = self.request.user if self.request.user.is_authenticated else None
        response = super().form_valid(form)
        messages.success(self.request, f'Period {self.object} created.')
        return response


class PayrollPeriodDetailView(PayrollPermissionMixin, PayrollNavMixin, DetailView):
    model = PayrollPeriod
    template_name = 'payroll/period_detail.html'
    page_title = 'Payroll Period'
    active_nav = 'payroll'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payrolls = self.object.payrolls.select_related('employee', 'employee__department')
        context['payrolls'] = payrolls
        context['process_form'] = PayrollProcessForm()
        context['approval_form'] = ApprovalActionForm()
        totals = payrolls.aggregate(
            gross=Sum('gross_salary'),
            net=Sum('net_salary'),
            tax=Sum('income_tax'),
            ot=Sum('total_overtime'),
            bonuses=Sum('total_bonuses'),
        )
        for key, value in totals.items():
            totals[key] = value or Decimal('0')
        context['totals'] = totals
        return context


class PayrollProcessView(PayrollPermissionMixin, View):
    permission_required = 'payroll.process_payroll_period'

    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        form = PayrollProcessForm(request.POST)
        employees = Employee.objects.filter(employment_status='ACTIVE').select_related('salary_profile')
        if form.is_valid() and form.cleaned_data.get('department'):
            employees = employees.filter(department=form.cleaned_data['department'])
        replace = True
        if form.is_valid():
            replace = form.cleaned_data.get('replace_existing', True)
        try:
            results = PayrollEngine().calculate_period(
                period,
                employees=employees,
                actor=request.user,
                request=request,
                replace_existing=replace,
            )
            messages.success(request, f'Calculated payroll for {len(results)} employees.')
        except PayrollEngineError as exc:
            messages.error(request, str(exc))
        return redirect('payroll_period_detail', pk=pk)


class PayrollListView(PayrollPermissionMixin, PayrollNavMixin, EnterpriseListMixin):
    model = Payroll
    template_name = 'payroll/payroll_list.html'
    page_title = 'Employee Payroll'
    active_nav = 'payroll'
    search_fields = [
        'employee__first_name', 'employee__last_name', 'employee__organization_id',
    ]
    export_fields = [
        ('employee__organization_id', 'Employee ID'),
        ('employee__full_name', 'Employee'),
        ('period__name', 'Period'),
        ('status', 'Status'),
        ('gross_salary', 'Gross'),
        ('income_tax', 'Tax'),
        ('net_salary', 'Net'),
        ('worked_hours', 'Worked Hours'),
        ('expected_hours', 'Expected Hours'),
    ]
    export_filename = 'payroll'
    default_ordering = '-period__year'

    def get_queryset(self):
        qs = super().get_queryset().select_related('employee', 'period', 'employee__department')
        period = self.request.GET.get('period')
        status = self.request.GET.get('status')
        department = self.request.GET.get('department')
        if period:
            qs = qs.filter(period_id=period)
        if status:
            qs = qs.filter(status=status)
        if department:
            qs = qs.filter(employee__department_id=department)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['periods'] = PayrollPeriod.objects.all()[:24]
        context['departments'] = Department.objects.filter(is_active=True)
        context['status_choices'] = Payroll.Status.choices
        return context

    def export_response(self, export_format):
        log_payroll_action(
            action='EXPORT',
            summary=f'Exported payroll list as {export_format}',
            request=self.request,
            entity_type='Payroll',
        )
        return super().export_response(export_format)


class PayrollDetailView(PayrollPermissionMixin, PayrollNavMixin, DetailView):
    model = Payroll
    template_name = 'payroll/payroll_detail.html'
    page_title = 'Payroll Detail'
    active_nav = 'payroll'

    def get_queryset(self):
        return Payroll.objects.select_related(
            'employee', 'period', 'salary_profile', 'employee__department'
        ).prefetch_related('items', 'approvals')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['approval_form'] = ApprovalActionForm()
        context['earnings'] = self.object.items.filter(direction='EARNING')
        context['deductions'] = self.object.items.filter(direction='DEDUCTION')
        context['employer_items'] = self.object.items.filter(direction='EMPLOYER')
        return context


class PayrollApprovalActionView(PayrollPermissionMixin, View):
    permission_required = 'payroll.approve_payroll'

    def post(self, request, pk):
        payroll = get_object_or_404(Payroll, pk=pk)
        action = request.POST.get('action')
        form = ApprovalActionForm(request.POST)
        comments = form.cleaned_data.get('comments', '') if form.is_valid() else ''
        service = ApprovalService()
        try:
            handlers = {
                'submit': service.submit_for_hr,
                'hr_approve': service.hr_approve,
                'finance_approve': service.finance_approve,
                'lock': service.lock_payroll,
                'unlock': service.unlock_payroll,
                'pay': service.mark_paid,
                'reject': service.reject,
                'advance': service.advance_payroll,
            }
            handler = handlers.get(action)
            if not handler:
                messages.error(request, 'Unknown approval action.')
            else:
                handler(payroll, request.user, comments=comments, request=request)
                messages.success(request, f'Payroll updated: {payroll.get_status_display()}.')
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
        return redirect('payroll_detail', pk=pk)


class PeriodApprovalActionView(PayrollPermissionMixin, View):
    permission_required = 'payroll.approve_payroll'

    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        action = request.POST.get('action')
        form = ApprovalActionForm(request.POST)
        comments = form.cleaned_data.get('comments', '') if form.is_valid() else ''
        service = ApprovalService()
        try:
            if action == 'advance':
                service.advance_period(period, request.user, comments=comments, request=request)
            elif action == 'unlock':
                service.unlock_period(period, request.user, comments=comments, request=request)
            elif action == 'payslips':
                slips = PayslipGenerator().generate_for_period(
                    period, actor=request.user, request=request
                )
                messages.success(request, f'Generated {len(slips)} payslips.')
                return redirect('payroll_period_detail', pk=pk)
            else:
                messages.error(request, 'Unknown period action.')
                return redirect('payroll_period_detail', pk=pk)
            messages.success(request, f'Period status: {period.get_status_display()}.')
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
        return redirect('payroll_period_detail', pk=pk)


class PayslipDetailView(PayrollPermissionMixin, PayrollNavMixin, DetailView):
    model = Payslip
    template_name = 'payroll/payslip.html'
    page_title = 'Payslip'
    active_nav = 'payroll'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['snapshot'] = self.object.snapshot_json or {}
        context['print_mode'] = self.request.GET.get('print') == '1'
        log_payroll_action(
            action='VIEW',
            summary=f'Viewed payslip {self.object.payslip_number}',
            request=self.request,
            entity_type='Payslip',
            entity_id=self.object.pk,
            payroll=self.object.payroll,
            period=self.object.payroll.period,
        )
        return context


class BonusListView(PayrollPermissionMixin, PayrollNavMixin, EnterpriseListMixin):
    model = Bonus
    template_name = 'payroll/bonus_list.html'
    page_title = 'Bonuses'
    active_nav = 'payroll'
    search_fields = ['employee__first_name', 'employee__last_name', 'reason']
    export_fields = [
        ('employee__full_name', 'Employee'), ('bonus_type', 'Type'),
        ('amount', 'Amount'), ('status', 'Status'), ('bonus_date', 'Date'),
    ]
    export_filename = 'bonuses'


class BonusCreateView(PayrollPermissionMixin, PayrollNavMixin, CreateView):
    model = Bonus
    form_class = BonusForm
    template_name = 'attendance/form.html'
    page_title = 'Add Bonus'
    active_nav = 'payroll'
    success_url = reverse_lazy('payroll_bonus_list')

    def form_valid(self, form):
        if form.cleaned_data.get('status') == Bonus.Status.APPROVED:
            form.instance.approved_by = self.request.user
            form.instance.approved_at = timezone.now()
        messages.success(self.request, 'Bonus saved.')
        return super().form_valid(form)


class DeductionListView(PayrollPermissionMixin, PayrollNavMixin, EnterpriseListMixin):
    model = Deduction
    template_name = 'payroll/deduction_list.html'
    page_title = 'Deductions & Penalties'
    active_nav = 'payroll'
    search_fields = ['employee__first_name', 'employee__last_name', 'reason']
    export_fields = [
        ('employee__full_name', 'Employee'), ('deduction_type', 'Type'),
        ('amount', 'Amount'), ('status', 'Status'), ('deduction_date', 'Date'),
    ]
    export_filename = 'deductions'


class DeductionCreateView(PayrollPermissionMixin, PayrollNavMixin, CreateView):
    model = Deduction
    form_class = DeductionForm
    template_name = 'attendance/form.html'
    page_title = 'Add Deduction'
    active_nav = 'payroll'
    success_url = reverse_lazy('payroll_deduction_list')

    def form_valid(self, form):
        if form.cleaned_data.get('status') == Deduction.Status.APPROVED:
            form.instance.approved_by = self.request.user
            form.instance.approved_at = timezone.now()
        messages.success(self.request, 'Deduction saved.')
        return super().form_valid(form)


class AllowanceListView(PayrollPermissionMixin, PayrollNavMixin, EnterpriseListMixin):
    model = Allowance
    template_name = 'payroll/allowance_list.html'
    page_title = 'Allowances'
    active_nav = 'payroll'
    search_fields = ['employee__first_name', 'employee__last_name', 'name']
    export_fields = [
        ('employee__full_name', 'Employee'), ('allowance_type', 'Type'),
        ('name', 'Name'), ('amount', 'Amount'), ('is_recurring', 'Recurring'),
    ]
    export_filename = 'allowances'


class AllowanceCreateView(PayrollPermissionMixin, PayrollNavMixin, CreateView):
    model = Allowance
    form_class = AllowanceForm
    template_name = 'attendance/form.html'
    page_title = 'Add Allowance'
    active_nav = 'payroll'
    success_url = reverse_lazy('payroll_allowance_list')


class PayrollReportsView(PayrollPermissionMixin, PayrollNavMixin, TemplateView):
    template_name = 'payroll/reports.html'
    page_title = 'Payroll Reports'
    active_nav = 'payroll'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period_id = self.request.GET.get('period')
        periods = PayrollPeriod.objects.all()[:24]
        context['periods'] = periods
        period = None
        if period_id:
            period = PayrollPeriod.objects.filter(pk=period_id).first()
        elif periods:
            period = periods[0]
        context['selected_period'] = period
        if period:
            payrolls = period.payrolls.select_related('employee', 'employee__department')
            context['payrolls'] = payrolls
            context['by_department'] = list(
                payrolls.values('employee__department__name').annotate(
                    headcount=Count('id'),
                    gross=Sum('gross_salary'),
                    net=Sum('net_salary'),
                    tax=Sum('income_tax'),
                    pension=Sum('pension_employee'),
                    overtime=Sum('total_overtime'),
                ).order_by('employee__department__name')
            )
            context['totals'] = payrolls.aggregate(
                gross=Sum('gross_salary'),
                net=Sum('net_salary'),
                tax=Sum('income_tax'),
                pension=Sum('pension_employee'),
                employer_pension=Sum('pension_employer'),
                overtime=Sum('total_overtime'),
                bonuses=Sum('total_bonuses'),
                deductions=Sum('total_company_deductions'),
                attendance_deductions=Sum('attendance_deductions'),
            )
        return context


class PayrollAuditListView(PayrollPermissionMixin, PayrollNavMixin, EnterpriseListMixin):
    model = PayrollAudit
    template_name = 'payroll/audit_list.html'
    page_title = 'Payroll Audit Log'
    active_nav = 'payroll'
    search_fields = ['summary', 'entity_type', 'actor__username']
    export_fields = [
        ('created_at', 'When'), ('action', 'Action'), ('summary', 'Summary'),
        ('actor__username', 'Actor'), ('entity_type', 'Entity'),
    ]
    export_filename = 'payroll-audit'
    default_ordering = '-created_at'
    permission_required = 'payroll.view_payrollaudit'


class PayrollPreviewJsonView(PayrollPermissionMixin, View):
    """AJAX endpoint for live payroll preview during salary editing."""

    def get(self, request):
        basic_salary = Decimal(request.GET.get('basic_salary', '0'))
        worked_hours = Decimal(request.GET.get('worked_hours', '0'))
        expected_hours = Decimal(request.GET.get('expected_hours', '0'))
        hourly_rate = Decimal(request.GET.get('hourly_rate', '0'))
        daily_rate = Decimal(request.GET.get('daily_rate', '0'))
        overtime_hours = Decimal(request.GET.get('overtime_hours', '0'))
        overtime_multiplier = Decimal(request.GET.get('overtime_multiplier', '1.50'))
        total_bonuses = Decimal(request.GET.get('total_bonuses', '0'))
        total_allowances = Decimal(request.GET.get('total_allowances', '0'))
        total_company_deductions = Decimal(request.GET.get('total_company_deductions', '0'))
        attendance_deductions = Decimal(request.GET.get('attendance_deductions', '0'))
        currency = request.GET.get('currency', 'ETB')
        tax_rule_set_id = request.GET.get('tax_rule_set_id')
        overtime_rule_set_id = request.GET.get('overtime_rule_set_id')
        pension_eligible = request.GET.get('pension_eligible', 'true') == 'true'
        tax_exempt = request.GET.get('tax_exempt', 'false') == 'true'

        if expected_hours <= 0:
            expected_hours = Decimal('160')
        if overtime_rule_set_id:
            from payroll.models import OvertimeRule
            rule = OvertimeRule.objects.filter(
                rule_set_id=overtime_rule_set_id, overtime_type='WEEKDAY', is_active=True
            ).first()
            if rule and rule.multiplier:
                overtime_multiplier = rule.multiplier

        service = PayrollPreviewService()
        result = service.preview(
            basic_salary=basic_salary,
            worked_hours=worked_hours,
            expected_hours=expected_hours,
            hourly_rate=hourly_rate,
            daily_rate=daily_rate,
            overtime_hours=overtime_hours,
            overtime_multiplier=overtime_multiplier,
            total_bonuses=total_bonuses,
            total_allowances=total_allowances,
            total_company_deductions=total_company_deductions,
            attendance_deductions=attendance_deductions,
            currency=currency,
            tax_rule_set_id=int(tax_rule_set_id) if tax_rule_set_id else None,
            pension_eligible=pension_eligible,
            tax_exempt=tax_exempt,
        )
        return JsonResponse({'success': True, 'data': service.to_dict(result)})
