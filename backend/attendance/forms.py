from django import forms

from .models import (
    Department,
    Employee,
    EmployeeSchedule,
    Holiday,
    LeaveRequest,
    Shift,
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
            'organization_id',
            'first_name',
            'last_name',
            'email',
            'phone',
            'department',
            'job_title',
            'office_location',
            'hire_date',
            'employment_status',
            'fingerprint_id',
        ]
        widgets = {'hire_date': forms.DateInput(attrs={'type': 'date'})}


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'manager', 'is_active']


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = [
            'name',
            'start_time',
            'end_time',
            'grace_period_minutes',
            'late_threshold_minutes',
            'absent_threshold_minutes',
            'early_checkout_threshold_minutes',
            'overtime_starts_after_minutes',
            'minimum_overtime_minutes',
            'is_overnight',
            'is_active',
        ]
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class EmployeeScheduleForm(forms.ModelForm):
    class Meta:
        model = EmployeeSchedule
        fields = [
            'employee',
            'department',
            'shift',
            'effective_start',
            'effective_end',
            'monday',
            'tuesday',
            'wednesday',
            'thursday',
            'friday',
            'saturday',
            'sunday',
            'is_flexible',
            'flexible_start_time',
            'flexible_end_time',
            'notes',
        ]
        widgets = {
            'effective_start': forms.DateInput(attrs={'type': 'date'}),
            'effective_end': forms.DateInput(attrs={'type': 'date'}),
            'flexible_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'flexible_end_time': forms.TimeInput(attrs={'type': 'time'}),
        }


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
