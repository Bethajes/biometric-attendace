import threading
import time
import serial


class SerialReader:
    def __init__(self, port: str, baudrate: int, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn = None
        self.lock = threading.Lock()

    def connect(self) -> bool:
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(2)
            return True
        except Exception:
            return False

    def write(self, command: str) -> bool:
        if not self.serial_conn or not self.serial_conn.is_open:
            return False
        try:
            with self.lock:
                self.serial_conn.write((command + '\n').encode('utf-8'))
            return True
        except Exception:
            return False

    def read_line(self):
        if not self.serial_conn or not self.serial_conn.is_open:
            return None
        try:
            if self.serial_conn.in_waiting > 0:
                return self.serial_conn.readline().decode('utf-8', errors='replace').strip()
        except Exception:
            return None
        return None

    def close(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
