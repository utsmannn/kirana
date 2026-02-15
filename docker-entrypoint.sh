#!/bin/bash
set -e

echo "[Entrypoint] Starting Kirana..."

# Run database migrations
echo "[Entrypoint] Running database migrations..."
alembic upgrade head

# Start the application
echo "[Entrypoint] Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
