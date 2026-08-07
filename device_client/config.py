import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

API_URL = os.getenv('DEVICE_API_URL', 'http://127.0.0.1:8000/')
DEVICE_ID = os.getenv('DEVICE_ID')
SERIAL_PORT = os.getenv('DEVICE_SERIAL_PORT', '/dev/ttyUSB0')
BAUDRATE = int(os.getenv('DEVICE_BAUDRATE', '9600'))

FACE_RECOGNITION_ENABLED = os.getenv('FACE_RECOGNITION_ENABLED', 'False').lower() in ('1', 'true', 'yes')
FINGERPRINT_ENABLED = os.getenv('FINGERPRINT_ENABLED', 'True').lower() in ('1', 'true', 'yes')
