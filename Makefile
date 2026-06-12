SHELL := /bin/bash
export PYTHONPATH := $(shell pwd)

PYTHON ?= python3.11
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 5173
DATABASE_URL ?= postgresql+asyncpg://kirana:kirana@localhost:5432/kirana
REDIS_URL ?= redis://localhost:6379/0
UPLOAD_DIR ?= ./uploads

.PHONY: dev infra backend frontend migrate seed install-python install-web

infra:
	docker compose up -d db redis

install-python:
	@if [ ! -d .venv ]; then $(PYTHON) -m venv .venv; fi
	@if [ "$$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.11" ]; then echo ".venv must use Python 3.11; remove .venv and rerun with PYTHON=python3.11"; exit 1; fi
	.venv/bin/python -m pip install -r requirements.txt

install-web:
	cd web && npm install

migrate: install-python
	DATABASE_URL='$(DATABASE_URL)' REDIS_URL='$(REDIS_URL)' UPLOAD_DIR='$(UPLOAD_DIR)' .venv/bin/alembic upgrade head

seed: install-python
	DATABASE_URL='$(DATABASE_URL)' REDIS_URL='$(REDIS_URL)' UPLOAD_DIR='$(UPLOAD_DIR)' .venv/bin/python scripts/seed_personalities.py

backend: install-python migrate seed
	DATABASE_URL='$(DATABASE_URL)' REDIS_URL='$(REDIS_URL)' UPLOAD_DIR='$(UPLOAD_DIR)' \
		.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $(BACKEND_PORT) --reload

frontend: install-web
	cd web && BACKEND_PORT='$(BACKEND_PORT)' npm run dev -- --host 0.0.0.0 --port $(FRONTEND_PORT)

dev: infra install-python install-web migrate seed
	@echo "Backend:  http://localhost:$(BACKEND_PORT)"
	@echo "Frontend: http://localhost:$(FRONTEND_PORT)"
	@echo "Press Ctrl+C to stop backend and frontend"
	@set -m; \
	trap 'kill $$backend_pid $$frontend_pid 2>/dev/null || true; wait 2>/dev/null || true' INT TERM EXIT; \
	DATABASE_URL='$(DATABASE_URL)' REDIS_URL='$(REDIS_URL)' UPLOAD_DIR='$(UPLOAD_DIR)' \
		.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $(BACKEND_PORT) --reload & \
	backend_pid=$$!; \
	cd web && BACKEND_PORT='$(BACKEND_PORT)' npm run dev -- --host 0.0.0.0 --port $(FRONTEND_PORT) & \
	frontend_pid=$$!; \
	wait $$backend_pid $$frontend_pid
