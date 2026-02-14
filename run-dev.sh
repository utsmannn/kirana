#!/bin/bash

# Exit on error
set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}=== Kirana Development Environment ===${NC}"

# --- Helper Functions ---

find_free_port() {
    local port=$1
    while nc -z 127.0.0.1 $port >/dev/null 2>&1; do
        ((port++))
    done
    echo $port
}

check_port_active() {
    nc -z 127.0.0.1 $1 >/dev/null 2>&1
}

# --- Initialization ---

if [ ! -f .env ]; then
    echo -e "${BLUE}Creating .env from .env.example...${NC}"
    cp .env.example .env
fi

# Load variables
set -a
source .env
set +a

# Defaults
DB_PORT=${DB_PORT:-5432}
REDIS_PORT=${REDIS_PORT:-6379}

# --- Logic: Check Connectivity vs Port Availability ---

INFRA_READY=true

# Check Postgres
if ! check_port_active $DB_PORT; then
    INFRA_READY=false
    echo -e "${RED}❌ PostgreSQL is not reachable on port $DB_PORT.${NC}"
else
    echo -e "✅ PostgreSQL detected on port $DB_PORT."
fi

# Check Redis
if ! check_port_active $REDIS_PORT; then
    INFRA_READY=false
    echo -e "${RED}❌ Redis is not reachable on port $REDIS_PORT.${NC}"
else
    echo -e "✅ Redis detected on port $REDIS_PORT."
fi

# --- Main Decision ---

if [ "$INFRA_READY" = false ]; then
    echo -e "\n${YELLOW}Infrastructure is not running.${NC}"
    echo -e "Please start the infrastructure:\n"
    echo -e "${GREEN}docker compose up -d db redis${NC}"
    echo -e "\nThen run this script again."
    exit 1
fi

# --- App Start ---

# Python Virtual Environment
if [ ! -d ".venv" ]; then
    echo -e "${BLUE}Creating Python virtual environment...${NC}"
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt > /dev/null

# Fix Path for Imports
export PYTHONPATH=$PWD

# Linting / Checks
echo -e "${BLUE}Running Code Checks (Ruff)...${NC}"
# We allow this to fail (return false) so development isn't blocked by style issues
# Remove '|| true' if you want to strictly block on lint errors
ruff check . || echo -e "${YELLOW}⚠️  Linter found issues. Proceeding anyway...${NC}"

# Migrations
echo -e "${BLUE}Running database migrations...${NC}"

# Check if versions directory is empty (no .py files)
if [ -z "$(ls -A alembic/versions/*.py 2>/dev/null)" ]; then
    echo -e "${YELLOW}No existing migrations found. Generating initial migration...${NC}"
    alembic revision --autogenerate -m "Initial migration"
fi

alembic upgrade head

# Seed
echo -e "${BLUE}Seeding initial data...${NC}"
python scripts/seed_personalities.py

# Find Free Port for API (Starting from 8001 since 8000 is often taken by SSH)
BASE_PORT=8001
API_PORT=$(find_free_port $BASE_PORT)

if [ "$API_PORT" != "$BASE_PORT" ]; then
    echo -e "${YELLOW}Port $BASE_PORT is busy, assigned to next available port: $API_PORT${NC}"
fi

# Start
echo -e "${GREEN}Starting FastAPI Server on port $API_PORT...${NC}"
echo -e "${GREEN}Docs available at: http://localhost:$API_PORT/docs${NC}"

uvicorn app.main:app --host 0.0.0.0 --port $API_PORT --reload