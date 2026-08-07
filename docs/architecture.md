# SmartAttend Architecture

## Overview
SmartAttend is organized as a modular Django backend plus a standalone device client and firmware layer.

### Django
- Located in `backend/`
- Uses `backend/config/` for project configuration
- Uses `backend/config/settings/` for environment-specific settings
- Contains apps: `attendance`, `employees`, `organizations`, `payroll`, `device_manager`

### Device Client
- Located in `device_client/`
- A standalone Python application that manages Arduino serial communication
- Responsible for:
  - reading serial events
  - sending attendance and device events to Django
  - polling Django for enrollment requests
  - retrying failed requests and buffering events offline

### Firmware
- Located in `firmware/biometric_reader/`
- Contains the Arduino sketch for fingerprint hardware

### Attendance Flow
1. Arduino sends fingerprint events over serial.
2. `device_client/bridge.py` reads and parses the events.
3. Device client pushes raw event payloads to Django via REST API.
4. Django records attendance, device events, and enrollment lifecycle state.
