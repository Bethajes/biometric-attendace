from django.contrib import admin, messages
from django.db.models import Max
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
	AttendanceLog,
	AttendanceRecord,
	BiometricDevice,
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
	list_filter = ('is_active',)
	search_fields = ('name', 'code')
	autocomplete_fields = ('manager',)
	fieldsets = (
		(None, {'fields': ('name', 'code', 'is_active')}),
		('Management', {'fields': ('manager',)}),
	)


@admin.register(OfficeLocation)
class OfficeLocationAdmin(admin.ModelAdmin):
	list_display = ('id', 'name', 'address', 'timezone', 'is_active')
	list_filter = ('is_active',)
	search_fields = ('name', 'address')
	fieldsets = (
		(None, {'fields': ('name', 'address', 'is_active')}),
		('Configuration', {'fields': ('timezone',)}),
	)


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
	list_display = ('id', 'employee', 'scan_type', 'timestamp')
	list_filter = ('scan_type', 'timestamp', 'employee__department')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
	autocomplete_fields = ('employee',)
	readonly_fields = ('timestamp',)
	list_per_page = 25


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
	list_display = ('date', 'employee', 'status', 'shift', 'minutes_late', 'minutes_early_leave', 'overtime_minutes', 'worked_minutes')
	list_filter = ('status', 'date', 'employee__department', 'shift')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
	autocomplete_fields = ('employee', 'schedule', 'shift')
	readonly_fields = ('calculated_at',)
	list_per_page = 25
	fieldsets = (
		('Employee & Schedule', {
			'fields': ('employee', 'date', 'schedule', 'shift'),
		}),
		('Time Tracking', {
			'fields': ('first_check_in', 'last_check_out'),
		}),
		('Classification', {
			'fields': ('status', 'minutes_late', 'minutes_early_leave', 'overtime_minutes', 'worked_minutes'),
		}),
		('Notes & Metadata', {
			'fields': ('notes', 'calculated_at'),
			'classes': ('collapse',),
		}),
	)


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
	list_display = ('name', 'start_time', 'end_time', 'grace_period_minutes', 'late_threshold_minutes', 'absent_threshold_minutes', 'is_active')
	list_filter = ('is_active', 'is_overnight')
	search_fields = ('name',)
	fieldsets = (
		('Basic Info', {'fields': ('name', 'is_active', 'is_overnight')}),
		('Schedule', {'fields': ('start_time', 'end_time')}),
		('Thresholds', {
			'fields': ('grace_period_minutes', 'late_threshold_minutes', 'absent_threshold_minutes', 'early_checkout_threshold_minutes'),
		}),
		('Overtime', {
			'fields': ('overtime_starts_after_minutes', 'minimum_overtime_minutes'),
		}),
	)


