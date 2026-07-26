from django.contrib import admin

from attendance.models import BiometricDevice, DeviceCommand, DeviceEvent


@admin.register(BiometricDevice)
class BiometricDeviceAdmin(admin.ModelAdmin):
	list_display = (
		'id', 'device_id', 'name', 'serial_port', 'mode',
		'status', 'template_count', 'firmware_version',
		'last_seen_at', 'is_active',
	)
	list_filter = ('mode', 'status', 'is_active')
	search_fields = ('device_id', 'name', 'serial_port')
	readonly_fields = ('created_at', 'updated_at', 'last_seen_at')
	list_per_page = 25
	fieldsets = (
		('Device Identity', {
			'fields': ('device_id', 'name', 'is_active'),
		}),
		('Connection', {
			'fields': ('serial_port', 'baudrate'),
		}),
		('Current State', {
			'fields': ('mode', 'status', 'template_count', 'firmware_version'),
		}),
		('Diagnostics', {
			'fields': ('last_seen_at', 'last_error'),
			'classes': ('collapse',),
		}),
		('Metadata', {
			'fields': ('created_at', 'updated_at'),
			'classes': ('collapse',),
		}),
	)


@admin.register(DeviceCommand)
class DeviceCommandAdmin(admin.ModelAdmin):
	list_display = (
		'id', 'device', 'command', 'employee', 'status',
		'created_at', 'sent_at', 'completed_at',
	)
	list_filter = ('command', 'status')
	search_fields = (
		'device__device_id', 'employee__first_name',
		'employee__last_name', 'raw_command', 'response',
	)
	autocomplete_fields = ('device', 'employee')
	readonly_fields = (
		'device', 'employee', 'enrollment_request', 'command',
		'payload', 'raw_command', 'status', 'response',
		'error_message', 'created_at', 'sent_at', 'completed_at',
	)
	list_per_page = 25
	has_add_permission = lambda self, request: False
	fieldsets = (
		('Command', {
			'fields': ('device', 'command', 'employee', 'enrollment_request'),
		}),
		('Payload & Protocol', {
			'fields': ('payload', 'raw_command'),
			'classes': ('collapse',),
		}),
		('Status', {
			'fields': ('status', 'response', 'error_message'),
		}),
		('Timing', {
			'fields': ('created_at', 'sent_at', 'completed_at'),
		}),
	)

	def has_change_permission(self, request, obj=None):
		return False


@admin.register(DeviceEvent)
class DeviceEventAdmin(admin.ModelAdmin):
	list_display = (
		'id', 'device', 'event_type', 'employee',
		'fingerprint_id', 'message', 'created_at',
	)
	list_filter = ('event_type', 'device')
	search_fields = ('message', 'device__device_id', 'employee__first_name')
	autocomplete_fields = ('device', 'employee')
	readonly_fields = (
		'device', 'employee', 'command', 'enrollment_request',
		'event_type', 'status', 'message', 'fingerprint_id',
		'payload', 'error_message', 'created_at',
	)
	list_per_page = 25
	has_add_permission = lambda self, request: False
	fieldsets = (
		('Event', {
			'fields': ('device', 'event_type', 'message'),
		}),
		('Context', {
			'fields': ('employee', 'command', 'enrollment_request', 'fingerprint_id'),
		}),
		('Details', {
			'fields': ('status', 'payload', 'error_message'),
			'classes': ('collapse',),
		}),
		('Metadata', {
			'fields': ('created_at',),
		}),
	)

	def has_change_permission(self, request, obj=None):
		return False
