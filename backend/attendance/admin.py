from django.contrib import admin, messages
from django.db.models import Max
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
	AttendanceLog,
	AttendanceRecord,
	Department,
	Employee,
	EmployeeSchedule,
	EnrollmentRequest,
	Holiday,
	LeaveBalance,
	LeaveRequest,
	Notification,
	OfficeLocation,
	Shift,
	SystemSetting,
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
	list_display = ('id', 'name', 'code', 'manager', 'is_active')
	search_fields = ('name', 'code')
	autocomplete_fields = ('manager',)


@admin.register(OfficeLocation)
class OfficeLocationAdmin(admin.ModelAdmin):
	list_display = ('id', 'name', 'timezone', 'is_active')
	search_fields = ('name', 'address')


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
	list_display = ('id', 'employee', 'scan_type', 'timestamp')
	list_filter = ('scan_type', 'timestamp', 'employee__department')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
	autocomplete_fields = ('employee',)


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
	list_display = ('date', 'employee', 'status', 'shift', 'minutes_late', 'minutes_early_leave', 'overtime_minutes', 'worked_minutes')
	list_filter = ('status', 'date', 'employee__department', 'shift')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
	autocomplete_fields = ('employee', 'schedule', 'shift')


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
	list_display = ('name', 'start_time', 'end_time', 'grace_period_minutes', 'late_threshold_minutes', 'absent_threshold_minutes', 'is_active')
	list_filter = ('is_active', 'is_overnight')
	search_fields = ('name',)


@admin.register(EmployeeSchedule)
class EmployeeScheduleAdmin(admin.ModelAdmin):
	list_display = ('employee', 'department', 'shift', 'effective_start', 'effective_end', 'is_flexible')
	list_filter = ('department', 'shift', 'is_flexible', 'effective_start')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id', 'shift__name')
	autocomplete_fields = ('employee', 'department', 'shift')


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
	list_display = ('date', 'name', 'department', 'office_location', 'is_paid')
	list_filter = ('date', 'department', 'office_location', 'is_paid')
	search_fields = ('name',)


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
	list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'days', 'status', 'approved_by')
	list_filter = ('leave_type', 'status', 'start_date')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
	autocomplete_fields = ('employee', 'approved_by')


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
	list_display = ('employee', 'leave_type', 'year', 'allocated_days', 'used_days', 'remaining_days')
	list_filter = ('leave_type', 'year')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
	autocomplete_fields = ('employee',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
	list_display = ('created_at', 'title', 'level', 'employee', 'is_read')
	list_filter = ('level', 'is_read', 'created_at')
	search_fields = ('title', 'message', 'employee__first_name', 'employee__last_name')
	autocomplete_fields = ('employee',)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
	list_display = ('key', 'value', 'updated_at')
	search_fields = ('key', 'description')


@admin.register(EnrollmentRequest)
class EnrollmentRequestAdmin(admin.ModelAdmin):
	list_display = ('id', 'employee', 'fingerprint_id', 'status', 'requested_at', 'dispatched_at', 'completed_at')
	list_filter = ('status', 'requested_at', 'dispatched_at', 'completed_at')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
	autocomplete_fields = ('employee',)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
	list_display = ('id', 'organization_id', 'first_name', 'last_name', 'department', 'job_title', 'employment_status', 'fingerprint_id', 'enrollment_status')
	list_filter = ('department', 'job_title', 'employment_status', 'office_location')
	search_fields = ('organization_id', 'first_name', 'last_name', 'email', 'fingerprint_id')
	autocomplete_fields = ('department', 'office_location')
	change_form_template = 'admin/attendance/employee/change_form.html'
	actions = ('register_fingerprint_action',)

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path(
				'<path:object_id>/enroll-fingerprint/',
				self.admin_site.admin_view(self.enroll_fingerprint_view),
				name='attendance_employee_enroll_fingerprint',
			),
		]
		return custom_urls + urls

	def enrollment_status(self, obj):
		request = obj.enrollment_requests.order_by('-requested_at').first()
		if not request:
			return 'No enrollment request'
		return request.status.title()

	enrollment_status.short_description = 'Enrollment Status'

	def register_fingerprint_action(self, request, queryset):
		if queryset.count() != 1:
			self.message_user(
				request,
				'Select exactly one employee to register a fingerprint.',
				level=messages.WARNING,
			)
			return

		employee = queryset.first()
		if employee.fingerprint_id:
			fingerprint_id = employee.fingerprint_id
		else:
			max_fingerprint = Employee.objects.aggregate(max_id=Max('fingerprint_id')).get('max_id') or 0
			fingerprint_id = max_fingerprint + 1
			employee.fingerprint_id = fingerprint_id
			employee.save(update_fields=['fingerprint_id'])

		existing_request = EnrollmentRequest.objects.filter(
			employee=employee,
			status__in=[EnrollmentRequest.Status.PENDING, EnrollmentRequest.Status.DISPATCHED],
		).first()
		if not existing_request:
			EnrollmentRequest.objects.create(
				employee=employee,
				fingerprint_id=fingerprint_id,
			)

		self.message_user(
			request,
			'Enrollment command sent to hardware. Please scan finger on the device.',
			level=messages.SUCCESS,
		)

	register_fingerprint_action.short_description = 'Register Fingerprint'

	def enroll_fingerprint_view(self, request, object_id):
		employee = get_object_or_404(Employee, pk=object_id)

		if request.method != 'POST':
			return HttpResponseRedirect(reverse('admin:attendance_employee_change', args=[employee.pk]))

		if employee.fingerprint_id is None:
			self.message_user(
				request,
				'Set the employee fingerprint ID before starting enrollment.',
				level=messages.ERROR,
			)
			return HttpResponseRedirect(reverse('admin:attendance_employee_change', args=[employee.pk]))

		existing_request = EnrollmentRequest.objects.filter(
			employee=employee,
			status__in=[EnrollmentRequest.Status.PENDING, EnrollmentRequest.Status.DISPATCHED],
		).first()
		if existing_request:
			self.message_user(
				request,
				f'Enrollment is already {existing_request.status.lower()} for this employee.',
				level=messages.WARNING,
			)
			return HttpResponseRedirect(reverse('admin:attendance_employee_change', args=[employee.pk]))

		EnrollmentRequest.objects.create(
			employee=employee,
			fingerprint_id=employee.fingerprint_id,
		)
		self.message_user(
			request,
			f'Enrollment request created for fingerprint ID {employee.fingerprint_id}. The bridge will pick it up automatically.',
			level=messages.SUCCESS,
		)
		return HttpResponseRedirect(reverse('admin:attendance_employee_change', args=[employee.pk]))
