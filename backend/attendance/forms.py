from django import forms
from organizations.models import Department, Team

from .models import (
    AttendancePolicy,
    Employee,
    EmployeeSchedule,
    Holiday,
    LeaveRequest,
    OvertimeRequest,
    RemoteWorkLog,
    ScheduleTemplate,
    Shift,
    SiteVisit,
)


class SearchFilterForm(forms.Form):
    q = forms.CharField(required=False, label='Search')
    department = forms.ModelChoiceField(queryset=Department.objects.filter(is_active=True), required=False)
    status = forms.CharField(required=False)
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            'organization_id', 'first_name', 'last_name', 'email', 'phone',
            'date_of_birth', 'gender', 'address',
            'emergency_contact_name', 'emergency_contact_phone',
            'department', 'team', 'manager', 'job_title',
            'employment_type', 'employment_status',
            'office_location', 'work_location_name',
            'hire_date', 'contract_start_date', 'contract_end_date',
            'weekly_working_days', 'expected_weekly_hours', 'expected_monthly_hours',
            'attendance_policy',
            'fingerprint_id',
        ]
        widgets = {
            'hire_date': forms.DateInput(attrs={'type': 'date'}),
            'contract_start_date': forms.DateInput(attrs={'type': 'date'}),
            'contract_end_date': forms.DateInput(attrs={'type': 'date'}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['company', 'name', 'code', 'branch', 'cost_center', 'parent', 'manager', 'description', 'is_active']


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'code', 'department', 'lead', 'description', 'is_active']


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = [
            'name', 'start_time', 'end_time',
            'grace_period_minutes', 'late_threshold_minutes', 'absent_threshold_minutes',
            'early_checkout_threshold_minutes', 'overtime_starts_after_minutes', 'minimum_overtime_minutes',
            'is_overnight', 'is_active',
        ]
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class EmployeeScheduleForm(forms.ModelForm):
    class Meta:
        model = EmployeeSchedule
        fields = [
            'employee', 'department', 'shift',
            'effective_start', 'effective_end',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'is_flexible', 'flexible_start_time', 'flexible_end_time',
            'rotation_group', 'notes',
        ]
        widgets = {
            'effective_start': forms.DateInput(attrs={'type': 'date'}),
            'effective_end': forms.DateInput(attrs={'type': 'date'}),
            'flexible_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'flexible_end_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class ScheduleTemplateForm(forms.ModelForm):
    class Meta:
        model = ScheduleTemplate
        fields = [
            'name', 'template_type', 'shift',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'is_flexible', 'flexible_start_time', 'flexible_end_time',
            'rotation_pattern', 'split_shifts', 'description', 'is_active',
        ]


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['employee', 'leave_type', 'start_date', 'end_date', 'status', 'days', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ['name', 'date', 'department', 'office_location', 'is_paid']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}


class OvertimeRequestForm(forms.ModelForm):
    class Meta:
        model = OvertimeRequest
        fields = ['employee', 'date', 'requested_minutes', 'reason']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}


class SiteVisitForm(forms.ModelForm):
    class Meta:
        model = SiteVisit
        fields = ['employee', 'date', 'location_name', 'purpose', 'check_in', 'check_out', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'check_in': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'check_out': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class RemoteWorkLogForm(forms.ModelForm):
    class Meta:
        model = RemoteWorkLog
        fields = ['employee', 'date', 'status', 'start_time', 'end_time', 'hours_worked', 'task_description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class AttendancePolicyForm(forms.ModelForm):
    class Meta:
        model = AttendancePolicy
        fields = [
            'name', 'description',
            'grace_period_minutes', 'late_threshold_minutes', 'absent_threshold_minutes',
            'early_checkout_threshold_minutes', 'overtime_starts_after_minutes',
            'minimum_overtime_minutes', 'max_overtime_minutes',
            'auto_checkout_enabled', 'auto_checkout_time',
            'duplicate_scan_prevention', 'duplicate_scan_cooldown_seconds',
            'allow_remote_checkin', 'require_location', 'geo_fence_enforcement',
            'break_deducted', 'lunch_deducted',
            'is_active',
        ]
        widgets = {
            'auto_checkout_time': forms.TimeInput(attrs={'type': 'time'}),
        }
