# Deployment

## Docker

1. Build the container:
   ```bash
   docker build -t smartattend-backend .
   ```

2. Start the app with Docker Compose:
   ```bash
   docker-compose up --build
   ```

3. The Django web app is available at `http://localhost:8000`.

## Render

- `render.yaml` is configured to deploy the backend as a Docker web service.
- Set environment variables in Render for `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, and host-specific values.
- Use `DJANGO_SETTINGS_MODULE=config.settings.production` for production deploys.

## Supabase

- Supabase can be used for storage, file hosting, and downstream analytics.
- The application reads `SUPABASE_DATABASE_URL`, `SUPABASE_STORAGE_BUCKET`, and `SUPABASE_API_KEY` from environment variables.
