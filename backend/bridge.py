"""
FingerprintBridge — Standalone bridge process that connects Arduino hardware
to the Django backend over serial + HTTP.

In production, this runs as a separate process beside the Arduino. It:
  1. Maintains the serial link to the Arduino.
  2. Reads incoming messages and pushes them to Django via the
     device_manager API endpoint.
  3. Polls Django for pending enrollment requests and dispatches them.
  4. Forwards attendance MATCH events to the attendance API.

Usage:
    python bridge.py                          # defaults
    python bridge.py --port /dev/ttyUSB1      # custom port
    python bridge.py --device-id 1            # target specific Django device
    python bridge.py --api-url http://host/   # custom Django URL
"""

import argparse
import json
import threading
import time
from datetime import datetime

import requests
import serial


class FingerprintBridge:
    def __init__(self, port='/dev/ttyUSB0', baudrate=9600,
                 api_url='http://127.0.0.1:8000/', device_pk=None):
        self.port = port
        self.baudrate = baudrate
        self.api_url = api_url.rstrip('/')
        self.device_pk = device_pk
        self.serial_conn = None
        self.running = True
        self.serial_lock = threading.Lock()
        self.active_enrollment = None
        self.poll_interval = 2

    # ------------------------------------------------------------------
    # Serial connection
    # ------------------------------------------------------------------

    def connect(self):
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)
            print(f"Connected to {self.port}")
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False

    def send_command(self, command):
        if not self.serial_conn:
            print("Not connected")
            return False
        try:
            with self.serial_lock:
                self.serial_conn.write((command + '\n').encode())
            print(f"Sent: {command}")
            return True
        except Exception as e:
            print(f"Error sending command: {e}")
            return False

    def read_line(self):
        try:
            if self.serial_conn.in_waiting > 0:
                line = self.serial_conn.readline().decode('utf-8', errors='replace').strip()
                if line:
                    print(f"Received: {line}")
                    return line
        except Exception as e:
            print(f"Read error: {e}")
        return None

    # ------------------------------------------------------------------
    # Django API helpers
    # ------------------------------------------------------------------

    def _post(self, path, data=None):
        try:
            url = f"{self.api_url}{path}"
            r = requests.post(url, json=data or {}, timeout=5)
            return r.status_code, r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        except Exception as e:
            print(f"POST {path} error: {e}")
            return 0, {}

    def _get(self, path):
        try:
            url = f"{self.api_url}{path}"
            r = requests.get(url, timeout=5)
            return r.status_code, r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        except Exception as e:
            print(f"GET {path} error: {e}")
            return 0, {}

    def push_message(self, raw_message):
        """Push an Arduino message to Django for processing."""
        if not self.device_pk:
            return
        self._post(f'devices/api/devices/{self.device_pk}/message/', {'message': raw_message})

    def send_attendance(self, fingerprint_id):
        """Forward attendance event to Django."""
        status, body = self._post('attendance/', {'fingerprint_id': fingerprint_id})
        if status in (200, 201):
            print(f"  Attendance synced for fp_id={fingerprint_id}: {body.get('message', '')}")
        else:
            print(f"  Attendance sync failed: {status}")

    # ------------------------------------------------------------------
    # Enrollment queue polling
    # ------------------------------------------------------------------

    def poll_enrollment_queue(self):
        if self.active_enrollment is not None:
            return

        status, payload = self._get('api/enrollment/next/')
        if status != 200 or payload.get('status') != 'ok':
            return

        request_data = payload.get('request', {})
        fingerprint_id = request_data.get('fingerprint_id')
        if not fingerprint_id:
            return

        self.active_enrollment = request_data
        self.send_command(f"ENROLL:{fingerprint_id}")
        print(f"  Dispatched enrollment #{request_data.get('id')} for "
              f"{request_data.get('organization_id')} (fp_id={fingerprint_id})")

    def complete_enrollment(self):
        if not self.active_enrollment:
            return
        request_id = self.active_enrollment.get('id')
        status, _ = self._post(f'api/enrollment/{request_id}/complete/')
        print(f"  Enrollment {request_id} completed: {status}")
        self.active_enrollment = None

    def fail_enrollment(self, message):
        if not self.active_enrollment:
            return
        request_id = self.active_enrollment.get('id')
        status, _ = self._post(f'api/enrollment/{request_id}/fail/', {'message': message})
        print(f"  Enrollment {request_id} failed: {status}")
        self.active_enrollment = None

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    def process_message(self, raw):
        """Parse an Arduino message, forward to Django, and handle locally."""
        # Push raw message to Django for canonical event logging
        self.push_message(raw)

        parts = raw.split(':')
        kind = parts[0]

        if kind == 'MATCH' or (kind == 'ATTENDANCE' and len(parts) > 1 and parts[1] == 'MATCH'):
            fp_id = int(parts[2] if kind == 'ATTENDANCE' else parts[1])
            self.send_attendance(fp_id)

        elif kind == 'SUCCESS_ENROLL':
            fp_id = int(parts[1]) if len(parts) > 1 else None
            if self.active_enrollment and self.active_enrollment.get('fingerprint_id') == fp_id:
                self.complete_enrollment()

        elif kind == 'ERROR':
            msg = parts[1] if len(parts) > 1 else raw
            if self.active_enrollment:
                self.fail_enrollment(msg)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def listen_loop(self):
        print("Listening for fingerprint events...")
        print("Bridge is polling Django for enrollment requests.")

        def poller():
            while self.running:
                self.poll_enrollment_queue()
                time.sleep(self.poll_interval)

        poll_thread = threading.Thread(target=poller, daemon=True)
        poll_thread.start()

        while self.running:
            line = self.read_line()
            if line:
                self.process_message(line)
            time.sleep(0.05)

    def run(self):
        if not self.connect():
            return
        try:
            self.listen_loop()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            if self.serial_conn:
                self.serial_conn.close()


def main():
    parser = argparse.ArgumentParser(description='Biometric Attendance Bridge')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Serial port')
    parser.add_argument('--baudrate', type=int, default=9600, help='Baud rate')
    parser.add_argument('--api-url', default='http://127.0.0.1:8000/', help='Django API base URL')
    parser.add_argument('--device-id', type=int, default=None, help='Django BiometricDevice PK')
    args = parser.parse_args()

    bridge = FingerprintBridge(
        port=args.port,
        baudrate=args.baudrate,
        api_url=args.api_url,
        device_pk=args.device_id,
    )
    bridge.run()


if __name__ == '__main__':
    main()
