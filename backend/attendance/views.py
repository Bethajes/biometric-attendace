import csv
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView
from django.views.generic.list import ListView

from .forms import (
    AttendancePolicyForm,
    DepartmentForm,
    EmployeeForm,
    EmployeeScheduleForm,
    HolidayForm,
    LeaveRequestForm,
    OvertimeRequestForm,
    RemoteWorkLogForm,
    ScheduleTemplateForm,
    ShiftForm,
    SiteVisitForm,
)
from organizations.models import Department
from .models import (
    AttendanceLog,
    AttendancePolicy,
    AttendanceRecord,
    Employee,
    EmployeeSchedule,
    EnrollmentRequest,
    Holiday,
    LeaveBalance,
    LeaveRequest,
    Notification,
    OvertimeRequest,
    RemoteWorkLog,
    ScheduleTemplate,
    Shift,
    SiteVisit,
    SystemSetting,
)
from .services.attendance_engine import AttendanceEngine

logger = logging.getLogger(__name__)


class EnterpriseContextMixin:
    page_title = ''
    active_nav = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.page_title
        context['active_nav'] = self.active_nav
        context['nav_items'] = [
            ('dashboard', 'Dashboard', 'dashboard'),
            ('employees', 'Employees', 'employee_list'),
            ('departments', 'Departments', 'department_list'),
            ('schedules', 'Schedules', 'schedule_list'),
            ('templates', 'Templates', 'template_list'),
            ('shifts', 'Shifts', 'shift_list'),
            ('attendance', 'Attendance', 'attendance_records'),
            ('devices', 'Devices', 'device_dashboard'),
            ('leave', 'Leave', 'leave_list'),
            ('holidays', 'Holidays', 'holiday_list'),
            ('overtime', 'Overtime', 'overtime_list'),
            ('remote', 'Remote Work', 'remote_list'),
            ('sites', 'Site Visits', 'site_list'),
            ('policies', 'Policies', 'policy_list'),
            ('reports', 'Reports', 'reports'),
            ('notifications', 'Notifications', 'notification_list'),
            ('roles', 'User Roles', 'user_roles'),
            ('settings', 'Settings', 'system_settings'),
        ]
        return context


