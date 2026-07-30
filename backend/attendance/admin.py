from django.contrib import admin, messages
from django.db.models import Max
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    AttendanceBreak,
    AttendanceLog,
    AttendancePolicy,
    AttendanceRecord,
    AuditLog,
    BiometricDevice,
    DeviceCommand,
    DeviceEvent,
    Employee,
    EmployeeSchedule,
    EnrollmentRequest,
    Holiday,
    LeaveBalance,
    LeaveRequest,
    Notification,
    OfficeLocation,
    OvertimeRequest,
    RemoteWorkLog,
    ScheduleTemplate,
    Shift,
    SiteVisit,
    SystemSetting,
)


@admin.register(AttendancePolicy)
class AttendancePolicyAdmin(admin.ModelAdmin):
    list_display = ('name', 'grace_period_minutes', 'late_threshold_minutes', 'auto_checkout_enabled', 'duplicate_scan_prevention', 'is_active')
    list_filter = ('is_active', 'auto_checkout_enabled', 'duplicate_scan_prevention')
    search_fields = ('name',)
    fieldsets = (
        ('Basic Info', {'fields': ('name', 'description', 'is_active')}),
        ('Time Thresholds', {'fields': ('grace_period_minutes', 'late_threshold_minutes', 'absent_threshold_minutes', 'early_checkout_threshold_minutes')}),
        ('Overtime', {'fields': ('overtime_starts_after_minutes', 'minimum_overtime_minutes', 'max_overtime_minutes')}),
        ('Auto Checkout', {'fields': ('auto_checkout_enabled', 'auto_checkout_time')}),
        ('Scan Rules', {'fields': ('duplicate_scan_prevention', 'duplicate_scan_cooldown_seconds')}),
        ('Remote & Location', {'fields': ('allow_remote_checkin', 'require_location', 'geo_fence_enforcement')}),
        ('Deductions', {'fields': ('break_deducted', 'lunch_deducted')}),
    )


@admin.register(OfficeLocation)
class OfficeLocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'city', 'country', 'is_headquarters', 'is_active')
    list_filter = ('is_active', 'is_headquarters', 'country')
    search_fields = ('name', 'city', 'address')
    fieldsets = (
        (None, {'fields': ('name', 'address', 'city', 'state', 'country', 'is_active', 'is_headquarters')}),
        ('Configuration', {'fields': ('timezone', 'latitude', 'longitude', 'geo_fence_radius_meters')}),
    )


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'scan_type', 'source', 'timestamp')
    list_filter = ('scan_type', 'source', 'timestamp', 'employee__department')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
    autocomplete_fields = ('employee', 'device')
    readonly_fields = ('timestamp',)
    list_per_page = 25


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('date', 'employee', 'status', 'shift', 'minutes_late', 'minutes_early_leave', 'overtime_minutes', 'worked_minutes', 'break_minutes')
    list_filter = ('status', 'date', 'employee__department', 'shift')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
    autocomplete_fields = ('employee', 'schedule', 'shift')
    readonly_fields = ('calculated_at',)
    list_per_page = 25
    fieldsets = (
        ('Employee & Schedule', {'fields': ('employee', 'date', 'schedule', 'shift')}),
        ('Time Tracking', {'fields': ('first_check_in', 'last_check_out')}),
        ('Classification', {'fields': ('status', 'minutes_late', 'minutes_early_leave', 'overtime_minutes', 'worked_minutes')}),
        ('Breaks & Deductions', {'fields': ('break_minutes', 'lunch_minutes', 'total_attendance_minutes'), 'classes': ('collapse',)}),
        ('Remote & Site', {'fields': ('remote_minutes', 'site_visit_minutes', 'auto_checkout'), 'classes': ('collapse',)}),
        ('Notes & Metadata', {'fields': ('notes', 'calculated_at'), 'classes': ('collapse',)}),
    )


@admin.register(AttendanceBreak)
class AttendanceBreakAdmin(admin.ModelAdmin):
    list_display = ('attendance_record', 'break_type', 'start_time', 'end_time', 'duration_minutes')
    list_filter = ('break_type',)
    search_fields = ('attendance_record__employee__first_name', 'attendance_record__employee__last_name')
    autocomplete_fields = ('attendance_record',)


