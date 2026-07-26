import json
import logging

from django.contrib import messages
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, ListView, TemplateView

from attendance.models import (
    BiometricDevice,
    DeviceCommand,
    DeviceEvent,
    Employee,
    EnrollmentRequest,
)
from attendance.views import EnterpriseContextMixin, EnterpriseListMixin

from .services.hardware_service import get_hardware_service

logger = logging.getLogger('device_manager.views')


# ---------------------------------------------------------------------------
# Device Dashboard
# ---------------------------------------------------------------------------

class DeviceDashboardView(EnterpriseContextMixin, TemplateView):
    template_name = 'device_manager/device_dashboard.html'
    page_title = 'Device Manager'
    active_nav = 'devices'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        devices = BiometricDevice.objects.all()
        ctx.update({
            'devices': devices,
            'device_count': devices.count(),
            'online_count': devices.filter(status=BiometricDevice.Status.ONLINE).count(),
            'active_enrollments': EnrollmentRequest.objects.filter(
                status__in=[EnrollmentRequest.Status.PENDING,
                            EnrollmentRequest.Status.DISPATCHED,
                            EnrollmentRequest.Status.IN_PROGRESS],
            ).select_related('employee', 'device'),
            'recent_events': DeviceEvent.objects.select_related(
                'device', 'employee',
            ).order_by('-created_at')[:25],
            'pending_commands': DeviceCommand.objects.filter(
                status__in=[DeviceCommand.Status.QUEUED, DeviceCommand.Status.SENT],
            ).select_related('device', 'employee'),
        })
        return ctx


# ---------------------------------------------------------------------------
# Device list / detail
# ---------------------------------------------------------------------------

class DeviceListView(EnterpriseListMixin):
    model = BiometricDevice
    template_name = 'device_manager/device_list.html'
    page_title = 'Biometric Devices'
    active_nav = 'devices'
    search_fields = ['device_id', 'name', 'firmware_version']
    default_ordering = 'name'
    paginate_by = 15
    export_filename = 'devices'
    export_fields = [
        ('device_id', 'Device ID'),
        ('name', 'Name'),
        ('serial_port', 'Port'),
        ('mode', 'Mode'),
        ('status', 'Status'),
        ('template_count', 'Templates'),
        ('firmware_version', 'Firmware'),
        ('last_seen_at', 'Last Seen'),
    ]


class DeviceDetailView(EnterpriseContextMixin, DetailView):
    model = BiometricDevice
    template_name = 'device_manager/device_detail.html'
    page_title = 'Device Detail'
    active_nav = 'devices'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        device = self.object
        ctx.update({
            'commands': device.commands.order_by('-created_at')[:30],
            'events': device.events.select_related(
                'employee', 'enrollment_request',
            ).order_by('-created_at')[:50],
            'enrollments': device.enrollment_requests.select_related(
                'employee',
            ).order_by('-requested_at')[:20],
        })
        return ctx


# ---------------------------------------------------------------------------
# Enrollment panel (select employee → register fingerprint)
# ---------------------------------------------------------------------------

class EnrollmentPanelView(EnterpriseContextMixin, TemplateView):
    template_name = 'device_manager/enrollment_panel.html'
    page_title = 'Fingerprint Enrollment'
    active_nav = 'devices'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        active_device = BiometricDevice.objects.filter(
            is_active=True,
        ).exclude(status=BiometricDevice.Status.OFFLINE).first()

        enrolled_ids = EnrollmentRequest.objects.filter(
            status__in=[EnrollmentRequest.Status.PENDING,
                        EnrollmentRequest.Status.DISPATCHED,
                        EnrollmentRequest.Status.IN_PROGRESS],
        ).values_list('employee_id', flat=True)

        employees = Employee.objects.filter(
            employment_status=Employee.EmploymentStatus.ACTIVE,
        ).exclude(id__in=enrolled_ids).order_by('first_name')

        ctx.update({
            'active_device': active_device,
            'devices': BiometricDevice.objects.filter(is_active=True),
            'employees': employees,
            'active_enrollments': EnrollmentRequest.objects.filter(
                status__in=[EnrollmentRequest.Status.PENDING,
                            EnrollmentRequest.Status.DISPATCHED,
                            EnrollmentRequest.Status.IN_PROGRESS],
            ).select_related('employee', 'device').order_by('requested_at'),
            'recent_completions': EnrollmentRequest.objects.filter(
                status=EnrollmentRequest.Status.COMPLETED,
            ).select_related('employee').order_by('-completed_at')[:10],
        })
        return ctx


