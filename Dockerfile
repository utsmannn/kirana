# Frontend build stage
FROM node:22-slim AS frontend
WORKDIR /web
COPY web/package.json web/bun.lock* web/package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install
COPY web/ .
RUN npm run build

# Backend build stage
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage
FROM python:3.11-slim
WORKDIR /app

# Install runtime dependencies and Node.js for MCP
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    poppler-utils \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r kirana && useradd -r -g kirana -d /app -s /sbin/nologin kirana

# Create uploads directory
RUN mkdir -p /app/uploads/knowledge && chown -R kirana:kirana /app/uploads

COPY --from=builder /install /usr/local
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY pyproject.toml .
COPY docker-entrypoint.sh .
COPY --from=frontend /web/build web/build/

RUN chmod +x docker-entrypoint.sh && chown -R kirana:kirana /app
USER kirana
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
