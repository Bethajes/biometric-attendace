import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger('attendance.consumers')


class DeviceEventConsumer(AsyncWebsocketConsumer):
    """Receives real-time events for a specific biometric device."""

    async def connect(self):
        self.device_id = self.scope['url_route']['kwargs']['device_id']
        self.group_name = f'device_{self.device_id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        from attendance.models import BiometricDevice
        device = await self._get_device()
        if device:
            await self.send(text_data=json.dumps({
                'type': 'device_status',
                'device_id': device['device_id'],
                'name': device['name'],
                'status': device['status'],
                'mode': device['mode'],
                'template_count': device['template_count'],
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass

    async def device_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'device_event',
            'event_type': event.get('event_type', ''),
            'message': event.get('message', ''),
            'employee': event.get('employee', None),
            'fingerprint_id': event.get('fingerprint_id', None),
            'timestamp': event.get('timestamp', ''),
            'error_message': event.get('error_message', ''),
        }))

    async def device_status_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'device_status_update',
            'status': event.get('status', ''),
            'mode': event.get('mode', ''),
            'template_count': event.get('template_count', 0),
            'last_seen_at': event.get('last_seen_at', ''),
        }))

    async def enrollment_progress(self, event):
        await self.send(text_data=json.dumps({
            'type': 'enrollment_progress',
            'status': event.get('status', ''),
            'progress_message': event.get('progress_message', ''),
            'fingerprint_id': event.get('fingerprint_id', None),
        }))

    async def enrollment_complete(self, event):
        await self.send(text_data=json.dumps({
            'type': 'enrollment_complete',
            'employee_name': event.get('employee_name', ''),
            'fingerprint_id': event.get('fingerprint_id', None),
        }))

    async def enrollment_failed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'enrollment_failed',
            'error_message': event.get('error_message', ''),
        }))

    async def _get_device(self):
        from asgiref.sync import sync_to_async
        from attendance.models import BiometricDevice
        try:
            device = await sync_to_async(
                BiometricDevice.objects.filter(pk=self.device_id).values(
                    'device_id', 'name', 'status', 'mode', 'template_count',
                ).first
            )()
            return device
        except Exception:
            return None


class EnrollmentProgressConsumer(AsyncWebsocketConsumer):
    """Receives real-time progress for a specific enrollment request."""

    async def connect(self):
        self.enrollment_id = self.scope['url_route']['kwargs']['enrollment_id']
        self.group_name = f'enrollment_{self.enrollment_id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        from asgiref.sync import sync_to_async
        from attendance.models import EnrollmentRequest
        try:
            enrollment = await sync_to_async(
                EnrollmentRequest.objects.filter(pk=self.enrollment_id).values(
                    'status', 'progress_message', 'fingerprint_id',
                    'employee__first_name', 'employee__last_name',
                    'error_message',
                ).first
            )()
            if enrollment:
                await self.send(text_data=json.dumps({
                    'type': 'enrollment_status',
                    'status': enrollment['status'],
                    'progress_message': enrollment['progress_message'],
                    'fingerprint_id': enrollment['fingerprint_id'],
                    'employee_name': f"{enrollment['employee__first_name']} {enrollment['employee__last_name']}",
                }))
        except Exception:
            pass

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass

    async def enrollment_progress(self, event):
        await self.send(text_data=json.dumps({
            'type': 'enrollment_progress',
            'status': event.get('status', ''),
            'progress_message': event.get('progress_message', ''),
            'fingerprint_id': event.get('fingerprint_id', None),
        }))

    async def enrollment_complete(self, event):
        await self.send(text_data=json.dumps({
            'type': 'enrollment_complete',
            'employee_name': event.get('employee_name', ''),
            'fingerprint_id': event.get('fingerprint_id', None),
        }))

    async def enrollment_failed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'enrollment_failed',
            'error_message': event.get('error_message', ''),
        }))


class DeviceDashboardConsumer(AsyncWebsocketConsumer):
    """Broadcasts device-wide events to the device dashboard page."""

    async def connect(self):
        self.group_name = 'device_dashboard'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass

    async def dashboard_device_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'device_event',
            'device_id': event.get('device_id', ''),
            'device_name': event.get('device_name', ''),
            'event_type': event.get('event_type', ''),
            'message': event.get('message', ''),
            'employee': event.get('employee', None),
            'timestamp': event.get('timestamp', ''),
        }))

    async def dashboard_device_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'device_status_update',
            'device_id': event.get('device_id', ''),
            'status': event.get('status', ''),
            'mode': event.get('mode', ''),
        }))

    async def dashboard_enrollment_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'enrollment_update',
            'enrollment_id': event.get('enrollment_id', ''),
            'employee_name': event.get('employee_name', ''),
            'status': event.get('status', ''),
            'progress_message': event.get('progress_message', ''),
        }))


class DashboardLiveActivityConsumer(AsyncWebsocketConsumer):
    """Pushes real-time attendance scans to the main dashboard table."""

    async def connect(self):
        self.group_name = 'dashboard_live_activity'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass

    async def dashboard_attendance_event(self, event):
        await self.send(text_data=json.dumps({
            'type': 'attendance_event',
            'device_id': event.get('device_id', ''),
            'device_name': event.get('device_name', ''),
            'fingerprint_id': event.get('fingerprint_id', None),
            'employee_id': event.get('employee_id', None),
            'employee_name': event.get('employee_name', ''),
            'organization_id': event.get('organization_id', ''),
            'department': event.get('department', ''),
            'job_title': event.get('job_title', ''),
            'scan_type': event.get('scan_type', ''),
            'status': event.get('status', ''),
            'message': event.get('message', ''),
            'timestamp': event.get('timestamp', ''),
        }))
