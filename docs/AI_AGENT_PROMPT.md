# Kirana — AI Agent Guide

Kirana is a production-ready AI chat platform with built-in RAG. It wraps AI providers (OpenAI, Z.AI, any OpenAI-compatible API) behind a **Provider → Channel → Session** architecture and deterministically injects knowledge base chunks into every chat request so the LLM always has the right context.

Use this guide when an AI agent needs to install Kirana, understand its API surface, or build an integration on top of it.

---

## 0. Raw Context Files (fetch these first)

Before you start, fetch the raw source of truth files directly from the repository to build full context:

```
https://raw.githubusercontent.com/utsmannn/kirana/main/README.md
https://raw.githubusercontent.com/utsmannn/kirana/main/docs/API_REFERENCE.md
https://raw.githubusercontent.com/utsmannn/kirana/main/docs/TECH_DOC.md
https://raw.githubusercontent.com/utsmannn/kirana/main/docs/AI_AGENT_PROMPT.md
https://raw.githubusercontent.com/utsmannn/kirana/main/.env.example
https://raw.githubusercontent.com/utsmannn/kirana/main/app/config.py
https://raw.githubusercontent.com/utsmannn/kirana/main/app/api/v1/router.py
https://raw.githubusercontent.com/utsmannn/kirana/main/app/api/deps.py
https://raw.githubusercontent.com/utsmannn/kirana/main/app/schemas/chat.py
https://raw.githubusercontent.com/utsmannn/kirana/main/app/services/chat_service.py
https://raw.githubusercontent.com/utsmannn/kirana/main/app/api/v1/knowledge.py
https://raw.githubusercontent.com/utsmannn/kirana/main/docker-compose.yml
https://raw.githubusercontent.com/utsmannn/kirana/main/Dockerfile
https://raw.githubusercontent.com/utsmannn/kirana/main/Makefile
https://raw.githubusercontent.com/utsmannn/kirana/main/requirements.txt
```

Repo: `https://github.com/utsmannn/kirana`

---

## 1. Installation

### Option A: Docker (Recommended)

Kirana is published as a multi-arch Docker image (amd64 + arm64) on GitHub Container Registry.

**Check the latest version:**

```bash
# List available tags on ghcr.io
curl -s https://api.github.com/repos/utsmannn/kirana/packages/container/kirana/versions | python3 -c "
import json, sys
for v in json.load(sys.stdin):
    print(v['metadata']['container']['tags'])
" 2>/dev/null || echo "Check https://github.com/utsmannn/kirana/pkgs/container/kirana"

# Or check GitHub releases
curl -s https://api.github.com/repos/utsmannn/kirana/releases/latest | python3 -c "
import json, sys
print(json.load(sys.stdin).get('tag_name', 'unknown'))
"
```

**Create a `docker-compose.yml`:**

```yaml
services:
  kirana:
    image: ghcr.io/utsmannn/kirana:latest
    ports:
      - "8000:8000"
    environment:
      - KIRANA_API_KEY=your-secure-api-key-change-me
      - ADMIN_PASSWORD=your-admin-password-change-me
      - SECRET_KEY=$(openssl rand -hex 32)
      - DB_HOST=postgres
      - DB_USER=kirana
      - DB_PASS=kirana
      - DB_NAME=kirana
      - REDIS_HOST=redis
      - OPENAI_API_KEY=sk-your-openai-api-key
      - DEFAULT_MODEL=gpt-4o-mini
      - APP_ENV=production
      - DEBUG=false
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - kirana-uploads:/app/uploads
    restart: unless-stopped

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_USER=kirana
      - POSTGRES_PASSWORD=kirana
      - POSTGRES_DB=kirana
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U kirana -d kirana"]
      interval: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 128mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 5
    restart: unless-stopped

volumes:
  kirana-uploads:
  postgres-data:
  redis-data:
```

**Start it:**

```bash
# Pull the image and start all services
docker compose up -d

# Watch the logs
docker compose logs -f kirana

# Verify everything is healthy
curl http://localhost:8000/health
# → {"app":"kirana","status":"ok","database":"ok","redis":"ok"}
```

**Pin a specific version in production:**

```yaml
image: ghcr.io/utsmannn/kirana:v1.0.0   # instead of :latest
```

