"""
Hardware Service — isolates all Arduino serial communication from business logic.

Protocol (text-over-serial, newline-delimited):
    Django → Arduino:
        ENROLL:<fingerprint_id>          Switch to enrollment mode and enroll
        DELETE:<fingerprint_id>           Delete a fingerprint template
        VERIFY:<fingerprint_id>           Verify a fingerprint
        ATTENDANCE                       Switch to attendance mode
        DEVICE_STATUS                    Request device status
        RESTART                          Restart the Arduino
        DELETE_ALL                       Delete all templates
        GET_COUNT                        Query stored template count

    Arduino → Django:
        ENROLL_PROGRESS:<step>:<message> Enrollment progress update
        ENROLL_SUCCESS:<fingerprint_id>  Enrollment completed
        ENROLL_FAIL:<message>            Enrollment failed
        DELETED:<fingerprint_id>         Template deleted
        DELETE_FAIL:<message>            Deletion failed
        MATCH:<fingerprint_id>:<score>   Fingerprint matched
        NO_MATCH                         No match found
        STATUS:<mode>:<template_count>:<firmware>  Device status
        ACK:<command>                    Command acknowledged
        ERROR:<message>                  Generic error
        INFO:<message>                   Informational
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import serial
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from attendance.models import (
    AttendanceLog,
    AttendanceRecord,
    BiometricDevice,
    DeviceCommand,
    DeviceEvent,
    Employee,
    EnrollmentRequest,
)
from attendance.services.attendance_engine import AttendanceEngine

logger = logging.getLogger('device_manager.hardware')


# ---------------------------------------------------------------------------
# Data containers returned by the service
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProtocolMessage:
    raw: str
    kind: str
    parts: list = field(default_factory=list)


@dataclass
class CommandResult:
    success: bool
    command_id: int
    message: str = ''
    raw_response: str = ''
    enrollment_id: int = 0


# ---------------------------------------------------------------------------
# Serial connection wrapper (testable, thread-safe)
# ---------------------------------------------------------------------------

class SerialConnection:
    """Manages the raw serial link to a single Arduino device."""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> bool:
        try:
            self._serial = serial.Serial(
                self.port, self.baudrate, timeout=self.timeout,
            )
            time.sleep(2)  # Arduino reset debounce
            logger.info('Serial connected: %s @ %d', self.port, self.baudrate)
            return True
        except Exception as exc:
            logger.error('Serial connect failed: %s', exc)
            return False

    def disconnect(self):
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info('Serial disconnected: %s', self.port)

    def send(self, data: str) -> bool:
        if not self.is_connected:
            logger.warning('Send on disconnected port %s', self.port)
            return False
        with self._lock:
            try:
                self._serial.write((data + '\n').encode('utf-8'))
                logger.debug('TX → %s: %s', self.port, data)
                return True
            except Exception as exc:
                logger.error('Send error on %s: %s', self.port, exc)
                return False

    def readline(self) -> Optional[str]:
        if not self.is_connected:
            return None
        try:
            if self._serial.in_waiting > 0:
                line = self._serial.readline().decode('utf-8', errors='replace').strip()
                if line:
                    logger.debug('RX ← %s: %s', self.port, line)
                    return line
        except Exception as exc:
            logger.error('Read error on %s: %s', self.port, exc)
        return None


# ---------------------------------------------------------------------------
# Protocol parser
# ---------------------------------------------------------------------------

class ProtocolParser:
    """Parses raw Arduino messages into ProtocolMessage objects."""

    @staticmethod
    def parse(raw: str) -> ProtocolMessage:
        parts = raw.split(':')
        kind = parts[0] if parts else 'UNKNOWN'
        return ProtocolMessage(raw=raw, kind=kind, parts=parts)


# ---------------------------------------------------------------------------
# Hardware Service — the public API used by views and the bridge
# ---------------------------------------------------------------------------

class HardwareService:
    """
    Orchestrates all communication between Django and the Arduino fleet.

    Responsibilities:
    - Send structured commands via DeviceCommand records
    - Parse incoming serial responses and create DeviceEvent records
    - Track device mode, status, and last-seen timestamps
    - Manage enrollment lifecycle end-to-end
    """

    def __init__(self):
        self._connections: dict[str, SerialConnection] = {}
        self._listener_threads: dict[str, threading.Thread] = {}
        self._running = False

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect_device(self, device: BiometricDevice) -> bool:
        if device.device_id in self._connections and self._connections[device.device_id].is_connected:
            return True

        conn = SerialConnection(device.serial_port, device.baudrate)
        if conn.connect():
            self._connections[device.device_id] = conn
            device.status = BiometricDevice.Status.ONLINE
            device.last_seen_at = timezone.now()
            device.save(update_fields=['status', 'last_seen_at'])
            self._log_event(device, DeviceEvent.EventType.DEVICE_STATUS,
                            message='Device connected')
            return True

        device.status = BiometricDevice.Status.OFFLINE
        device.last_error = 'Connection failed'
        device.save(update_fields=['status', 'last_error'])
        return False

    def disconnect_device(self, device: BiometricDevice):
        conn = self._connections.pop(device.device_id, None)
        if conn:
            conn.disconnect()
        device.status = BiometricDevice.Status.OFFLINE
        device.save(update_fields=['status'])

    def get_connection(self, device: BiometricDevice) -> Optional[SerialConnection]:
        conn = self._connections.get(device.device_id)
        if conn and conn.is_connected:
            return conn
        return None

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def send_command(self, device: BiometricDevice, command_type: str,
                     employee: Optional[Employee] = None,
                     enrollment_request: Optional[EnrollmentRequest] = None,
                     payload: Optional[dict] = None) -> CommandResult:
        """Create a DeviceCommand, serialize it, send it over serial, and log the event."""
        payload = payload or {}

        raw_command = self._build_raw_command(command_type, payload)

        cmd = DeviceCommand.objects.create(
            device=device,
            employee=employee,
            enrollment_request=enrollment_request,
            command=command_type,
            payload=payload,
            raw_command=raw_command,
        )

        conn = self.get_connection(device)
        if not conn:
            # No in-memory serial connection in this process (multi-process setup).
            # The listener process owns the serial port.  Queue the command
            # for the listener to pick up — accept any non-OFFLINE status
            # since "BUSY" is a stale flag left by a previous send_command call.
            device.refresh_from_db()
            if device.status != BiometricDevice.Status.OFFLINE:
                cmd.status = DeviceCommand.Status.QUEUED
                cmd.save(update_fields=['status'])
                self._log_event(device, DeviceEvent.EventType.COMMAND_ACK,
                                message=f'Command queued: {command_type}',
                                command=cmd, employee=employee)
                return CommandResult(True, cmd.id, 'Command queued', raw_command)

            cmd.status = DeviceCommand.Status.FAILED
            cmd.error_message = f'Device {device.device_id} not connected'
            cmd.completed_at = timezone.now()
            cmd.save(update_fields=['status', 'error_message', 'completed_at'])
            self._log_event(device, DeviceEvent.EventType.ERROR,
                            message=cmd.error_message, command=cmd,
                            employee=employee)
            return CommandResult(False, cmd.id, cmd.error_message)

        sent = conn.send(raw_command)
        if not sent:
            cmd.status = DeviceCommand.Status.FAILED
            cmd.error_message = 'Serial write failed'
            cmd.completed_at = timezone.now()
            cmd.save(update_fields=['status', 'error_message', 'completed_at'])
            self._log_event(device, DeviceEvent.EventType.ERROR,
                            message=cmd.error_message, command=cmd,
                            employee=employee)
            return CommandResult(False, cmd.id, cmd.error_message)

        cmd.status = DeviceCommand.Status.SENT
        cmd.sent_at = timezone.now()
        cmd.save(update_fields=['status', 'sent_at'])

        device.status = BiometricDevice.Status.BUSY
        device.last_seen_at = timezone.now()
        device.save(update_fields=['status', 'last_seen_at'])

        self._log_event(device, DeviceEvent.EventType.COMMAND_ACK,
                        message=f'Command sent: {command_type}',
                        command=cmd, employee=employee)

        return CommandResult(True, cmd.id, 'Command sent', raw_command)

    def _build_raw_command(self, command_type: str, payload: dict) -> str:
        mapping = {
            DeviceCommand.Command.ENROLL: f"ENROLL:{payload.get('fingerprint_id', '')}",
            DeviceCommand.Command.DELETE: f"DELETE:{payload.get('fingerprint_id', '')}",
            DeviceCommand.Command.VERIFY: f"VERIFY:{payload.get('fingerprint_id', '')}",
            DeviceCommand.Command.DEVICE_STATUS: "DEVICE_STATUS",
            DeviceCommand.Command.RESTART: "RESTART",
            DeviceCommand.Command.MAINTENANCE: "MAINTENANCE",
            DeviceCommand.Command.ATTENDANCE_MODE: "ATTENDANCE",
        }
        return mapping.get(command_type, command_type)

    # ------------------------------------------------------------------
    # High-level enrollment workflow
    # ------------------------------------------------------------------

    def start_enrollment(self, device: BiometricDevice, employee: Employee,
                         fingerprint_id: int) -> CommandResult:
        """Full enrollment initiation: create request, create command, send to Arduino."""
        with transaction.atomic():
            # Auto-cancel stale enrollments (older than 5 min) that got stuck
            stale_cutoff = timezone.now() - timezone.timedelta(minutes=5)
            stale = EnrollmentRequest.objects.filter(
                employee=employee,
                status__in=[EnrollmentRequest.Status.PENDING,
                            EnrollmentRequest.Status.DISPATCHED,
                            EnrollmentRequest.Status.IN_PROGRESS],
                requested_at__lt=stale_cutoff,
            )
            if stale.exists():
                stale.update(status=EnrollmentRequest.Status.FAILED,
                             error_message='Auto-cancelled: stale enrollment timeout',
                             completed_at=timezone.now())

            existing = EnrollmentRequest.objects.filter(
                employee=employee,
                status__in=[EnrollmentRequest.Status.PENDING,
                            EnrollmentRequest.Status.DISPATCHED,
                            EnrollmentRequest.Status.IN_PROGRESS],
            ).first()
            if existing:
                return CommandResult(False, 0,
                                     f'Active enrollment already exists (#{existing.id})')

            enrollment = EnrollmentRequest.objects.create(
                employee=employee,
                fingerprint_id=fingerprint_id,
                device=device,
            )

            # Do NOT set device.mode here — the listener process controls
            # mode switching when it picks up and sends the command.

            result = self.send_command(
                device,
                DeviceCommand.Command.ENROLL,
                employee=employee,
                enrollment_request=enrollment,
                payload={'fingerprint_id': fingerprint_id},
            )

            if result.success:
                enrollment.status = EnrollmentRequest.Status.DISPATCHED
                enrollment.dispatched_at = timezone.now()
                enrollment.save(update_fields=['status', 'dispatched_at'])

                self._log_event(
                    device, DeviceEvent.EventType.ENROLL_PROGRESS,
                    message=f'Enrollment started for {employee.full_name} (fp_id={fingerprint_id})',
                    employee=employee, enrollment_request=enrollment,
                    fingerprint_id=fingerprint_id,
                )
            else:
                enrollment.status = EnrollmentRequest.Status.FAILED
                enrollment.error_message = result.message
                enrollment.completed_at = timezone.now()
                enrollment.save(update_fields=['status', 'error_message', 'completed_at'])

            return CommandResult(
                result.success, result.command_id,
                result.message, enrollment_id=enrollment.id,
            )

    def complete_enrollment(self, enrollment_request: EnrollmentRequest,
                            fingerprint_id: int):
        """Called when Arduino confirms enrollment success."""
        with transaction.atomic():
            enrollment_request.status = EnrollmentRequest.Status.COMPLETED
            enrollment_request.completed_at = timezone.now()
            enrollment_request.error_message = ''
            enrollment_request.save(update_fields=['status', 'completed_at', 'error_message'])

            employee = enrollment_request.employee
            employee.fingerprint_id = fingerprint_id
            employee.save(update_fields=['fingerprint_id'])

            device = enrollment_request.device
            if device:
                device.mode = BiometricDevice.Mode.ATTENDANCE
                device.status = BiometricDevice.Status.ONLINE
                device.save(update_fields=['mode', 'status'])

            self._log_event(
                device, DeviceEvent.EventType.ENROLL_SUCCESS,
                message=f'Enrollment completed for {employee.full_name} (fp_id={fingerprint_id})',
                employee=employee, enrollment_request=enrollment_request,
                fingerprint_id=fingerprint_id,
            )

    def fail_enrollment(self, enrollment_request: EnrollmentRequest, error_msg: str):
        """Called when Arduino reports enrollment failure."""
        with transaction.atomic():
            enrollment_request.status = EnrollmentRequest.Status.FAILED
            enrollment_request.error_message = error_msg
            enrollment_request.completed_at = timezone.now()
            enrollment_request.save(update_fields=['status', 'error_message', 'completed_at'])

            device = enrollment_request.device
            if device:
                device.mode = BiometricDevice.Mode.ATTENDANCE
                device.status = BiometricDevice.Status.ONLINE
                device.save(update_fields=['mode', 'status'])

            self._log_event(
                device, DeviceEvent.EventType.ERROR,
                message=f'Enrollment failed: {error_msg}',
                employee=enrollment_request.employee,
                enrollment_request=enrollment_request,
                error_message=error_msg,
            )

    # ------------------------------------------------------------------
    # Deletion workflow
    # ------------------------------------------------------------------

    def delete_fingerprint(self, device: BiometricDevice, fingerprint_id: int,
                           employee: Optional[Employee] = None) -> CommandResult:
        device.mode = BiometricDevice.Mode.DELETION
        device.save(update_fields=['mode'])

        result = self.send_command(
            device,
            DeviceCommand.Command.DELETE,
            employee=employee,
            payload={'fingerprint_id': fingerprint_id},
        )

        if not result.success:
            device.mode = BiometricDevice.Mode.ATTENDANCE
            device.save(update_fields=['mode'])

        return result

    def confirm_deletion(self, device: BiometricDevice, fingerprint_id: int,
                         employee: Optional[Employee] = None):
        self._log_event(
            device, DeviceEvent.EventType.DELETE_SUCCESS,
            message=f'Fingerprint {fingerprint_id} deleted',
            employee=employee, fingerprint_id=fingerprint_id,
        )
        if employee and employee.fingerprint_id == fingerprint_id:
            employee.fingerprint_id = None
            employee.save(update_fields=['fingerprint_id'])
        device.mode = BiometricDevice.Mode.ATTENDANCE
        device.save(update_fields=['mode'])

    # ------------------------------------------------------------------
    # Device control
    # ------------------------------------------------------------------

    def restart_device(self, device: BiometricDevice) -> CommandResult:
        result = self.send_command(device, DeviceCommand.Command.RESTART)
        if result.success:
            device.status = BiometricDevice.Status.OFFLINE
            device.last_error = ''
            device.save(update_fields=['status', 'last_error'])
        return result

    def request_status(self, device: BiometricDevice) -> CommandResult:
        return self.send_command(device, DeviceCommand.Command.DEVICE_STATUS)

    def return_to_attendance(self, device: BiometricDevice) -> CommandResult:
        result = self.send_command(device, DeviceCommand.Command.ATTENDANCE_MODE)
        if result.success:
            device.mode = BiometricDevice.Mode.ATTENDANCE
            device.save(update_fields=['mode'])
        return result

    # ------------------------------------------------------------------
    # Incoming message processing (called by listener or bridge)
    # ------------------------------------------------------------------

    def process_message(self, device: BiometricDevice, raw: str):
        # Normalize: strip whitespace, handle ATTENDANCE:MATCH:<id> prefix
        raw = raw.strip()
        if not raw:
            return

        # Some Arduino sketches send "ATTENDANCE:MATCH:<id>:<score>"
        # Normalise to "MATCH:<id>:<score>" so the handler lookup works
        if raw.startswith('ATTENDANCE:'):
            inner = raw[len('ATTENDANCE:'):]
            if inner.startswith('MATCH:'):
                raw = inner  # becomes "MATCH:<id>:<score>"
            elif inner.startswith('NO_MATCH'):
                raw = 'NO_MATCH'

        msg = ProtocolParser.parse(raw)
        device.last_seen_at = timezone.now()
        device.save(update_fields=['last_seen_at'])

        print(f"[LISTENER] Received: {msg.raw} → kind={msg.kind} parts={msg.parts}")

        handlers = {
            'ENROLL_PROGRESS': self._handle_enroll_progress,
            'ENROLL_SUCCESS': self._handle_enroll_success,
            'ENROLL_FAIL': self._handle_enroll_fail,
            'DELETED': self._handle_deleted,
            'DELETE_FAIL': self._handle_delete_fail,
            'MATCH': self._handle_match,
            'NO_MATCH': self._handle_no_match,
            'STATUS': self._handle_status,
            'ACK': self._handle_ack,
            'ERROR': self._handle_error,
            'INFO': self._handle_info,
        }

        handler = handlers.get(msg.kind)
        if handler:
            handler(device, msg)
        else:
            print(f"[LISTENER] WARNING: No handler for kind={msg.kind}, logging as RAW")
            self._log_event(device, DeviceEvent.EventType.RAW,
                            message=msg.raw)

    def _handle_enroll_progress(self, device, msg: ProtocolMessage):
        step = msg.parts[1] if len(msg.parts) > 1 else ''
        message = msg.parts[2] if len(msg.parts) > 2 else msg.raw
        enrollment = self._get_active_enrollment(device)
        event = self._log_event(
            device, DeviceEvent.EventType.ENROLL_PROGRESS,
            message=message, enrollment_request=enrollment,
            fingerprint_id=enrollment.fingerprint_id if enrollment else None,
        )
        if enrollment:
            enrollment.status = EnrollmentRequest.Status.IN_PROGRESS
            enrollment.progress_message = message
            enrollment.save(update_fields=['status', 'progress_message'])

    def _handle_enroll_success(self, device, msg: ProtocolMessage):
        fingerprint_id = int(msg.parts[1]) if len(msg.parts) > 1 else None
        enrollment = self._get_active_enrollment(device)
        if enrollment:
            self.complete_enrollment(enrollment, fingerprint_id or enrollment.fingerprint_id)
        else:
            self._log_event(
                device, DeviceEvent.EventType.ENROLL_SUCCESS,
                message=f'Enroll success for fp_id={fingerprint_id}',
                fingerprint_id=fingerprint_id,
            )

    def _handle_enroll_fail(self, device, msg: ProtocolMessage):
        error_msg = msg.parts[1] if len(msg.parts) > 1 else 'Unknown error'
        enrollment = self._get_active_enrollment(device)
        if enrollment:
            self.fail_enrollment(enrollment, error_msg)

    def _handle_deleted(self, device, msg: ProtocolMessage):
        fingerprint_id = int(msg.parts[1]) if len(msg.parts) > 1 else None
        employee = None
        if fingerprint_id:
            employee = Employee.objects.filter(fingerprint_id=fingerprint_id).first()
        self.confirm_deletion(device, fingerprint_id, employee)

    def _handle_delete_fail(self, device, msg: ProtocolMessage):
        error_msg = msg.parts[1] if len(msg.parts) > 1 else 'Delete failed'
        device.mode = BiometricDevice.Mode.ATTENDANCE
        device.save(update_fields=['mode'])
        self._log_event(device, DeviceEvent.EventType.ERROR,
                        message=error_msg, error_message=error_msg)

    def _handle_match(self, device, msg: ProtocolMessage):
        fingerprint_id = int(msg.parts[1]) if len(msg.parts) > 1 else None
        score = int(msg.parts[2]) if len(msg.parts) > 2 else 0

        print(f"\n[MATCH] Raw message: {msg.raw}")
        print(f"[MATCH] Parsed fingerprint_id={fingerprint_id}, score={score}")

        if fingerprint_id is None:
            print("[MATCH] ERROR: Could not parse fingerprint_id from message")
            self._log_event(
                device, DeviceEvent.EventType.ERROR,
                message=f'MATCH parse failed: {msg.raw}',
                error_message='Could not extract fingerprint_id',
            )
            return

        # ── 1. Look up employee ──────────────────────────────────────
        try:
            employee = Employee.objects.select_related('department').get(fingerprint_id=fingerprint_id)
            print(f"[MATCH] Employee found: {employee.full_name} ({employee.organization_id})")
        except Employee.DoesNotExist:
            print(f"[MATCH] ERROR: No employee with fingerprint_id={fingerprint_id}")
            self._log_event(
                device, DeviceEvent.EventType.ATTENDANCE_EVENT,
                message=f'Match for unregistered fingerprint_id={fingerprint_id}',
                fingerprint_id=fingerprint_id,
            )
            self._push_attendance_broadcast(
                device, employee=None, fingerprint_id=fingerprint_id,
                scan_type=None, status='UNKNOWN',
                message=f'Unregistered fingerprint {fingerprint_id}',
            )
            return
        except Exception as exc:
            print(f"[MATCH] ERROR: Database lookup failed: {exc}")
            self._log_event(
                device, DeviceEvent.EventType.ERROR,
                message=f'Employee lookup error: {exc}',
                error_message=str(exc),
                fingerprint_id=fingerprint_id,
            )
            return

        # ── 1b. Duplicate scan prevention ────────────────────────────
        engine = AttendanceEngine()
        allowed, cooldown_msg = engine.is_scan_allowed(employee)
        if not allowed:
            print(f"[MATCH] Scan rejected: {cooldown_msg}")
            self._log_event(
                device, DeviceEvent.EventType.ATTENDANCE_EVENT,
                message=f'Scan rejected for {employee.full_name}: {cooldown_msg}',
                employee=employee, fingerprint_id=fingerprint_id,
            )
            self._push_attendance_broadcast(
                device, employee=employee, fingerprint_id=fingerprint_id,
                scan_type=None, status='COOLDOWN',
                message=cooldown_msg,
            )
            return

        # ── 2. Determine scan type (IN / OUT) ────────────────────────
        today = timezone.localdate()
        last_scan = (
            AttendanceLog.objects
            .filter(employee=employee, timestamp__date=today)
            .order_by('-timestamp')
            .first()
        )
        scan_type = 'OUT' if last_scan and last_scan.scan_type == 'IN' else 'IN'
        print(f"[MATCH] Scan type: {scan_type} (last scan today: {last_scan})")

        # ── 3. Create AttendanceLog ──────────────────────────────────
        try:
            log_entry = AttendanceLog.objects.create(employee=employee, scan_type=scan_type)
            print(f"[MATCH] AttendanceLog created: id={log_entry.id}, timestamp={log_entry.timestamp}")
        except Exception as exc:
            print(f"[MATCH] ERROR: Failed to create AttendanceLog: {exc}")
            self._log_event(
                device, DeviceEvent.EventType.ERROR,
                message=f'AttendanceLog creation failed for {employee.full_name}: {exc}',
                employee=employee, error_message=str(exc),
                fingerprint_id=fingerprint_id,
            )
            return

        # ── 4. Calculate / update AttendanceRecord ────────────────────
        try:
            record = engine.calculate_employee_day(employee, today)
            print(f"[MATCH] AttendanceRecord updated: status={record.status}, "
                  f"worked={record.worked_minutes}min, late={record.minutes_late}min, "
                  f"overtime={record.overtime_minutes}min")
        except Exception as exc:
            print(f"[MATCH] ERROR: AttendanceEngine failed: {exc}")
            self._log_event(
                device, DeviceEvent.EventType.ERROR,
                message=f'AttendanceEngine failed for {employee.full_name}: {exc}',
                employee=employee, error_message=str(exc),
                fingerprint_id=fingerprint_id,
            )
            return

        # ── 5. Log the device event ──────────────────────────────────
        self._log_event(
            device, DeviceEvent.EventType.ATTENDANCE_EVENT,
            message=f'{scan_type} for {employee.full_name} ({employee.organization_id}) '
                    f'score={score} status={record.status}',
            employee=employee, fingerprint_id=fingerprint_id,
            payload={'score': score, 'scan_type': scan_type, 'status': record.status},
        )
        print(f"[MATCH] DeviceEvent logged")

        # ── 6. Broadcast to WebSocket dashboard ──────────────────────
        self._push_attendance_broadcast(
            device, employee=employee, fingerprint_id=fingerprint_id,
            scan_type=scan_type, status=record.status,
            message=f"{'Welcome' if scan_type == 'IN' else 'Goodbye'}, {employee.full_name}",
        )
        print(f"[MATCH] WebSocket broadcast sent")
        print(f"[MATCH] DONE — {employee.full_name} {scan_type} recorded as {record.status}\n")

    def _handle_no_match(self, device, msg: ProtocolMessage):
        print(f"\n[NO_MATCH] Raw message: {msg.raw}")
        self._log_event(device, DeviceEvent.EventType.ATTENDANCE_EVENT,
                        message='No match')

    def _handle_status(self, device, msg: ProtocolMessage):
        mode = msg.parts[1] if len(msg.parts) > 1 else device.mode
        template_count = int(msg.parts[2]) if len(msg.parts) > 2 else device.template_count
        firmware = msg.parts[3] if len(msg.parts) > 3 else device.firmware_version

        device.mode = mode
        device.template_count = template_count
        device.firmware_version = firmware
        device.status = BiometricDevice.Status.ONLINE
        device.save(update_fields=['mode', 'template_count', 'firmware_version', 'status'])

        self._log_event(
            device, DeviceEvent.EventType.DEVICE_STATUS,
            message=f'mode={mode} templates={template_count} fw={firmware}',
            payload={'mode': mode, 'template_count': template_count,
                     'firmware_version': firmware},
        )

        cmd = DeviceCommand.objects.filter(
            device=device, command=DeviceCommand.Command.DEVICE_STATUS,
            status=DeviceCommand.Status.SENT,
        ).order_by('-created_at').first()
        if cmd:
            cmd.status = DeviceCommand.Status.COMPLETED
            cmd.response = msg.raw
            cmd.completed_at = timezone.now()
            cmd.save(update_fields=['status', 'response', 'completed_at'])

    def _handle_ack(self, device, msg: ProtocolMessage):
        cmd_name = msg.parts[1] if len(msg.parts) > 1 else ''
        cmd = DeviceCommand.objects.filter(
            device=device, command=cmd_name,
            status=DeviceCommand.Status.SENT,
        ).order_by('-created_at').first()
        if cmd:
            cmd.status = DeviceCommand.Status.ACKNOWLEDGED
            cmd.response = msg.raw
            cmd.save(update_fields=['status', 'response'])

        self._log_event(device, DeviceEvent.EventType.COMMAND_ACK,
                        message=f'ACK for {cmd_name}')

    def _handle_error(self, device, msg: ProtocolMessage):
        error_msg = msg.parts[1] if len(msg.parts) > 1 else msg.raw
        device.status = BiometricDevice.Status.ERROR
        device.last_error = error_msg
        device.save(update_fields=['status', 'last_error'])

        self._log_event(device, DeviceEvent.EventType.ERROR,
                        message=error_msg, error_message=error_msg)

        cmd = DeviceCommand.objects.filter(
            device=device, status__in=[DeviceCommand.Status.SENT, DeviceCommand.Status.ACKNOWLEDGED],
        ).order_by('-created_at').first()
        if cmd:
            cmd.status = DeviceCommand.Status.FAILED
            cmd.error_message = error_msg
            cmd.completed_at = timezone.now()
            cmd.save(update_fields=['status', 'error_message', 'completed_at'])

    def _handle_info(self, device, msg: ProtocolMessage):
        info_msg = msg.parts[1] if len(msg.parts) > 1 else msg.raw
        self._log_event(device, DeviceEvent.EventType.DEVICE_STATUS,
                        message=info_msg)

    # ------------------------------------------------------------------
    # Serial listener thread
    # ------------------------------------------------------------------

    def start_listener(self, device: BiometricDevice) -> bool:
        if device.device_id in self._listener_threads:
            return True

        if not self.connect_device(device):
            return False

        self._running = True

        def _listen():
            logger.info('Listener started for %s', device.device_id)
            poll_counter = 0
            while self._running:
                conn = self.get_connection(device)
                if not conn:
                    logger.warning('Connection lost for %s, attempting reconnect', device.device_id)
                    self.connect_device(device)
                    time.sleep(5)
                    continue
                raw = conn.readline()
                if raw:
                    try:
                        self.process_message(device, raw)
                    except Exception:
                        logger.exception('Error processing message from %s', device.device_id)
                # Poll for QUEUED commands every ~1 second (20 iterations × 50ms)
                poll_counter += 1
                if poll_counter >= 20:
                    poll_counter = 0
                    try:
                        self.poll_queued_commands(device)
                    except Exception:
                        logger.exception('Error polling queued commands for %s', device.device_id)
                time.sleep(0.05)

        thread = threading.Thread(target=_listen, daemon=True,
                                  name=f'listener-{device.device_id}')
        thread.start()
        self._listener_threads[device.device_id] = thread
        return True

    def stop_listener(self, device: BiometricDevice):
        self._running = False
        self._listener_threads.pop(device.device_id, None)

    def poll_queued_commands(self, device: BiometricDevice):
        """Pick up QUEUED commands from the DB and send them over serial.

        Called by the listener loop so the web server process (which creates
        QUEUED commands) can communicate with the listener process (which has
        the serial connection).
        """
        pending = DeviceCommand.objects.filter(
            device=device,
            status=DeviceCommand.Status.QUEUED,
        ).order_by('created_at')[:5]

        for cmd in pending:
            conn = self.get_connection(device)
            if not conn:
                break

            sent = conn.send(cmd.raw_command)
            if sent:
                cmd.status = DeviceCommand.Status.SENT
                cmd.sent_at = timezone.now()
                cmd.save(update_fields=['status', 'sent_at'])

                device.status = BiometricDevice.Status.BUSY
                device.last_seen_at = timezone.now()
                device.save(update_fields=['status', 'last_seen_at'])

                self._log_event(
                    device, DeviceEvent.EventType.COMMAND_ACK,
                    message=f'Queued command sent: {cmd.command}',
                    command=cmd, employee=cmd.employee,
                )
            else:
                cmd.status = DeviceCommand.Status.FAILED
                cmd.error_message = 'Serial write failed'
                cmd.completed_at = timezone.now()
                cmd.save(update_fields=['status', 'error_message', 'completed_at'])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_channel_layer(self):
        """Return the channel layer, logging any failure instead of swallowing it."""
        try:
            return get_channel_layer()
        except Exception as exc:
            logger.warning('get_channel_layer() failed: %s: %s', type(exc).__name__, exc)
            return None

    def _push_device_status_broadcast(self, device: BiometricDevice):
        """Broadcast device online/offline status to all WebSocket consumers."""
        channel_layer = self._get_channel_layer()
        if channel_layer is None:
            return

        timestamp = timezone.now().isoformat()
        try:
            async_to_sync(channel_layer.group_send)(f'device_{device.pk}', {
                'type': 'device.status_update',
                'status': device.status,
                'mode': device.mode,
                'template_count': device.template_count,
                'last_seen_at': timestamp,
            })
            async_to_sync(channel_layer.group_send)('device_dashboard', {
                'type': 'dashboard.device_status',
                'device_id': str(device.pk),
                'status': device.status,
                'mode': device.mode,
            })
        except Exception as exc:
            logger.warning('WS broadcast failed (device_status): %s: %s', type(exc).__name__, exc)

    def _get_active_enrollment(self, device) -> Optional[EnrollmentRequest]:
        return EnrollmentRequest.objects.filter(
            device=device,
            status__in=[EnrollmentRequest.Status.DISPATCHED,
                        EnrollmentRequest.Status.IN_PROGRESS],
        ).order_by('-requested_at').first()

    def _log_event(self, device, event_type, message='', employee=None,
                   enrollment_request=None, command=None, fingerprint_id=None,
                   payload=None, error_message=''):
        if device is None:
            return None
        event = DeviceEvent.objects.create(
            device=device,
            employee=employee,
            command=command,
            enrollment_request=enrollment_request,
            event_type=event_type,
            message=message,
            fingerprint_id=fingerprint_id,
            payload=payload or {},
            error_message=error_message,
        )
        print(f"  [EVENT] id={event.id} type={event_type} device={device.device_id} "
              f"employee={employee.full_name if employee else '-'} msg={message[:80]}")
        self._push_to_channel(device, event, enrollment_request, employee)
        return event

    def _push_to_channel(self, device, event, enrollment_request=None, employee=None):
        """Push event data to WebSocket channel groups for real-time UI updates."""
        channel_layer = self._get_channel_layer()
        if channel_layer is None:
            return

        employee_name = employee.full_name if employee else (
            enrollment_request.employee.full_name if enrollment_request else None
        )
        enrollment_id = enrollment_request.id if enrollment_request else None
        timestamp = timezone.now().isoformat()

        # Push to per-device group
        device_group = f'device_{device.pk}'
        device_event_data = {
            'type': 'device.event',
            'event_type': event.event_type,
            'message': event.message,
            'employee': employee_name,
            'fingerprint_id': event.fingerprint_id,
            'timestamp': timestamp,
            'error_message': event.error_message,
        }
        try:
            async_to_sync(channel_layer.group_send)(device_group, device_event_data)

            async_to_sync(channel_layer.group_send)(device_group, {
                'type': 'device.status_update',
                'status': device.status,
                'mode': device.mode,
                'template_count': device.template_count,
                'last_seen_at': timestamp,
            })

            # Push enrollment-specific events
            if enrollment_id and event.event_type in (
                DeviceEvent.EventType.ENROLL_PROGRESS,
                DeviceEvent.EventType.ENROLL_SUCCESS,
                DeviceEvent.EventType.ERROR,
            ):
                enrollment_group = f'enrollment_{enrollment_id}'
                enrollment_data = {
                    'type': 'enrollment.progress',
                    'status': enrollment_request.status if enrollment_request else '',
                    'progress_message': enrollment_request.progress_message if enrollment_request else event.message,
                    'fingerprint_id': event.fingerprint_id,
                    'employee_name': employee_name,
                }

                if event.event_type == DeviceEvent.EventType.ENROLL_SUCCESS:
                    enrollment_data['type'] = 'enrollment.complete'
                    enrollment_data['employee_name'] = employee_name
                    enrollment_data['fingerprint_id'] = event.fingerprint_id
                elif event.event_type == DeviceEvent.EventType.ERROR:
                    enrollment_data['type'] = 'enrollment.failed'
                    enrollment_data['error_message'] = event.error_message

                async_to_sync(channel_layer.group_send)(enrollment_group, enrollment_data)

                async_to_sync(channel_layer.group_send)('device_dashboard', {
                    'type': 'dashboard.enrollment_update',
                    'enrollment_id': enrollment_id,
                    'employee_name': employee_name,
                    'status': enrollment_request.status if enrollment_request else '',
                    'progress_message': enrollment_request.progress_message if enrollment_request else event.message,
                })
        except Exception as exc:
            logger.warning('WS broadcast failed (push_to_channel): %s: %s', type(exc).__name__, exc)

    def _push_attendance_broadcast(self, device, employee, fingerprint_id,
                                   scan_type, status, message=''):
        """Broadcast attendance events to the main dashboard WebSocket group.

        This powers the Live Biometric Activity table on the dashboard.
        """
        channel_layer = self._get_channel_layer()
        if channel_layer is None:
            return

        timestamp = timezone.now().isoformat()
        payload = {
            'type': 'dashboard.attendance_event',
            'device_id': device.device_id,
            'device_name': device.name,
            'fingerprint_id': fingerprint_id,
            'employee_id': employee.pk if employee else None,
            'employee_name': employee.full_name if employee else None,
            'organization_id': employee.organization_id if employee else None,
            'department': employee.department.name if employee and employee.department else None,
            'job_title': employee.job_title if employee else None,
            'scan_type': scan_type,
            'status': status,
            'message': message,
            'timestamp': timestamp,
        }

        # Main dashboard group (Live Biometric Activity table)
        try:
            async_to_sync(channel_layer.group_send)('dashboard_live_activity', payload)

            async_to_sync(channel_layer.group_send)(f'device_{device.pk}', payload)

            async_to_sync(channel_layer.group_send)('notifications', {
                'type': 'notification.new',
                'title': f'{"Check-In" if scan_type == "IN" else "Check-Out"}',
                'message': message,
                'level': 'INFO',
                'timestamp': timestamp,
            })
        except Exception as exc:
            logger.warning('WS broadcast failed (attendance): %s: %s', type(exc).__name__, exc)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_hardware_service: Optional[HardwareService] = None


def get_hardware_service() -> HardwareService:
    global _hardware_service
    if _hardware_service is None:
        _hardware_service = HardwareService()
    return _hardware_service