@admin.register(EmployeeSchedule)
class EmployeeScheduleAdmin(admin.ModelAdmin):
	list_display = ('employee', 'department', 'shift', 'effective_start', 'effective_end', 'is_flexible')
	list_filter = ('department', 'shift', 'is_flexible', 'effective_start')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id', 'shift__name')
	autocomplete_fields = ('employee', 'department', 'shift')
	readonly_fields = ('created_at',)
	list_per_page = 25
	fieldsets = (
		('Assignment', {'fields': ('employee', 'department', 'shift')}),
		('Effective Period', {'fields': ('effective_start', 'effective_end')}),
		('Working Days', {
			'fields': ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'),
		}),
		('Flexible Schedule', {
			'fields': ('is_flexible', 'flexible_start_time', 'flexible_end_time'),
			'classes': ('collapse',),
		}),
		('Notes', {
			'fields': ('notes', 'created_at'),
			'classes': ('collapse',),
		}),
	)


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
	list_display = ('date', 'name', 'department', 'office_location', 'is_paid')
	list_filter = ('date', 'department', 'office_location', 'is_paid')
	search_fields = ('name',)
	fieldsets = (
		(None, {'fields': ('name', 'date', 'is_paid')}),
		('Scope', {'fields': ('department', 'office_location')}),
	)


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
	list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'days', 'status', 'approved_by')
	list_filter = ('leave_type', 'status', 'start_date')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
	autocomplete_fields = ('employee', 'approved_by')
	readonly_fields = ('created_at', 'updated_at')
	list_per_page = 25
	fieldsets = (
		('Employee', {'fields': ('employee',)}),
		('Leave Details', {'fields': ('leave_type', 'start_date', 'end_date', 'days')}),
		('Status', {'fields': ('status', 'approved_by')}),
		('Reason', {'fields': ('reason',), 'classes': ('collapse',)}),
		('Metadata', {
			'fields': ('created_at', 'updated_at'),
			'classes': ('collapse',),
		}),
	)

	def save_model(self, request, obj, form, change):
		if not change and not obj.approved_by:
			obj.approved_by = request.user
		super().save_model(request, obj, form, change)


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
	list_display = ('employee', 'leave_type', 'year', 'allocated_days', 'used_days', 'remaining_days')
	list_filter = ('leave_type', 'year')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
	autocomplete_fields = ('employee',)
	fieldsets = (
		(None, {'fields': ('employee', 'leave_type', 'year')}),
		('Balance', {'fields': ('allocated_days', 'used_days')}),
	)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
	list_display = ('created_at', 'title', 'level', 'employee', 'is_read')
	list_filter = ('level', 'is_read', 'created_at')
	search_fields = ('title', 'message', 'employee__first_name', 'employee__last_name')
	autocomplete_fields = ('employee',)
	readonly_fields = ('created_at',)
	fieldsets = (
		(None, {'fields': ('title', 'message', 'level')}),
		('Recipient', {'fields': ('employee', 'is_read')}),
		('Metadata', {'fields': ('created_at',), 'classes': ('collapse',)}),
	)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
	list_display = ('key', 'value', 'description', 'updated_at')
	search_fields = ('key', 'description')
	readonly_fields = ('updated_at',)
	fieldsets = (
		(None, {'fields': ('key', 'value', 'description')}),
		('Metadata', {'fields': ('updated_at',), 'classes': ('collapse',)}),
	)