@admin.register(OvertimeRequest)
class OvertimeRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'requested_minutes', 'approved_minutes', 'status', 'approved_by')
    list_filter = ('status', 'date')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
    autocomplete_fields = ('employee', 'approved_by')


@admin.register(SiteVisit)
class SiteVisitAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'location_name', 'duration_minutes')
    list_filter = ('date',)
    search_fields = ('employee__first_name', 'employee__last_name', 'location_name')
    autocomplete_fields = ('employee',)


@admin.register(RemoteWorkLog)
class RemoteWorkLogAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'status', 'hours_worked')
    list_filter = ('status', 'date')
    search_fields = ('employee__first_name', 'employee__last_name')
    autocomplete_fields = ('employee', 'approved_by')


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_time', 'end_time', 'grace_period_minutes', 'late_threshold_minutes', 'absent_threshold_minutes', 'is_active')
    list_filter = ('is_active', 'is_overnight')
    search_fields = ('name',)
    fieldsets = (
        ('Basic Info', {'fields': ('name', 'is_active', 'is_overnight')}),
        ('Schedule', {'fields': ('start_time', 'end_time')}),
        ('Thresholds', {'fields': ('grace_period_minutes', 'late_threshold_minutes', 'absent_threshold_minutes', 'early_checkout_threshold_minutes')}),
        ('Overtime', {'fields': ('overtime_starts_after_minutes', 'minimum_overtime_minutes')}),
    )