### Option B: Local Development (for customizing the code)

Infrastructure runs in Docker, backend + frontend run locally with hot-reload.

```bash
# 1. Clone the repo
git clone https://github.com/utsmannn/kirana.git
cd kirana

# 2. Start infrastructure (PostgreSQL/pgvector + Redis)
make infra

# 3. Install dependencies
make install-python
make install-web

# 4. Run database migrations
make migrate

# 5. Start backend + frontend (logs to console, Ctrl+C stops both)
make dev

# 6. Verify
curl http://localhost:8000/health
# → {"app":"kirana","status":"ok","database":"ok","redis":"ok"}

# Open the admin dashboard
open http://localhost:8000/panel
```

Backend runs on port 8000, frontend dev server on port 5173.

---

## 2. Configuration

### Required Environment Variables

| Variable | Purpose |
|----------|---------|
| `KIRANA_API_KEY` | Server API key used to authenticate all admin/API calls |
| `ADMIN_PASSWORD` | Admin panel login password |
| `SECRET_KEY` | Used for admin token generation (SHA256 daily rotation) |
| `OPENAI_API_KEY` | Default LLM API key (fallback when no provider configured) |

### Recommended overrides for production

| Variable | Default | Recommended |
|----------|---------|-------------|
| `DEFAULT_MODEL` | `gpt-4o-mini` | Your preferred model |
| `OPENAI_BASE_URL` | OpenAI default | Your provider's base URL if using alternatives |
| `CORS_ORIGINS` | Allow all | Your domain(s) |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | 60 | Adjust for expected load |
| `RAG_ENABLED` | `true` | `true` to keep RAG on |

See `.env.example` in the repository for the full list.

---

## 3. Post-Installation — Admin Setup

Before you can chat, you need at least one provider and one channel. Follow this order:

### Step 1: Login to get an admin token

```bash
curl -X POST http://localhost:8000/v1/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password": "your-admin-password"}'
# → {"token": "abc123..."}
```

Save the token — use it for all subsequent API calls in this setup.

### Step 2: Check if a provider already exists

```bash
curl http://localhost:8000/v1/providers/ \
  -H "Authorization: Bearer <admin-token>"
```

If the response shows an active provider, skip to Step 4.

### Step 3: Add and activate an AI provider

```bash
# Add a provider
curl -X POST http://localhost:8000/v1/providers/ \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OpenAI",
    "model": "gpt-4o-mini",
    "api_key": "sk-your-key-here",
    "base_url": null
  }'

# Activate it (use the returned provider ID)
curl -X POST http://localhost:8000/v1/providers/<provider-id>/activate \
  -H "Authorization: Bearer <admin-token>"
```

### Step 4: Check existing channels

```bash
curl http://localhost:8000/v1/channels/ \
  -H "Authorization: Bearer <admin-token>"
```

Note the `default_channel.id`. If none exists, create one:

### Step 5: Create a channel (if needed)

```bash
curl -X POST http://localhost:8000/v1/channels/ \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Default",
    "provider_id": "<provider-id>",
    "personality_name": "Helpful Assistant"
  }'

# Set it as default
curl -X POST http://localhost:8000/v1/channels/<channel-id>/set-default \
  -H "Authorization: Bearer <admin-token>"
```

### Step 6: Test chat

```bash
curl -X POST http://localhost:8000/v1/chat/send \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello!"}],
    "channel_id": "<channel-id>",
    "stream": false
  }'
```

---

## 4. API Quick Reference

### Base URL

```
http://<host>:8000/v1
```

### Auth

All endpoints use `Authorization: Bearer <token>`. Four auth methods:

| Method | Token source | Scope |
|--------|-------------|-------|
| Server API key | `KIRANA_API_KEY` from `.env` | All endpoints |
| Admin token | `POST /v1/admin/login` | All endpoints (rotates daily) |
| Client API key | `POST /v1/clients/` (one-time display) | Chat, knowledge, `/v1/clients/me` |
| Embed token | Channel config | Chat only (per-channel) |

### Trailine Slashes

- Collection endpoints **require** a trailing slash: `/v1/providers/`, `/v1/knowledge/`, `/v1/sessions/`, `/v1/clients/`
- Singular endpoints must **not** have one: `/v1/clients/me`, `/v1/providers/{id}`, `/v1/channels/{id}`
- Wrong slash → `307` redirect.