# ---------------------------------------------------------------------------
# Communication logs
# ---------------------------------------------------------------------------

class DeviceLogsView(EnterpriseListMixin):
    model = DeviceEvent
    template_name = 'device_manager/logs.html'
    page_title = 'Communication Logs'
    active_nav = 'devices'
    search_fields = ['message', 'device__device_id', 'employee__first_name',
                     'employee__last_name']
    default_ordering = '-created_at'
    paginate_by = 25
    export_filename = 'device_logs'
    export_fields = [
        ('created_at', 'Timestamp'),
        ('device__device_id', 'Device'),
        ('event_type', 'Event'),
        ('employee__full_name', 'Employee'),
        ('message', 'Message'),
        ('error_message', 'Error'),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('device', 'employee')
        event_type = self.request.GET.get('event_type')
        device_id = self.request.GET.get('device')
        if event_type:
            qs = qs.filter(event_type=event_type)
        if device_id:
            qs = qs.filter(device_id=device_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['event_types'] = DeviceEvent.EventType.choices
        ctx['all_devices'] = BiometricDevice.objects.all()
        return ctx


# ---------------------------------------------------------------------------
# AJAX API endpoints
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def api_connect_device(request, device_id):
    device = get_object_or_404(BiometricDevice, pk=device_id)
    svc = get_hardware_service()
    ok = svc.connect_device(device)
    return JsonResponse({
        'status': 'connected' if ok else 'failed',
        'device_status': device.status,
    })


@csrf_exempt
@require_POST
def api_disconnect_device(request, device_id):
    device = get_object_or_404(BiometricDevice, pk=device_id)
    svc = get_hardware_service()
    svc.disconnect_device(device)
    return JsonResponse({'status': 'disconnected'})


@csrf_exempt
@require_POST
def api_start_enrollment(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    device_id = data.get('device_id')
    employee_id = data.get('employee_id')

    if not device_id or not employee_id:
        return JsonResponse({'error': 'device_id and employee_id required'}, status=400)

    try:
        device = get_object_or_404(BiometricDevice, pk=device_id)
        employee = get_object_or_404(Employee, pk=employee_id)
    except Exception:
        return JsonResponse({'error': 'Device or employee not found'}, status=404)

    if employee.fingerprint_id:
        fingerprint_id = employee.fingerprint_id
    else:
        max_id = Employee.objects.aggregate(m=Max('fingerprint_id')).get('m') or 0
        fingerprint_id = max_id + 1
        employee.fingerprint_id = fingerprint_id
        employee.save(update_fields=['fingerprint_id'])

    # If device is stuck BUSY with no real pending commands, reset it.
    if device.status == BiometricDevice.Status.BUSY:
        has_pending = DeviceCommand.objects.filter(
            device=device,
            status__in=[DeviceCommand.Status.QUEUED, DeviceCommand.Status.SENT],
        ).exists()
        if not has_pending:
            device.status = BiometricDevice.Status.ONLINE
            device.save(update_fields=['status'])

    try:
        svc = get_hardware_service()
        result = svc.start_enrollment(device, employee, fingerprint_id)
    except Exception as exc:
        logger.exception('start_enrollment failed')
        return JsonResponse({'error': str(exc)}, status=500)

    return JsonResponse({
        'status': 'ok' if result.success else 'error',
        'message': result.message,
        'command_id': result.command_id,
        'enrollment_id': result.enrollment_id,
    })


@csrf_exempt
@require_POST
def api_delete_fingerprint(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    device_id = data.get('device_id')
    fingerprint_id = data.get('fingerprint_id')

    if not device_id or not fingerprint_id:
        return JsonResponse({'error': 'device_id and fingerprint_id required'}, status=400)

    device = get_object_or_404(BiometricDevice, pk=device_id)
    employee = Employee.objects.filter(fingerprint_id=fingerprint_id).first()

    svc = get_hardware_service()
    result = svc.delete_fingerprint(device, int(fingerprint_id), employee)

    return JsonResponse({
        'status': 'ok' if result.success else 'error',
        'message': result.message,
        'command_id': result.command_id,
    })


@csrf_exempt
@require_POST
def api_restart_device(request, device_id):
    device = get_object_or_404(BiometricDevice, pk=device_id)
    svc = get_hardware_service()
    result = svc.restart_device(device)
    return JsonResponse({
        'status': 'ok' if result.success else 'error',
        'message': result.message,
    })


@csrf_exempt
@require_POST
def api_request_status(request, device_id):
    device = get_object_or_404(BiometricDevice, pk=device_id)
    svc = get_hardware_service()
    result = svc.request_status(device)
    return JsonResponse({
        'status': 'ok' if result.success else 'error',
        'message': result.message,
    })


@csrf_exempt
@require_POST
def api_return_to_attendance(request, device_id):
    device = get_object_or_404(BiometricDevice, pk=device_id)
    svc = get_hardware_service()
    result = svc.return_to_attendance(device)
    return JsonResponse({
        'status': 'ok' if result.success else 'error',
        'message': result.message,
    })


@require_GET
def api_device_status(request, device_id):
    device = get_object_or_404(BiometricDevice, pk=device_id)
    return JsonResponse({
        'device_id': device.device_id,
        'name': device.name,
        'mode': device.mode,
        'status': device.status,
        'template_count': device.template_count,
        'firmware_version': device.firmware_version,
        'last_seen_at': device.last_seen_at.isoformat() if device.last_seen_at else None,
        'last_error': device.last_error,
    })


@require_GET
def api_enrollment_progress(request, enrollment_id):
    enrollment = get_object_or_404(
        EnrollmentRequest.objects.select_related('employee', 'device'),
        pk=enrollment_id,
    )
    return JsonResponse({
        'id': enrollment.id,
        'status': enrollment.status,
        'progress_message': enrollment.progress_message,
        'employee_name': enrollment.employee.full_name,
        'fingerprint_id': enrollment.fingerprint_id,
        'device_name': enrollment.device.name if enrollment.device else None,
        'error_message': enrollment.error_message,
        'requested_at': enrollment.requested_at.isoformat(),
        'completed_at': enrollment.completed_at.isoformat() if enrollment.completed_at else None,
    })


@require_GET
def api_recent_events(request):
    limit = min(int(request.GET.get('limit', 20)), 100)
    events = DeviceEvent.objects.select_related(
        'device', 'employee',
    ).order_by('-created_at')[:limit]
    return JsonResponse({
        'events': [
            {
                'id': e.id,
                'device': e.device.device_id,
                'event_type': e.event_type,
                'message': e.message,
                'employee': e.employee.full_name if e.employee else None,
                'error_message': e.error_message,
                'created_at': e.created_at.isoformat(),
            }
            for e in events
        ],
    })


@require_GET
def api_enrollment_list(request):
    enrollments = EnrollmentRequest.objects.filter(
        status__in=[EnrollmentRequest.Status.PENDING,
                    EnrollmentRequest.Status.DISPATCHED,
                    EnrollmentRequest.Status.IN_PROGRESS,
                    EnrollmentRequest.Status.COMPLETED],
    ).select_related('employee', 'device').order_by('-requested_at')[:20]
    return JsonResponse({
        'enrollments': [
            {
                'id': e.id,
                'employee_name': e.employee.full_name,
                'fingerprint_id': e.fingerprint_id,
                'status': e.status,
                'progress_message': e.progress_message,
                'device': e.device.name if e.device else None,
                'error_message': e.error_message,
                'requested_at': e.requested_at.isoformat(),
                'completed_at': e.completed_at.isoformat() if e.completed_at else None,
            }
            for e in enrollments
        ],
    })


@csrf_exempt
@require_POST
def api_process_arduino_message(request, device_id):
    """Endpoint for the bridge to push Arduino messages into Django."""
    device = get_object_or_404(BiometricDevice, pk=device_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    raw = data.get('message', '')
    if not raw:
        return JsonResponse({'error': 'message field required'}, status=400)

    svc = get_hardware_service()
    svc.process_message(device, raw)
    return JsonResponse({'status': 'processed'})
