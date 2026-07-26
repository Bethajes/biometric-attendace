import logging
import signal
import sys
import threading
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import (
    BiometricDevice,
    DeviceCommand,
    EnrollmentRequest,
)
from device_manager.services.hardware_service import get_hardware_service

logger = logging.getLogger('device_manager.listen_devices')


class Command(BaseCommand):
    help = 'Start the device listener that reads Arduino serial messages and processes them in Django'

    def add_arguments(self, parser):
        parser.add_argument(
            '--device-id', type=int,
            help='Listen to a specific device ID (default: all active devices)',
        )
        parser.add_argument(
            '--enroll-poll', type=int, default=1,
            help='Enrollment poll interval in seconds (default: 1)',
        )

    def handle(self, *args, **options):
        global logger
        logger = logging.getLogger('device_manager.listen_devices')

        svc = get_hardware_service()
        device_id = options.get('device_id')
        enroll_poll_interval = options.get('enroll_poll')

        if device_id:
            devices = BiometricDevice.objects.filter(pk=device_id, is_active=True)
        else:
            devices = BiometricDevice.objects.filter(is_active=True)

        if not devices.exists():
            self.stderr.write(self.style.ERROR('No active devices found.'))
            return

        # Track devices we started so we can clean up on shutdown
        started_devices = []

        for device in devices:
            self.stdout.write(f'Starting listener for {device.name} ({device.serial_port})...')
            if svc.start_listener(device):
                self.stdout.write(self.style.SUCCESS(f'  Listener active for {device.device_id}'))
                started_devices.append(device)
            else:
                self.stderr.write(self.style.ERROR(f'  Failed to start listener for {device.device_id}'))

        if not started_devices:
            self.stderr.write(self.style.ERROR('No listeners started. Exiting.'))
            return

        self.stdout.write(self.style.SUCCESS(
            f'{len(started_devices)} listener(s) active. Polling enrollments every {enroll_poll_interval}s. Press Ctrl+C to stop.'
        ))

        # Graceful shutdown handler
        def _shutdown(signum, frame):
            self.stdout.write('\nShutting down listeners...')
            for device in started_devices:
                svc.stop_listener(device)
                device.status = BiometricDevice.Status.OFFLINE
                device.save(update_fields=['status'])
                svc._push_device_status_broadcast(device)
                self.stdout.write(f'  Stopped {device.name}')
            self.stdout.write(self.style.SUCCESS('Done.'))
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        # ── Enrollment polling thread ──────────────────────────────────────
        # Actively polls for PENDING or DISPATCHED EnrollmentRequest records
        # and sends ENROLL:<id>\n directly via the serial connection.

        def enrollment_poller():
            logger.info('Enrollment poller started (interval=%ds)', enroll_poll_interval)
            while True:
                try:
                    _poll_enrollments(svc, started_devices, logger)
                except Exception:
                    logger.exception('Error in enrollment poller')
                time.sleep(enroll_poll_interval)

        poll_thread = threading.Thread(target=enrollment_poller, daemon=True,
                                       name='enrollment-poller')
        poll_thread.start()

        # Keep main thread alive — listeners run in daemon threads
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            _shutdown(None, None)


def _poll_enrollments(svc, devices, log):
    """Pick up enrolment requests and dispatch the ENROLL serial command.

    Two paths bring an enrollment here:

    Path A (normal): api_start_enrollment → start_enrollment → send_command
        creates a QUEUED DeviceCommand with status=DISPATCHED on the request.

    Path B (safety net): if the DeviceCommand was never created (e.g. the
        web process crashed after creating the EnrollmentRequest but before
        send_command), the request stays PENDING.  This poller catches both.
    """
    for device in devices:
        # ── 1. Always pick up QUEUED DeviceCommands ────────────────────
        try:
            svc.poll_queued_commands(device)
        except Exception:
            log.exception('Error polling queued commands for %s', device.device_id)

        # ── 2. Find enrollments that need the serial ENROLL command ────
        #    Covers both PENDING (safety net) and DISPATCHED (normal path).
        pending_enrollments = EnrollmentRequest.objects.filter(
            device=device,
            status__in=[
                EnrollmentRequest.Status.PENDING,
                EnrollmentRequest.Status.DISPATCHED,
            ],
        ).select_related('employee').order_by('requested_at')

        for enrollment in pending_enrollments:
            # Skip if a QUEUED DeviceCommand already covers this enrollment
            has_queued = DeviceCommand.objects.filter(
                enrollment_request=enrollment,
                status=DeviceCommand.Status.QUEUED,
            ).exists()
            if has_queued:
                continue

            # Also skip if a SENT command is already in flight
            has_sent = DeviceCommand.objects.filter(
                enrollment_request=enrollment,
                status=DeviceCommand.Status.SENT,
            ).exists()
            if has_sent:
                continue

            conn = svc.get_connection(device)
            if not conn:
                log.warning('No serial connection for %s, cannot dispatch enrollment %d',
                            device.device_id, enrollment.id)
                continue

            # Transition PENDING → DISPATCHED if needed
            if enrollment.status == EnrollmentRequest.Status.PENDING:
                enrollment.status = EnrollmentRequest.Status.DISPATCHED
                enrollment.dispatched_at = timezone.now()
                enrollment.save(update_fields=['status', 'dispatched_at'])

            raw_cmd = f"ENROLL:{enrollment.fingerprint_id}"
            sent = conn.send(raw_cmd)
            if sent:
                log.info('Dispatched enrollment %d → %s (fp_id=%d)',
                         enrollment.id, device.device_id, enrollment.fingerprint_id)

                DeviceCommand.objects.create(
                    device=device,
                    employee=enrollment.employee,
                    enrollment_request=enrollment,
                    command=DeviceCommand.Command.ENROLL,
                    payload={'fingerprint_id': enrollment.fingerprint_id},
                    raw_command=raw_cmd,
                    status=DeviceCommand.Status.SENT,
                    sent_at=timezone.now(),
                )

                device.mode = BiometricDevice.Mode.ENROLLMENT
                device.status = BiometricDevice.Status.BUSY
                device.last_seen_at = timezone.now()
                device.save(update_fields=['mode', 'status', 'last_seen_at'])
            else:
                log.error('Failed to send ENROLL:%d to %s',
                          enrollment.fingerprint_id, device.device_id)