class EnterpriseListMixin(EnterpriseContextMixin, ListView):
    paginate_by = 15
    search_fields = []
    default_ordering = '-id'
    export_fields = []
    export_filename = 'export'

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get('q', '').strip()
        if query and self.search_fields:
            condition = Q()
            for field in self.search_fields:
                condition |= Q(**{f'{field}__icontains': query})
            queryset = queryset.filter(condition)
        return queryset.order_by(self.get_ordering())

    def get_ordering(self):
        ordering = self.request.GET.get('sort') or self.default_ordering
        allowed = {field.lstrip('-') for field in self.get_sort_fields()}
        return ordering if ordering.lstrip('-') in allowed else self.default_ordering

    def get_sort_fields(self):
        fields = []
        for field, _label in self.export_fields:
            fields.append(field.split('__')[0])
        return fields + ['id', 'date', 'created_at', 'timestamp', 'name']

    def render_to_response(self, context, **response_kwargs):
        export_format = self.request.GET.get('export')
        if export_format:
            return self.export_response(export_format)
        return super().render_to_response(context, **response_kwargs)

    def export_response(self, export_format):
        rows = self.get_queryset()
        filename = f'{self.export_filename}-{timezone.localdate()}'
        if export_format == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
            writer = csv.writer(response)
            writer.writerow([label for _field, label in self.export_fields])
            for row in rows:
                writer.writerow([self.resolve_attr(row, field) for field, _label in self.export_fields])
            return response
        if export_format in ['excel', 'pdf']:
            content_type = 'application/vnd.ms-excel' if export_format == 'excel' else 'text/html'
            extension = 'xls' if export_format == 'excel' else 'html'
            response = HttpResponse(content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{filename}.{extension}"'
            response.write('<!doctype html><html><head><meta charset="utf-8"><style>body{font-family:Arial,sans-serif}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:8px;text-align:left}th{background:#eef3f7}</style></head><body>')
            response.write(f'<h1>{self.page_title}</h1><table><thead><tr>')
            for _field, label in self.export_fields:
                response.write(f'<th>{label}</th>')
            response.write('</tr></thead><tbody>')
            for row in rows:
                response.write('<tr>')
                for field, _label in self.export_fields:
                    response.write(f'<td>{self.resolve_attr(row, field)}</td>')
                response.write('</tr>')
            response.write('</tbody></table></body></html>')
            return response
        return redirect(self.request.path)

    @staticmethod
    def resolve_attr(obj, path):
        value = obj
        for part in path.split('__'):
            value = getattr(value, part, '')
            if value is None:
                return ''
        if callable(value):
            value = value()
        return value


class DashboardView(EnterpriseContextMixin, TemplateView):
    template_name = 'attendance/dashboard.html'
    page_title = 'Dashboard'
    active_nav = 'dashboard'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        start_week = today - timedelta(days=today.weekday())
        records_today = AttendanceRecord.objects.filter(date=today)
        if not records_today.exists() and AttendanceLog.objects.filter(timestamp__date=today).exists():
            AttendanceEngine().calculate_date(today)
            records_today = AttendanceRecord.objects.filter(date=today)

        context.update({
            'today': today,
            'employee_count': Employee.objects.filter(employment_status=Employee.EmploymentStatus.ACTIVE).count(),
            'department_count': Department.objects.filter(is_active=True).count(),
            'present_count': records_today.filter(status__in=[
                AttendanceRecord.Status.PRESENT,
                AttendanceRecord.Status.LATE,
                AttendanceRecord.Status.EARLY_LEAVE,
                AttendanceRecord.Status.OVERTIME,
            ]).count(),
            'late_count': records_today.filter(status=AttendanceRecord.Status.LATE).count(),
            'absent_count': records_today.filter(status=AttendanceRecord.Status.ABSENT).count(),
            'weekly_overtime': AttendanceRecord.objects.filter(date__gte=start_week).aggregate(
                total=Sum('overtime_minutes')
            )['total'] or 0,
            'recent_logs': AttendanceLog.objects.select_related('employee', 'employee__department').order_by('-timestamp')[:8],
            'department_stats': Department.objects.annotate(employee_total=Count('employee_set')).order_by('name')[:8],
            'status_breakdown': records_today.values('status').annotate(total=Count('id')).order_by('status'),
            'notifications': Notification.objects.order_by('-created_at')[:5],
        })
        return context


class EmployeeListView(EnterpriseListMixin):
    model = Employee
    template_name = 'attendance/employee_list.html'
    page_title = 'Employees'
    active_nav = 'employees'
    search_fields = ['organization_id', 'first_name', 'last_name', 'email', 'job_title', 'department__name']
    default_ordering = 'first_name'
    export_filename = 'employees'
    export_fields = [
        ('organization_id', 'Employee ID'),
        ('full_name', 'Name'),
        ('email', 'Email'),
        ('department__name', 'Department'),
        ('job_title', 'Job Title'),
        ('employment_status', 'Status'),
    ]

    def get_queryset(self):
        queryset = super().get_queryset().select_related('department', 'office_location')
        department = self.request.GET.get('department')
        status = self.request.GET.get('status')
        if department:
            queryset = queryset.filter(department_id=department)
        if status:
            queryset = queryset.filter(employment_status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['departments'] = Department.objects.filter(is_active=True)
        context['status_choices'] = Employee.EmploymentStatus.choices
        return context


class EmployeeDetailView(EnterpriseContextMixin, DetailView):
    model = Employee
    template_name = 'attendance/employee_detail.html'
    page_title = 'Employee Profile'
    active_nav = 'employees'

    def get_queryset(self):
        return Employee.objects.select_related('department', 'office_location')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.object
        records = employee.attendance_records.order_by('-date')[:30]
        total = employee.attendance_records.count()
        attended = employee.attendance_records.filter(status__in=[
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
            AttendanceRecord.Status.EARLY_LEAVE,
            AttendanceRecord.Status.OVERTIME,
        ]).count()
        context.update({
            'current_schedule': AttendanceEngine().get_schedule(employee, timezone.localdate()),
            'attendance_records': records,
            'leave_balances': LeaveBalance.objects.filter(employee=employee),
            'attendance_percentage': round((attended / total) * 100, 1) if total else 0,
        })
        return context


class EmployeeCreateView(EnterpriseContextMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('employee_list')
    page_title = 'Add Employee'
    active_nav = 'employees'


class EmployeeUpdateView(EmployeeCreateView, UpdateView):
    page_title = 'Edit Employee'


class DepartmentListView(EnterpriseListMixin):
    model = Department
    template_name = 'attendance/department_list.html'
    page_title = 'Departments'
    active_nav = 'departments'
    search_fields = ['name', 'code']
    default_ordering = 'name'
    export_filename = 'departments'
    export_fields = [('name', 'Name'), ('code', 'Code'), ('employee_count', 'Employees'), ('is_active', 'Active')]

    def get_queryset(self):
        queryset = Department.objects.annotate(employee_count=Count('employee_set')).select_related('manager', 'company')
        query = self.request.GET.get('q', '').strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(code__icontains=query))
        return queryset.order_by(self.get_ordering())


class DepartmentCreateView(EnterpriseContextMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('department_list')
    page_title = 'Add Department'
    active_nav = 'departments'


class DepartmentUpdateView(DepartmentCreateView, UpdateView):
    page_title = 'Edit Department'


class ShiftListView(EnterpriseListMixin):
    model = Shift
    template_name = 'attendance/shift_list.html'
    page_title = 'Shift Management'
    active_nav = 'shifts'
    search_fields = ['name']
    default_ordering = 'start_time'
    export_filename = 'shifts'
    export_fields = [
        ('name', 'Name'),
        ('start_time', 'Start'),
        ('end_time', 'End'),
        ('grace_period_minutes', 'Grace'),
        ('late_threshold_minutes', 'Late Threshold'),
        ('absent_threshold_minutes', 'Absent Threshold'),
        ('overtime_starts_after_minutes', 'Overtime Rule'),
    ]


class ShiftCreateView(EnterpriseContextMixin, CreateView):
    model = Shift
    form_class = ShiftForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('shift_list')
    page_title = 'Add Shift'
    active_nav = 'shifts'


class ShiftUpdateView(ShiftCreateView, UpdateView):
    page_title = 'Edit Shift'


class ScheduleListView(EnterpriseListMixin):
    model = EmployeeSchedule
    template_name = 'attendance/schedule_list.html'
    page_title = 'Schedule Management'
    active_nav = 'schedules'
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__organization_id', 'shift__name', 'department__name']
    default_ordering = '-effective_start'
    export_filename = 'schedules'
    export_fields = [
        ('employee__organization_id', 'Employee ID'),
        ('employee__full_name', 'Employee'),
        ('department__name', 'Department'),
        ('shift__name', 'Shift'),
        ('effective_start', 'Starts'),
        ('effective_end', 'Ends'),
        ('is_flexible', 'Flexible'),
    ]

    def get_queryset(self):
        return super().get_queryset().select_related('employee', 'department', 'shift')


class ScheduleCreateView(EnterpriseContextMixin, CreateView):
    model = EmployeeSchedule
    form_class = EmployeeScheduleForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('schedule_list')
    page_title = 'Add Schedule'
    active_nav = 'schedules'


class ScheduleUpdateView(ScheduleCreateView, UpdateView):
    page_title = 'Edit Schedule'


class AttendanceRecordListView(EnterpriseListMixin):
    model = AttendanceRecord
    template_name = 'attendance/attendance_records.html'
    page_title = 'Attendance'
    active_nav = 'attendance'
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__organization_id', 'employee__department__name']
    default_ordering = '-date'
    export_filename = 'attendance'
    export_fields = [
        ('date', 'Date'),
        ('employee__organization_id', 'Employee ID'),
        ('employee__full_name', 'Employee'),
        ('employee__department__name', 'Department'),
        ('status', 'Status'),
        ('minutes_late', 'Late Minutes'),
        ('minutes_early_leave', 'Early Leave'),
        ('overtime_minutes', 'Overtime'),
        ('worked_minutes', 'Worked'),
    ]

    def get_queryset(self):
        queryset = super().get_queryset().select_related('employee', 'employee__department', 'shift')
        status = self.request.GET.get('status')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if status:
            queryset = queryset.filter(status=status)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = AttendanceRecord.Status.choices
        return context


class LeaveListView(EnterpriseListMixin):
    model = LeaveRequest
    template_name = 'attendance/leave_list.html'
    page_title = 'Leave Management'
    active_nav = 'leave'
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__organization_id', 'reason']
    default_ordering = '-start_date'
    export_filename = 'leave'
    export_fields = [
        ('employee__full_name', 'Employee'),
        ('leave_type', 'Type'),
        ('start_date', 'Start'),
        ('end_date', 'End'),
        ('days', 'Days'),
        ('status', 'Status'),
    ]

    def get_queryset(self):
        queryset = super().get_queryset().select_related('employee')
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        return queryset


class LeaveCreateView(EnterpriseContextMixin, CreateView):
    model = LeaveRequest
    form_class = LeaveRequestForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('leave_list')
    page_title = 'Add Leave Request'
    active_nav = 'leave'


class LeaveUpdateView(LeaveCreateView, UpdateView):
    page_title = 'Edit Leave Request'


class HolidayListView(EnterpriseListMixin):
    model = Holiday
    template_name = 'attendance/holiday_list.html'
    page_title = 'Holidays'
    active_nav = 'holidays'
    search_fields = ['name', 'department__name', 'office_location__name']
    default_ordering = 'date'
    export_filename = 'holidays'
    export_fields = [('date', 'Date'), ('name', 'Name'), ('department__name', 'Department'), ('is_paid', 'Paid')]

    def get_queryset(self):
        return super().get_queryset().select_related('department', 'office_location')


class HolidayCreateView(EnterpriseContextMixin, CreateView):
    model = Holiday
    form_class = HolidayForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('holiday_list')
    page_title = 'Add Holiday'
    active_nav = 'holidays'


class HolidayUpdateView(HolidayCreateView, UpdateView):
    page_title = 'Edit Holiday'


class ReportsView(EnterpriseContextMixin, TemplateView):
    template_name = 'attendance/reports.html'
    page_title = 'Reports'
    active_nav = 'reports'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        month_start = today.replace(day=1)
        records = AttendanceRecord.objects.filter(date__gte=month_start)
        context.update({
            'today': today,
            'daily': AttendanceRecord.objects.filter(date=today).select_related('employee', 'employee__department')[:20],
            'monthly_status': records.values('status').annotate(total=Count('id')).order_by('status'),
            'department_attendance': records.values('employee__department__name').annotate(
                total=Count('id'),
                late=Count('id', filter=Q(status=AttendanceRecord.Status.LATE)),
                absent=Count('id', filter=Q(status=AttendanceRecord.Status.ABSENT)),
                overtime=Sum('overtime_minutes'),
            ).order_by('employee__department__name'),
            'late_arrivals': records.filter(status=AttendanceRecord.Status.LATE).select_related('employee')[:10],
            'absences': records.filter(status=AttendanceRecord.Status.ABSENT).select_related('employee')[:10],
            'overtime': records.filter(overtime_minutes__gt=0).select_related('employee')[:10],
        })
        return context


class NotificationListView(EnterpriseListMixin):
    model = Notification
    template_name = 'attendance/notification_list.html'
    page_title = 'Notifications'
    active_nav = 'notifications'
    search_fields = ['title', 'message', 'employee__first_name', 'employee__last_name']
    default_ordering = '-created_at'
    export_filename = 'notifications'
    export_fields = [('created_at', 'Created'), ('title', 'Title'), ('level', 'Level'), ('is_read', 'Read')]


class UserRolesView(EnterpriseContextMixin, TemplateView):
    template_name = 'attendance/user_roles.html'
    page_title = 'User Roles'
    active_nav = 'roles'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.prefetch_related('groups').order_by('username')
        context['groups'] = Group.objects.prefetch_related('permissions').order_by('name')
        return context


class SystemSettingsView(EnterpriseContextMixin, TemplateView):
    template_name = 'attendance/system_settings.html'
    page_title = 'System Settings'
    active_nav = 'settings'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['settings_rows'] = SystemSetting.objects.all()
        context['system_health'] = {
            'debug': settings.DEBUG,
            'timezone': settings.TIME_ZONE,
            'database': settings.DATABASES['default']['ENGINE'].split('.')[-1],
        }
        return context


@csrf_exempt
def attendance_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            fp_id = data.get('fingerprint_id')
            if fp_id is None:
                return JsonResponse({'error': 'Missing fingerprint_id'}, status=400)

            try:
                employee = Employee.objects.select_related('department').get(fingerprint_id=fp_id)
            except Employee.DoesNotExist:
                logger.warning('Unregistered fingerprint attempt: %s', fp_id)
                return JsonResponse({'error': 'Unregistered fingerprint', 'fingerprint_id': fp_id}, status=404)

            engine = AttendanceEngine()
            allowed, cooldown_msg = engine.is_scan_allowed(employee)
            if not allowed:
                return JsonResponse({'error': cooldown_msg, 'status': 'cooldown'}, status=429)

            today = timezone.localdate()
            last_scan = AttendanceLog.objects.filter(employee=employee, timestamp__date=today).order_by('-timestamp').first()
            scan_type = 'OUT' if last_scan and last_scan.scan_type == 'IN' else 'IN'
            log_entry = AttendanceLog.objects.create(employee=employee, scan_type=scan_type)
            record = engine.calculate_employee_day(employee, today)

            return JsonResponse({
                'status': 'success',
                'message': f"{'Goodbye' if scan_type == 'OUT' else 'Welcome'}, {employee.first_name}!",
                'employee': {
                    'id': employee.id,
                    'name': employee.full_name,
                    'organization_id': employee.organization_id,
                    'department': employee.department.name if employee.department else 'N/A',
                    'job_title': employee.job_title,
                },
                'scan_type': scan_type,
                'attendance_status': record.status,
                'timestamp': log_entry.timestamp.isoformat(),
            }, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)
        except Exception as exc:
            logger.exception('Attendance API error')
            return JsonResponse({'error': 'Internal server error', 'message': str(exc) if settings.DEBUG else 'Unexpected error'}, status=500)

    if request.method == 'GET':
        return redirect('dashboard')

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def enrollment_next_api(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    with transaction.atomic():
        enrollment_request = (
            EnrollmentRequest.objects.select_related('employee')
            .filter(status=EnrollmentRequest.Status.PENDING)
            .order_by('requested_at')
            .first()
        )
        if not enrollment_request:
            return JsonResponse({'status': 'idle'})
        enrollment_request.status = EnrollmentRequest.Status.DISPATCHED
        enrollment_request.dispatched_at = timezone.now()
        enrollment_request.save(update_fields=['status', 'dispatched_at'])

    return JsonResponse({
        'status': 'ok',
        'request': {
            'id': enrollment_request.id,
            'employee_id': enrollment_request.employee_id,
            'organization_id': enrollment_request.employee.organization_id,
            'name': enrollment_request.employee.full_name,
            'fingerprint_id': enrollment_request.fingerprint_id,
        },
    })


@csrf_exempt
def enrollment_complete_api(request, request_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    enrollment_request = get_object_or_404(EnrollmentRequest.objects.select_related('employee'), pk=request_id)
    enrollment_request.employee.fingerprint_id = enrollment_request.fingerprint_id
    enrollment_request.employee.save(update_fields=['fingerprint_id'])
    enrollment_request.status = EnrollmentRequest.Status.COMPLETED
    enrollment_request.completed_at = timezone.now()
    enrollment_request.error_message = ''
    enrollment_request.save(update_fields=['status', 'completed_at', 'error_message'])
    return JsonResponse({'status': 'ok', 'message': 'Enrollment completed'})


@csrf_exempt
def enrollment_fail_api(request, request_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    enrollment_request = get_object_or_404(EnrollmentRequest, pk=request_id)
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        payload = {}
    enrollment_request.status = EnrollmentRequest.Status.FAILED
    enrollment_request.error_message = payload.get('message', 'Enrollment failed')
    enrollment_request.save(update_fields=['status', 'error_message'])
    return JsonResponse({'status': 'ok', 'message': enrollment_request.error_message})


# ---------------------------------------------------------------------------
# Enrollment scanning page (real-time WebSocket UI)
# ---------------------------------------------------------------------------

def enroll_scan_view(request, enrollment_id):
    """Rendering the real-time fingerprint scanning page."""
    enrollment = get_object_or_404(
        EnrollmentRequest.objects.select_related('employee', 'device'),
        pk=enrollment_id,
    )

    return render(request, 'admin/attendance/employee/enroll_scan.html', {
        'enrollment': enrollment,
        'employee': enrollment.employee,
        'device': enrollment.device,
        'fingerprint_id': enrollment.fingerprint_id,
        'page_title': f'Enrolling — {enrollment.employee.full_name}',
    })


# ---------------------------------------------------------------------------
# Overtime Requests
# ---------------------------------------------------------------------------

class OvertimeRequestListView(EnterpriseListMixin):
    model = OvertimeRequest
    template_name = 'attendance/overtime_list.html'
    page_title = 'Overtime Requests'
    active_nav = 'overtime'
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__organization_id']
    default_ordering = '-date'
    export_filename = 'overtime'
    export_fields = [
        ('employee__full_name', 'Employee'),
        ('date', 'Date'),
        ('requested_minutes', 'Requested'),
        ('approved_minutes', 'Approved'),
        ('status', 'Status'),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('employee', 'approved_by')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = OvertimeRequest.Status.choices
        return context


class OvertimeRequestCreateView(EnterpriseContextMixin, CreateView):
    model = OvertimeRequest
    form_class = OvertimeRequestForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('overtime_list')
    page_title = 'Request Overtime'
    active_nav = 'overtime'


class OvertimeRequestUpdateView(OvertimeRequestCreateView, UpdateView):
    page_title = 'Edit Overtime Request'


@csrf_exempt
def overtime_approve_api(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    overtime = get_object_or_404(OvertimeRequest, pk=pk)
    data = json.loads(request.body or '{}')
    action = data.get('action', '')
    if action == 'approve':
        overtime.status = OvertimeRequest.Status.APPROVED
        overtime.approved_minutes = data.get('approved_minutes', overtime.requested_minutes)
        overtime.approved_by = request.user if request.user.is_authenticated else None
    elif action == 'reject':
        overtime.status = OvertimeRequest.Status.REJECTED
    overtime.save(update_fields=['status', 'approved_minutes', 'approved_by'])
    return JsonResponse({'status': 'ok', 'new_status': overtime.status})


# ---------------------------------------------------------------------------
# Remote Work Logs
# ---------------------------------------------------------------------------

class RemoteWorkLogListView(EnterpriseListMixin):
    model = RemoteWorkLog
    template_name = 'attendance/remote_list.html'
    page_title = 'Remote Work'
    active_nav = 'remote'
    search_fields = ['employee__first_name', 'employee__last_name']
    default_ordering = '-date'
    export_filename = 'remote_work'
    export_fields = [
        ('employee__full_name', 'Employee'),
        ('date', 'Date'),
        ('status', 'Status'),
        ('hours_worked', 'Hours'),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('employee')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = RemoteWorkLog.Status.choices
        return context


class RemoteWorkLogCreateView(EnterpriseContextMixin, CreateView):
    model = RemoteWorkLog
    form_class = RemoteWorkLogForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('remote_list')
    page_title = 'Log Remote Work'
    active_nav = 'remote'


class RemoteWorkLogUpdateView(RemoteWorkLogCreateView, UpdateView):
    page_title = 'Edit Remote Work'


# ---------------------------------------------------------------------------
# Site Visits
# ---------------------------------------------------------------------------

class SiteVisitListView(EnterpriseListMixin):
    model = SiteVisit
    template_name = 'attendance/site_list.html'
    page_title = 'Site Visits'
    active_nav = 'sites'
    search_fields = ['employee__first_name', 'employee__last_name', 'location_name']
    default_ordering = '-date'
    export_filename = 'site_visits'
    export_fields = [
        ('employee__full_name', 'Employee'),
        ('date', 'Date'),
        ('location_name', 'Location'),
        ('duration_minutes', 'Duration'),
    ]

    def get_queryset(self):
        return super().get_queryset().select_related('employee')


class SiteVisitCreateView(EnterpriseContextMixin, CreateView):
    model = SiteVisit
    form_class = SiteVisitForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('site_list')
    page_title = 'Log Site Visit'
    active_nav = 'sites'


class SiteVisitUpdateView(SiteVisitCreateView, UpdateView):
    page_title = 'Edit Site Visit'


# ---------------------------------------------------------------------------
# Schedule Templates
# ---------------------------------------------------------------------------

class ScheduleTemplateListView(EnterpriseListMixin):
    model = ScheduleTemplate
    template_name = 'attendance/template_list.html'
    page_title = 'Schedule Templates'
    active_nav = 'templates'
    search_fields = ['name']
    default_ordering = 'name'
    export_filename = 'schedule_templates'
    export_fields = [('name', 'Name'), ('template_type', 'Type'), ('is_active', 'Active')]

    def get_queryset(self):
        qs = super().get_queryset().select_related('shift')
        t = self.request.GET.get('type')
        if t:
            qs = qs.filter(template_type=t)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['template_types'] = ScheduleTemplate.TemplateType.choices
        return context


class ScheduleTemplateCreateView(EnterpriseContextMixin, CreateView):
    model = ScheduleTemplate
    form_class = ScheduleTemplateForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('template_list')
    page_title = 'Add Template'
    active_nav = 'templates'


class ScheduleTemplateUpdateView(ScheduleTemplateCreateView, UpdateView):
    page_title = 'Edit Template'


# ---------------------------------------------------------------------------
# Attendance Policies
# ---------------------------------------------------------------------------

class AttendancePolicyListView(EnterpriseListMixin):
    model = AttendancePolicy
    template_name = 'attendance/policy_list.html'
    page_title = 'Attendance Policies'
    active_nav = 'policies'
    search_fields = ['name']
    default_ordering = 'name'
    export_filename = 'policies'
    export_fields = [
        ('name', 'Name'),
        ('grace_period_minutes', 'Grace (min)'),
        ('late_threshold_minutes', 'Late (min)'),
        ('auto_checkout_enabled', 'Auto Checkout'),
    ]

    def get_queryset(self):
        return super().get_queryset()


class AttendancePolicyCreateView(EnterpriseContextMixin, CreateView):
    model = AttendancePolicy
    form_class = AttendancePolicyForm
    template_name = 'attendance/form.html'
    success_url = reverse_lazy('policy_list')
    page_title = 'Add Policy'
    active_nav = 'policies'


class AttendancePolicyUpdateView(AttendancePolicyCreateView, UpdateView):
    page_title = 'Edit Policy'


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

from django.contrib.auth import authenticate, login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView


class SmartLoginView(LoginView):
    template_name = 'attendance/login.html'
    redirect_authenticated_user = True


class SmartLogoutView(LogoutView):
    next_page = 'login'
