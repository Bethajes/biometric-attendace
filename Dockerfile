FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory to /app/backend
WORKDIR /app/backend

# Copy requirements and install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy project files
COPY backend/ /app/backend/
COPY device_client/ /app/device_client/

ENV DJANGO_SETTINGS_MODULE=config.settings.production

# Collect static assets (running python manage.py directly since WORKDIR is /app/backend)
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Use Railway's $PORT environment variable dynamically (falls back to 8000)
CMD ["sh", "-c", "daphne -b 0.0.0.0 -p ${PORT:-8000} config.asgi:application"]