@admin.register(EnrollmentRequest)
class EnrollmentRequestAdmin(admin.ModelAdmin):
	list_display = ('id', 'employee', 'fingerprint_id', 'status', 'device', 'requested_at', 'dispatched_at', 'completed_at')
	list_filter = ('status', 'requested_at', 'device')
	search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
	autocomplete_fields = ('employee', 'device')
	readonly_fields = ('requested_at', 'dispatched_at', 'completed_at')
	list_per_page = 25
	fieldsets = (
		('Employee & Device', {'fields': ('employee', 'fingerprint_id', 'device')}),
		('Status', {'fields': ('status', 'progress_message')}),
		('Timing', {
			'fields': ('requested_at', 'dispatched_at', 'completed_at'),
			'classes': ('collapse',),
		}),
		('Errors', {
			'fields': ('error_message',),
			'classes': ('collapse',),
		}),
	)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
	list_display = ('id', 'organization_id', 'first_name', 'last_name', 'department', 'job_title', 'employment_status', 'fingerprint_id', 'enrollment_status')
	list_filter = ('department', 'job_title', 'employment_status', 'office_location')
	search_fields = ('organization_id', 'first_name', 'last_name', 'email', 'fingerprint_id')
	autocomplete_fields = ('department', 'office_location')
	change_form_template = 'admin/attendance/employee/change_form.html'
	actions = ('register_fingerprint_action',)
	readonly_fields = ('created_at', 'updated_at')
	list_per_page = 25
	fieldsets = (
		('Personal Information', {
			'fields': ('organization_id', 'first_name', 'last_name', 'email', 'phone'),
		}),
		('Employment', {
			'fields': ('department', 'job_title', 'office_location', 'hire_date', 'employment_status'),
		}),
		('Biometrics', {
			'fields': ('fingerprint_id',),
			'description': 'Fingerprint ID is assigned during enrollment.',
		}),
		('Metadata', {
			'fields': ('created_at', 'updated_at'),
			'classes': ('collapse',),
		}),
	)

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

	def _find_active_device(self):
		"""Return the first active, non-offline BiometricDevice."""
		return BiometricDevice.objects.filter(
			is_active=True,
		).exclude(
			status=BiometricDevice.Status.OFFLINE,
		).order_by('name').first()

	def _get_or_create_enrollment(self, employee, device):
		"""
		Create an EnrollmentRequest if none is pending/dispatched/in-progress.
		Returns (enrollment_request, already_in_progress).
		"""
		existing = EnrollmentRequest.objects.filter(
			employee=employee,
			status__in=[
				EnrollmentRequest.Status.PENDING,
				EnrollmentRequest.Status.DISPATCHED,
				EnrollmentRequest.Status.IN_PROGRESS,
			],
		).select_related('device').first()

		if existing:
			return existing, True

		return EnrollmentRequest.objects.create(
			employee=employee,
			fingerprint_id=employee.fingerprint_id,
			device=device,
			status=EnrollmentRequest.Status.PENDING,
		), False

	def _dispatch_to_hardware(self, enrollment, device, employee):
		"""Send the ENROLL command to the biometric device."""
		try:
			from device_manager.services.hardware_service import get_hardware_service
			svc = get_hardware_service()
			svc.start_enrollment(device, employee, enrollment.fingerprint_id)
		except Exception as exc:
			import logging
			logging.getLogger('attendance.admin').warning(
				'Failed to dispatch enrollment %s to hardware: %s',
				enrollment.pk, exc,
			)

	def register_fingerprint_action(self, request, queryset):
		"""Admin action: auto-assign fp_id, create EnrollmentRequest, dispatch, redirect to scan page."""
		if queryset.count() != 1:
			self.message_user(
				request,
				'Select exactly one employee to register a fingerprint.',
				level=messages.WARNING,
			)
			return

		employee = queryset.first()

		# Auto-assign fingerprint_id if not yet set
		if employee.fingerprint_id is None:
			max_fingerprint = Employee.objects.aggregate(
				max_id=Max('fingerprint_id'),
			).get('max_id') or 0
			employee.fingerprint_id = max_fingerprint + 1
			employee.save(update_fields=['fingerprint_id'])

		# Find an active device
		device = self._find_active_device()
		if not device:
			self.message_user(
				request,
				'No active biometric device available. Connect a device first.',
				level=messages.ERROR,
			)
			return

		# Create or reuse enrollment request
		enrollment, already_in_progress = self._get_or_create_enrollment(employee, device)

		if not already_in_progress:
			self._dispatch_to_hardware(enrollment, device, employee)

		# Redirect to the real-time scanning page
		return redirect('enroll_scan', enrollment_id=enrollment.pk)

	register_fingerprint_action.short_description = 'Enroll Fingerprint'

	def enroll_fingerprint_view(self, request, object_id):
		"""Custom button on employee change form — same as the admin action."""
		employee = get_object_or_404(Employee, pk=object_id)

		# Auto-assign fingerprint_id if needed
		if employee.fingerprint_id is None:
			max_fingerprint = Employee.objects.aggregate(
				max_id=Max('fingerprint_id'),
			).get('max_id') or 0
			employee.fingerprint_id = max_fingerprint + 1
			employee.save(update_fields=['fingerprint_id'])

		device = self._find_active_device()
		if not device:
			self.message_user(
				request,
				'No active biometric device available.',
				level=messages.ERROR,
			)
			return HttpResponseRedirect(
				reverse('admin:attendance_employee_change', args=[employee.pk])
			)

		enrollment, already_in_progress = self._get_or_create_enrollment(employee, device)

		if not already_in_progress:
			self._dispatch_to_hardware(enrollment, device, employee)

		return redirect('enroll_scan', enrollment_id=enrollment.pk)
