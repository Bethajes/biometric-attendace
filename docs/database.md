# Database Architecture

## Primary Database
- The Django backend is configured to use `DATABASE_URL`.
- By default, local development uses `sqlite:///backend/db.sqlite3`.
- Production deployments should use a managed PostgreSQL database.

## Django Models
- `attendance` holds employee attendance, leave, holidays, and biometric enrollment state.
- `device_manager` holds biometric devices, device events, and enrollment request lifecycle.
- `payroll` holds salary profiles, payroll calculations, and payslips.
- `organizations` holds tenant and organization metadata.

## Environment Variables
- `DATABASE_URL` is the canonical database connection string.
- `REDIS_URL` is used for Django Channels and real-time device communication.