### Key Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check (no auth) |
| `POST` | `/v1/admin/login` | Get admin token |
| `POST` | `/v1/chat/send` | **Primary chat endpoint** — send messages, get responses |
| `WS` | `/v1/chat/ws` | WebSocket chat |
| `POST` | `/v1/knowledge/upload` | Upload documents for RAG |
| `GET` | `/v1/knowledge/` | List/search knowledge items |
| `GET` | `/v1/channels/` | List channels |
| `POST` | `/v1/sessions/` | Create a chat session |
| `GET` | `/v1/sessions/{id}/messages` | Get conversation history |
| `GET` | `/v1/providers/` | List AI providers |

Full API contract: [`docs/API_REFERENCE.md`](API_REFERENCE.md)

---

## 5. Chat Request Format

`POST /v1/chat/send` accepts OpenAI-compatible messages plus Kirana extensions:

```json
{
  "messages": [{"role": "user", "content": "Hello!"}],
  "channel_id": "<uuid>",
  "session_id": "<uuid>",
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 4096
}
```

| Field | Type | Notes |
|-------|------|-------|
| `messages` | array | **Required.** OpenAI `[{role, content}]` format |
| `channel_id` | UUID | **Always pass this.** Tells Kirana which provider/personality/tools to use |
| `session_id` | UUID | Optional. For persistent conversation history |
| `stream` | bool | Enable SSE streaming |
| `visitor_id` | string | Embed widget visitor tracking |

**SET `channel_id` for every chat request.** Without it Kirana doesn't know which provider to use.

---

## 6. RAG — Knowledge Upload & Retrieval

### Upload a document

```bash
curl -X POST http://localhost:8000/v1/knowledge/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@document.pdf" \
  -F "title=Company Handbook"
```

Supported formats: PDF, DOCX, TXT, CSV, MD, JSON, XLSX, PPTX, PNG, JPG.

Upload is **fire-and-forget** — returns `201` immediately with `"processing_status": "processing"`. Heavy work runs in the background:

1. **LiteParse** parses the document (OCR for PDFs)
2. Optional **AI summarization** via configured LLM
3. **Chunking** — tiktoken `cl100k_base`, 800-token chunks, 120-token overlap
4. **Embedding** — FastEmbed `paraphrase-multilingual-MiniLM-L12-v2`, 384-dim vectors
5. **Storage** — pgvector with HNSW cosine distance index

### Poll for completion

```bash
# Poll until status is "ready" or "failed"
curl http://localhost:8000/v1/knowledge/<id> \
  -H "Authorization: Bearer <token>" | python3 -c "import sys,json; print(json.load(sys.stdin)['processing_status'])"
```

| Status | Meaning |
|--------|---------|
| `processing` | Background worker is still parsing/indexing — poll again in 2-3s |
| `ready` | Document fully indexed and queryable via RAG |
| `failed` | Check `metadata.processing_error` for the failure reason |

### How retrieval works at chat time

1. User sends a chat message
2. Kirana embeds the latest user message
3. Searches `knowledge_chunks` via pgvector cosine similarity
4. Injects top-10 most relevant chunks into the system prompt
5. LLM responds with `[S1]`, `[S2]` citations

**RAG is deterministic** — it runs automatically before every chat request. The LLM doesn't decide whether to search.

---

## 7. Provider Error Handling

When the AI provider fails, Kirana returns structured errors. Do **not** silently ignore them.

| Error code | HTTP | Meaning | What to do |
|-----------|------|---------|------------|
| `provider_config_error` | 502 | Channel has inactive/missing provider, or no API key | Fix provider config in admin panel |
| `provider_error` (AuthenticationError) | 502 | Provider rejected API key | Update provider credentials |
| `provider_error` (RateLimitError) | 429 | Upstream rate limit | Retry with backoff |
| `provider_error` (APITimeoutError / APIConnectionError) | 504 | Provider unreachable | Check base URL/network, retry with backoff |
| `provider_error` (generic) | 502 | Provider returned an error | Check provider config, try again |

**Streaming chat** sends these as SSE payloads before `[DONE]`:
```text
data: {"error":{"code":"provider_error","message":"...","status_code":502}}

data: [DONE]
```

