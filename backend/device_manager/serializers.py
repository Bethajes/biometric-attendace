from rest_framework import serializers

from attendance.models import (
    BiometricDevice,
    DeviceCommand,
    DeviceEvent,
    EnrollmentRequest,
)


class BiometricDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = BiometricDevice
        fields = [
            'id', 'device_id', 'name', 'serial_port', 'baudrate',
            'mode', 'status', 'firmware_version', 'template_count',
            'last_seen_at', 'last_error', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['last_seen_at', 'created_at', 'updated_at']


class DeviceCommandSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.device_id', read_only=True)
    employee_name = serializers.CharField(
        source='employee.full_name', read_only=True, default='',
    )

    class Meta:
        model = DeviceCommand
        fields = [
            'id', 'device', 'device_name', 'employee', 'employee_name',
            'command', 'payload', 'status', 'raw_command', 'response',
            'error_message', 'created_at', 'sent_at', 'completed_at',
        ]
        read_only_fields = ['created_at', 'sent_at', 'completed_at']


class DeviceEventSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.device_id', read_only=True)
    employee_name = serializers.CharField(
        source='employee.full_name', read_only=True, default='',
    )

    class Meta:
        model = DeviceEvent
        fields = [
            'id', 'device', 'device_name', 'employee', 'employee_name',
            'event_type', 'status', 'message', 'fingerprint_id',
            'error_message', 'created_at',
        ]
        read_only_fields = ['created_at']


class EnrollmentRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source='employee.full_name', read_only=True,
    )
    device_name = serializers.CharField(
        source='device.name', read_only=True, default='',
    )

    class Meta:
        model = EnrollmentRequest
        fields = [
            'id', 'employee', 'employee_name', 'fingerprint_id',
            'status', 'device', 'device_name', 'progress_message',
            'requested_at', 'dispatched_at', 'completed_at',
            'error_message',
        ]
        read_only_fields = [
            'requested_at', 'dispatched_at', 'completed_at',
        ]
