"""Standalone device bridge for Arduino fingerprint event sync."""

import argparse
import threading
import time

from device_client.api_client import DjangoApiClient
from device_client.config import API_URL, BAUDRATE, DEVICE_ID, SERIAL_PORT
from device_client.serial_reader import SerialReader


class FingerprintBridge:
    def __init__(self, port=SERIAL_PORT, baudrate=BAUDRATE, api_url=API_URL, device_pk=DEVICE_ID):
        self.serial_reader = SerialReader(port, baudrate)
        self.api = DjangoApiClient(api_url)
        self.device_pk = device_pk
        self.running = True
        self.active_enrollment = None
        self.poll_interval = 2

    def connect(self):
        return self.serial_reader.connect()

    def send_command(self, command):
        return self.serial_reader.write(command)

    def read_line(self):
        return self.serial_reader.read_line()

    def push_message(self, raw_message):
        if not self.device_pk:
            return
        self.api.post(f'devices/api/devices/{self.device_pk}/message/', {'message': raw_message})

    def send_attendance(self, fingerprint_id):
        status, body = self.api.post('api/attendance/', {'fingerprint_id': fingerprint_id})
        if status in (200, 201):
            print(f"Attendance synced for fp_id={fingerprint_id}: {body.get('message', '')}")
        else:
            print(f"Attendance sync failed: {status}")

    def poll_enrollment_queue(self):
        if self.active_enrollment is not None:
            return
        status, payload = self.api.get('api/enrollment/next/')
        if status != 200 or payload.get('status') != 'ok':
            return
        request_data = payload.get('request', {})
        fingerprint_id = request_data.get('fingerprint_id')
        if not fingerprint_id:
            return
        self.active_enrollment = request_data
        self.send_command(f"ENROLL:{fingerprint_id}")
        print(f"Dispatched enrollment #{request_data.get('id')} for organization {request_data.get('organization_id')} (fp_id={fingerprint_id})")

    def complete_enrollment(self):
        if not self.active_enrollment:
            return
        request_id = self.active_enrollment.get('id')
        self.api.post(f'api/enrollment/{request_id}/complete/')
        self.active_enrollment = None

    def fail_enrollment(self, message):
        if not self.active_enrollment:
            return
        request_id = self.active_enrollment.get('id')
        self.api.post(f'api/enrollment/{request_id}/fail/', {'message': message})
        self.active_enrollment = None

    def process_message(self, raw):
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

    def listen_loop(self):
        print('Listening for fingerprint events...')
        print('Bridge is polling Django for enrollment requests.')

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
            print('Unable to connect to hardware serial port.')
            return
        try:
            self.listen_loop()
        except KeyboardInterrupt:
            print('\nShutting down...')
        finally:
            self.serial_reader.close()


def main():
    parser = argparse.ArgumentParser(description='Biometric Attendance Bridge')
    parser.add_argument('--port', default=SERIAL_PORT, help='Serial port')
    parser.add_argument('--baudrate', type=int, default=BAUDRATE, help='Baud rate')
    parser.add_argument('--api-url', default=API_URL, help='Django API base URL')
    parser.add_argument('--device-id', default=DEVICE_ID, help='Django BiometricDevice PK')
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
