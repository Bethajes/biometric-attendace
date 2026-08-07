# SmartAttend Enterprise Workforce Management System

This repository contains the SmartAttend Django backend, a standalone device client for Arduino fingerprint integration, and firmware for biometric hardware.

- `backend/` — Django application and project code
- `device_client/` — standalone Python bridge for Arduino communication
- `firmware/` — Arduino sketch for biometric reader
- `docs/` — architecture, deployment, and database documentation

## Getting Started
1. Copy `.env.example` to `.env`
2. Install dependencies with `pip install -r requirements.txt`
3. Run the Django app from `backend/`