@admin.register(EmployeeSchedule)
class EmployeeScheduleAdmin(admin.ModelAdmin):
    list_display = ('employee', 'department', 'shift', 'effective_start', 'effective_end', 'is_flexible', 'rotation_group')
    list_filter = ('department', 'shift', 'is_flexible', 'effective_start')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id', 'shift__name', 'rotation_group')
    autocomplete_fields = ('employee', 'department', 'shift')
    readonly_fields = ('created_at',)
    list_per_page = 25
    fieldsets = (
        ('Assignment', {'fields': ('employee', 'department', 'shift')}),
        ('Effective Period', {'fields': ('effective_start', 'effective_end')}),
        ('Working Days', {'fields': ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')}),
        ('Flexible Schedule', {'fields': ('is_flexible', 'flexible_start_time', 'flexible_end_time'), 'classes': ('collapse',)}),
        ('Rotation', {'fields': ('rotation_group',), 'classes': ('collapse',)}),
        ('Notes', {'fields': ('notes', 'created_at'), 'classes': ('collapse',)}),
    )


@admin.register(ScheduleTemplate)
class ScheduleTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'template_type', 'shift', 'is_active')
    list_filter = ('template_type', 'is_active')
    search_fields = ('name',)
    autocomplete_fields = ('shift',)


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
        ('Status', {'fields': ('status', 'approved_by', 'approved_at', 'rejection_reason')}),
        ('Reason', {'fields': ('reason',), 'classes': ('collapse',)}),
        ('Metadata', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def save_model(self, request, obj, form, change):
        if not change and not obj.approved_by:
            obj.approved_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'year', 'allocated_days', 'used_days', 'carried_over', 'remaining_days')
    list_filter = ('leave_type', 'year')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__organization_id')
    autocomplete_fields = ('employee',)
    fieldsets = (
        (None, {'fields': ('employee', 'leave_type', 'year')}),
        ('Balance', {'fields': ('allocated_days', 'used_days', 'carried_over')}),
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
        ('Recipient', {'fields': ('employee', 'is_read', 'link')}),
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


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'model_name', 'object_repr', 'ip_address')
    list_filter = ('action', 'model_name', 'timestamp')
    search_fields = ('user__username', 'object_repr', 'model_name')
    readonly_fields = ('timestamp',)
    list_per_page = 25


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
        ('Timing', {'fields': ('requested_at', 'dispatched_at', 'completed_at'), 'classes': ('collapse',)}),
        ('Errors', {'fields': ('error_message',), 'classes': ('collapse',)}),
    )


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization_id', 'first_name', 'last_name', 'department', 'team', 'job_title', 'employment_type', 'employment_status', 'fingerprint_id', 'enrollment_status')
    list_filter = ('department', 'team', 'job_title', 'employment_type', 'employment_status', 'office_location')
    search_fields = ('organization_id', 'first_name', 'last_name', 'email', 'fingerprint_id')
    autocomplete_fields = ('department', 'office_location', 'team', 'manager', 'attendance_policy')
    change_form_template = 'admin/attendance/employee/change_form.html'
    actions = ('register_fingerprint_action',)
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 25
    fieldsets = (
        ('Personal Information', {'fields': ('organization_id', 'first_name', 'last_name', 'email', 'phone', 'date_of_birth', 'gender', 'address')}),
        ('Employment', {'fields': ('department', 'team', 'manager', 'job_title', 'employment_type', 'employment_status', 'office_location', 'work_location_name', 'hire_date')}),
        ('Contract', {'fields': ('contract_start_date', 'contract_end_date', 'resignation_date', 'termination_date'), 'classes': ('collapse',)}),
        ('Working Hours', {'fields': ('weekly_working_days', 'expected_weekly_hours', 'expected_monthly_hours')}),
        ('Attendance', {'fields': ('attendance_policy',)}),
        ('Biometrics', {'fields': ('fingerprint_id', 'face_profile'), 'description': 'Fingerprint ID is assigned during enrollment.'}),
        ('Emergency Contact', {'fields': ('emergency_contact_name', 'emergency_contact_phone'), 'classes': ('collapse',)}),
        ('Metadata', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
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
        return BiometricDevice.objects.filter(
            is_active=True,
        ).exclude(
            status=BiometricDevice.Status.OFFLINE,
        ).order_by('name').first()

    def _get_or_create_enrollment(self, employee, device):
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
        if queryset.count() != 1:
            self.message_user(
                request,
                'Select exactly one employee to register a fingerprint.',
                level=messages.WARNING,
            )
            return

        employee = queryset.first()

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
                'No active biometric device available. Connect a device first.',
                level=messages.ERROR,
            )
            return

        enrollment, already_in_progress = self._get_or_create_enrollment(employee, device)

        if not already_in_progress:
            self._dispatch_to_hardware(enrollment, device, employee)

        return redirect('enroll_scan', enrollment_id=enrollment.pk)

    register_fingerprint_action.short_description = 'Enroll Fingerprint'

    def enroll_fingerprint_view(self, request, object_id):
        employee = get_object_or_404(Employee, pk=object_id)

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


@admin.register(BiometricDevice)
class BiometricDeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'device_id', 'device_type', 'mode', 'status', 'template_count', 'firmware_version', 'last_seen_at', 'is_active')
    list_filter = ('device_type', 'mode', 'status', 'is_active')
    search_fields = ('device_id', 'name', 'firmware_version')
    readonly_fields = ('created_at', 'updated_at', 'last_seen_at')
    fieldsets = (
        ('Device Info', {'fields': ('device_id', 'name', 'device_type', 'is_active')}),
        ('Connection', {'fields': ('serial_port', 'baudrate', 'ip_address', 'mac_address')}),
        ('Location', {'fields': ('office_location', 'building_name', 'floor_number', 'assigned_branch')}),
        ('Status', {'fields': ('mode', 'status', 'firmware_version', 'template_count', 'last_seen_at', 'last_error')}),
        ('Health', {'fields': ('health_check_interval', 'last_health_check')}),
        ('Metadata', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(DeviceCommand)
class DeviceCommandAdmin(admin.ModelAdmin):
    list_display = ('command', 'device', 'employee', 'status', 'created_at', 'sent_at', 'completed_at')
    list_filter = ('command', 'status')
    search_fields = ('device__device_id', 'employee__first_name', 'employee__last_name')
    autocomplete_fields = ('device', 'employee')
    readonly_fields = ('created_at', 'sent_at', 'completed_at')


@admin.register(DeviceEvent)
class DeviceEventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'device', 'event_type', 'employee', 'message')
    list_filter = ('event_type', 'device')
    search_fields = ('device__device_id', 'message', 'employee__first_name')
    autocomplete_fields = ('device', 'employee')
    readonly_fields = ('created_at',)
    list_per_page = 25
