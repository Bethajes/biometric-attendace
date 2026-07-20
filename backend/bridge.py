import serial
import time
import threading
import requests
from datetime import datetime

class FingerprintBridge:
    def __init__(self, port='/dev/ttyUSB0', baudrate=9600, api_url='http://127.0.0.1:8000/'):
        self.port = port
        self.baudrate = baudrate
        self.api_url = api_url
        self.serial = None
        self.running = True
        self.serial_lock = threading.Lock()
        self.active_enrollment = None
        self.poll_interval = 2
        
    def connect(self):
        """Establish serial connection to Arduino"""
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Wait for Arduino to reset
            print(f"Connected to {self.port}")
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
            
    def send_command(self, command):
        """Send a command to the Arduino"""
        if not self.serial:
            print("Not connected")
            return False
            
        try:
            with self.serial_lock:
                self.serial.write((command + '\n').encode())
            print(f"Sent: {command}")
            return True
        except Exception as e:
            print(f"Error sending command: {e}")
            return False
            
    def read_response(self):
        """Read and parse Arduino responses"""
        try:
            if self.serial.in_waiting > 0:
                line = self.serial.readline().decode().strip()
                if line:
                    print(f"Received: {line}")
                    return self.parse_response(line)
        except Exception as e:
            print(f"Error reading: {e}")
        return None
        
    def parse_response(self, message):
        """Parse different types of messages from Arduino"""
        if message.startswith('MATCH:') or message.startswith('ATTENDANCE:MATCH:'):
            parts = message.split(':')
            if len(parts) >= 2:
                user_index = 1 if message.startswith('MATCH:') else 2
                confidence_index = 2 if message.startswith('MATCH:') else 3
                return {
                    'type': 'attendance_match',
                    'user_id': int(parts[user_index]),
                    'confidence': int(parts[confidence_index]) if len(parts) > confidence_index else 0,
                    'timestamp': datetime.now().isoformat()
                }
                
        elif message.startswith('ATTENDANCE:NO_MATCH'):
            return {'type': 'attendance_no_match'}
            
        elif message.startswith('SUCCESS_ENROLL:'):
            user_id = int(message.split(':')[1])
            return {
                'type': 'enroll_success',
                'user_id': user_id
            }
            
        elif message.startswith('ERROR:'):
            return {
                'type': 'error',
                'message': message
            }
            
        elif message.startswith('ACK:'):
            return {
                'type': 'acknowledgement',
                'message': message
            }
            
        elif message.startswith('INFO:'):
            return {
                'type': 'info',
                'message': message
            }
            
        return {'type': 'unknown', 'message': message}
        
    def process_response(self, parsed):
        """Handle different types of responses"""
        if parsed['type'] == 'attendance_match':
            self.send_attendance_to_django(parsed['user_id'])
            
        elif parsed['type'] == 'enroll_success':
            print(f"✅ Employee {parsed['user_id']} enrolled successfully!")
            if self.active_enrollment and self.active_enrollment.get('fingerprint_id') == parsed['user_id']:
                self.complete_enrollment()
            
        elif parsed['type'] == 'error':
            print(f"❌ Error: {parsed['message']}")
            if self.active_enrollment:
                self.fail_enrollment(parsed['message'])

    def send_attendance_to_django(self, fingerprint_id):
        try:
            response = requests.post(f"{self.api_url}attendance/", json={'fingerprint_id': fingerprint_id}, timeout=5)
            if response.status_code in (200, 201):
                print(f"✅ Attendance synced for fingerprint {fingerprint_id}")
            else:
                print(f"⚠️ Attendance sync failed: {response.status_code} {response.text}")
        except Exception as e:
            print(f"⚠️ Django attendance error: {e}")
            
    def send_to_django(self, endpoint, data):
        """Send data to Django API"""
        try:
            url = f"{self.api_url}{endpoint}/"
            response = requests.post(url, json=data, timeout=5)
            if response.status_code == 200:
                print(f"✅ Synced to Django: {endpoint}")
            else:
                print(f"⚠️ Django sync failed: {response.status_code}")
        except Exception as e:
            print(f"⚠️ Django connection error: {e}")
            
    def enroll_employee(self, employee_id):
        """Public method to enroll an employee"""
        if employee_id < 1 or employee_id > 126:
            print("❌ Employee ID must be between 1 and 126")
            return False
            
        print(f"📝 Starting enrollment for ID {employee_id}...")
        print("📌 Please follow the fingerprint scanner prompts")
        return self.send_command(f"ENROLL:{employee_id}")

    def poll_enrollment_queue(self):
        try:
            response = requests.get(f"{self.api_url}enrollment/next/", timeout=5)
            if response.status_code != 200:
                return

            payload = response.json()
            if payload.get('status') != 'ok':
                return

            request_data = payload.get('request', {})
            fingerprint_id = request_data.get('fingerprint_id')
            if not fingerprint_id:
                return

            self.active_enrollment = request_data
            self.send_command(f"ENROLL:{fingerprint_id}")
            print(f"🧭 Dispatched enrollment request #{request_data.get('id')} for {request_data.get('organization_id')}")
        except Exception as e:
            print(f"⚠️ Enrollment poll error: {e}")

    def complete_enrollment(self):
        try:
            request_id = self.active_enrollment.get('id')
            response = requests.post(f"{self.api_url}enrollment/{request_id}/complete/", timeout=5)
            if response.status_code in (200, 201):
                print(f"✅ Enrollment request {request_id} completed")
            else:
                print(f"⚠️ Enrollment completion failed: {response.status_code} {response.text}")
        except Exception as e:
            print(f"⚠️ Enrollment completion error: {e}")
        finally:
            self.active_enrollment = None

    def fail_enrollment(self, message):
        try:
            request_id = self.active_enrollment.get('id')
            response = requests.post(
                f"{self.api_url}enrollment/{request_id}/fail/",
                json={'message': message},
                timeout=5,
            )
            if response.status_code in (200, 201):
                print(f"⚠️ Enrollment request {request_id} marked failed")
            else:
                print(f"⚠️ Enrollment failure sync failed: {response.status_code} {response.text}")
        except Exception as e:
            print(f"⚠️ Enrollment failure error: {e}")
        finally:
            self.active_enrollment = None
        
    def switch_to_attendance(self):
        """Switch back to attendance mode"""
        return self.send_command("ATTENDANCE")
        
    def delete_fingerprint(self, employee_id):
        """Delete a fingerprint template"""
        return self.send_command(f"DELETE:{employee_id}")
        
    def delete_all(self):
        """Delete all fingerprints"""
        return self.send_command("DELETE_ALL")
        
    def get_template_count(self):
        """Get number of stored templates"""
        return self.send_command("GET_COUNT")
        
    def listen_loop(self):
        """Main listening loop"""
        print("🔍 Listening for fingerprint events...")
        print("Bridge is polling Django for enrollment requests.")

        def poller():
            while self.running:
                if self.active_enrollment is None:
                    self.poll_enrollment_queue()
                time.sleep(self.poll_interval)

        poll_thread = threading.Thread(target=poller, daemon=True)
        poll_thread.start()
        
        # Main read loop
        while self.running:
            response = self.read_response()
            if response:
                self.process_response(response)
            time.sleep(0.1)
            
    def run(self):
        """Main entry point"""
        if not self.connect():
            return
            
        try:
            self.listen_loop()
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
        finally:
            if self.serial:
                self.serial.close()

if __name__ == "__main__":
    # Configuration
    PORT = '/dev/ttyUSB0'  # Change to your Arduino port
    API_URL = 'http://127.0.0.1:8000/'  # Your Django API endpoint
    
    bridge = FingerprintBridge(port=PORT, api_url=API_URL)
    bridge.run()