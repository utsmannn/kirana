#!/bin/bash
set -e

echo "[Entrypoint] Starting Kirana..."

# Run database migrations
echo "[Entrypoint] Running database migrations..."
alembic upgrade head

# Realtime session events and Telegram long-polling are process-local, so Kirana
# must run as one application worker until the event bus moves to Redis/pubsub.
echo "[Entrypoint] Starting uvicorn (single worker)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