---

## 8. Canonical Integration Flow

```
1. POST /v1/clients/              → register, get API key
2. GET  /v1/channels/             → pick a channel_id
3. POST /v1/sessions/             → create session with channel_id
4. POST /v1/chat/send             → chat with channel_id + session_id
5. POST /v1/knowledge/upload      → add documents to RAG
6. POST /v1/chat/send             → ask grounded questions
7. GET  /v1/sessions/{id}/messages → retrieve conversation history
```

---

## 9. Repository Files (for code-level understanding)

All files are under `https://github.com/utsmannn/kirana`. Fetch them raw via `https://raw.githubusercontent.com/utsmannn/kirana/main/<path>`.

| # | File | Raw URL | Purpose |
|---|------|---------|---------|
| 1 | `README.md` | `raw.githubusercontent.com/utsmannn/kirana/main/README.md` | Project overview, quick start, configuration, RAG behavior, deployment. |
| 2 | `docs/API_REFERENCE.md` | `raw.githubusercontent.com/utsmannn/kirana/main/docs/API_REFERENCE.md` | Full API contract: endpoints, auth, schemas, error codes, canonical flows. |
| 3 | `docs/TECH_DOC.md` | `raw.githubusercontent.com/utsmannn/kirana/main/docs/TECH_DOC.md` | Internals: chat service, RAG pipeline, DB schema, streaming, deployment. |
| 4 | `docs/AI_AGENT_PROMPT.md` | `raw.githubusercontent.com/utsmannn/kirana/main/docs/AI_AGENT_PROMPT.md` | This file — AI agent setup & integration guide. |
| 5 | `.env.example` | `raw.githubusercontent.com/utsmannn/kirana/main/.env.example` | All environment variables with defaults. |
| 6 | `app/config.py` | `raw.githubusercontent.com/utsmannn/kirana/main/app/config.py` | Pydantic Settings model — canonical source of config defaults. |
| 7 | `app/api/v1/router.py` | `raw.githubusercontent.com/utsmannn/kirana/main/app/api/v1/router.py` | All registered API routes and prefixes. |
| 8 | `app/api/deps.py` | `raw.githubusercontent.com/utsmannn/kirana/main/app/api/deps.py` | Authentication dependency functions. |
| 9 | `app/schemas/chat.py` | `raw.githubusercontent.com/utsmannn/kirana/main/app/schemas/chat.py` | Chat request/response Pydantic models. |
| 10 | `app/services/chat_service.py` | `raw.githubusercontent.com/utsmannn/kirana/main/app/services/chat_service.py` | Chat orchestration: provider resolution, prompt building, RAG injection, streaming, error mapping. |
| 11 | `app/api/v1/knowledge.py` | `raw.githubusercontent.com/utsmannn/kirana/main/app/api/v1/knowledge.py` | Knowledge CRUD, file upload, async processing, RAG indexing. |
| 12 | `app/core/security.py` | `raw.githubusercontent.com/utsmannn/kirana/main/app/core/security.py` | API key generation and SHA256 hashing. |
| 13 | `docker-compose.yml` | `raw.githubusercontent.com/utsmannn/kirana/main/docker-compose.yml` | Infrastructure services (PostgreSQL/pgvector + Redis). |
| 14 | `Dockerfile` | `raw.githubusercontent.com/utsmannn/kirana/main/Dockerfile` | Multi-stage production image build. |
| 15 | `Makefile` | `raw.githubusercontent.com/utsmannn/kirana/main/Makefile` | Local dev workflow targets. |
| 16 | `requirements.txt` | `raw.githubusercontent.com/utsmannn/kirana/main/requirements.txt` | Python dependencies. |

---

## 10. Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI (Python 3.11) |
| Frontend | SvelteKit (Node 22) |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| LLM SDK | OpenAI SDK (AsyncOpenAI) |
| Embeddings | FastEmbed (paraphrase-multilingual-MiniLM-L12-v2, 384d) |
| Chunking | tiktoken (cl100k_base) |
| Parsing | LiteParse (OCR-enabled) |
| Container | Docker multi-arch (amd64 + arm64), ghcr.io |
| CI/CD | GitHub Actions — build + push on tag/release |
