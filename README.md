# Kirana — AI Chat Platform with RAG

**Production-ready AI chat API with built-in RAG (Retrieval-Augmented Generation), multi-provider routing, and embeddable widgets.** Built with FastAPI, SvelteKit, PostgreSQL/pgvector, and Redis.

Deploy once. Use everywhere — REST API, WebSocket, embeddable chat widget, or as an OpenAI-compatible drop-in replacement.

---

## What Kirana Does

```
                     ┌──────────────────────────────┐
                     │         Kirana Server          │
                     │                                │
  Client ──────────▶ │  Auth → Channel → RAG → LLM   │ ────▶ AI Provider
  (simple HTTP)      │                                │        (OpenAI, Z.AI,
                     │  Tools: knowledge, datetime,   │         any compatible)
                     │  web search, image analysis    │
                     └──────────────────────────────┘
```

**Kirana is the middle layer.** Clients send plain HTTP requests. Kirana handles authentication, channels, tool execution, knowledge retrieval (RAG), and LLM communication. Clients don't need OpenAI SDKs, don't manage prompts, don't configure tools.

**Key difference from calling an LLM directly:** Kirana deterministically injects relevant knowledge base chunks into the LLM context before every request — the LLM always has the right information without the client having to manage retrieval.

---

## Core Features

| Feature | What it does |
|---------|-------------|
| **RAG Pipeline** | Documents → LiteParse → Chunk (tiktoken 800/120) → Embed (FastEmbed 384d) → pgvector HNSW → Deterministic context injection |
| **Multi-Provider** | Configure OpenAI, Z.AI, or any OpenAI-compatible API. Switch per channel. Active/inactive per provider. |
| **Channel System** | Each channel = provider + personality + tools + context guard. One server, unlimited use cases. |
| **Tool Calling** | query_knowledge (vector search), get_current_datetime, web search via MCP, image analysis via Vision |
| **Session Management** | Persistent chat history. Auto-cleanup. Multi-session per client. |
| **Embed Widget** | Drop-in chat iframe for any website. Customizable theme. Visitor isolation via localStorage + server sessions. |
| **Streaming** | SSE streaming (standard `stream: true`). Buffer-based resume for reconnection. |
| **Admin Panel** | SvelteKit dashboard at `/panel`. Manage providers, channels, knowledge, sessions. |
| **Auth** | API key, admin token, client API key (hashed), embed token. Per-endpoint granularity. |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose (for infrastructure)
- Python 3.11+ (for local backend dev)
- Node.js 22+ (for local frontend dev)
- An OpenAI-compatible API key

### Option 1: Full Docker (Recommended for Production)

```bash
# Pull the image
docker pull ghcr.io/utsmannn/kirana:latest

# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  kirana:
    image: ghcr.io/utsmannn/kirana:latest
    ports:
      - "8000:8000"
    environment:
      - KIRANA_API_KEY=your-secure-api-key
      - ADMIN_PASSWORD=your-admin-password
      - SECRET_KEY=$(openssl rand -hex 32)
      - DB_HOST=postgres
      - DB_USER=kirana
      - DB_PASS=kirana
      - DB_NAME=kirana
      - REDIS_HOST=redis
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
EOF

docker compose up -d
```

Verify:
```bash
curl http://localhost:8000/health
# {"app":"kirana","status":"ok","database":"ok","redis":"ok"}
```

### Option 2: Local Development (Recommended for Customization)

Infrastructure runs in Docker. Backend + frontend run locally for hot-reload.

```bash
# 1. Start infrastructure (PostgreSQL + Redis)
make infra

# 2. Install dependencies
make install-python
make install-web

# 3. Run migrations
make migrate

# 4. Start backend + frontend (both print logs to console)
make dev
```

**What `make dev` does:** Starts `uvicorn` on port 8000 and `vite dev` on port 5173 concurrently. Both log to the same terminal. Ctrl+C stops both.

See the **[Makefile](Makefile)** for all targets.

### Quick Test

```bash
# Login to admin panel
curl -X POST http://localhost:8000/v1/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password":"admin"}'
# → {"token": "abc123..."}

# Chat
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'
```

Open **http://localhost:8000/panel** for the admin dashboard.

---

## Architecture Deep Dive

### RAG Pipeline

This is the core knowledge system. Every uploaded document goes through this pipeline:

```
Document (PDF/DOCX/XLSX/TXT/CSV)
    │
    ▼
┌──────────────┐
│  LiteParse   │  OCR-enabled smart parsing (Indonesian OCR).
│  Parser      │  Falls back to generic extraction.
└──────┬───────┘
       │ ParsedDocument (text + page/bbox/font metadata)
       ▼
┌──────────────┐
│  Chunking    │  tiktoken cl100k_base. 800-token chunks.
│              │  120-token overlap. Paragraph-aware splitting.
└──────┬───────┘
       │ List[RagChunk] (text + provenance metadata)
       ▼
┌──────────────┐
│  Embedding   │  FastEmbed: paraphrase-multilingual-MiniLM-L12-v2
│              │  Dimension: 384. Batched (32 at a time).
└──────┬───────┘
       │ KnowledgeChunk rows with pgvector embeddings
       ▼
┌──────────────┐
│  pgvector    │  HNSW index. Cosine distance.
│  Storage     │  Stores embeddings + metadata.
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Retrieval   │  On chat: embed user query → cosine search
│  (at query   │  → deduplicate → top-10 chunks → format as
│   time)      │  [S1], [S2] citations → inject into LLM context
└──────────────┘
```

**Key design decisions:**
- **Deterministic, not tool-based.** RAG context is injected before every chat request — the LLM doesn't decide whether to search. This ensures it always has relevant knowledge.
- **pgvector, not Qdrant.** Kirana already ships pgvector Postgres. No extra service needed.
- **Chunks preserve provenance.** Each chunk knows its source document, page number, bbox coordinates, and extraction method. Citations are traceable.

### Chat Flow

```
POST /v1/chat/completions
    │
    ▼
1. Authenticate (API key / admin token / embed token / client API key)
    │
    ▼
2. Resolve Channel → get provider credentials, personality, context guard
    │
    ▼
3. Build system prompt (personality + context guard + tool definitions)
    │
    ▼
4. Retrieve RAG context (embed user query → pgvector search → format citations)
    │
    ▼
5. Inject RAG context into system prompt (deterministic, not tool-based)
    │
    ▼
6. Call LLM via OpenAI SDK (using channel's provider — not .env fallback)
    │
    ▼
7. Stream or return response
```

### Provider + Channel Model

```
┌──────────────────┐
│ ProviderCredential│  ← API key, base URL, model name
│ (one per AI API)  │
└────────┬─────────┘
         │ 1:N
         ▼
┌──────────────────┐
│     Channel       │  ← Personality, system prompt, tools, context guard
│ (one per use-case)│
└────────┬─────────┘
         │ 1:N
         ▼
┌──────────────────┐
│     Session       │  ← Individual chat conversations
└──────────────────┘
```

**Why this way:** One provider can power many channels (e.g., "Support Bot", "Sales Assistant", "Code Reviewer"), each with different personalities, tools, and knowledge scope. Clients just specify a `channel_id`.

---

## Authentication

Kirana has **4 auth methods**, all using `Authorization: Bearer <token>`:

| Method | Token | Used by | Scope |
|--------|-------|---------|-------|
| **Server API Key** | `KIRANA_API_KEY` from `.env` | Admin scripts, internal services | All endpoints |
| **Admin Token** | From `POST /v1/admin/login` | Admin panel users | All endpoints (rotates daily) |
| **Client API Key** | From `POST /v1/clients` (registration) | External API consumers | `/v1/clients/me`, chat, knowledge |
| **Embed Token** | From channel config (`?embed_token=...`) | Embed widget visitors | Chat only (per-channel) |

**Client API keys are SHA256-hashed** in the database. The raw key is shown only once at registration time.

```bash
# Register as an external client
curl -X POST http://localhost:8000/v1/clients/ \
  -H "Content-Type: application/json" \
  -d '{"name":"My App","email":"dev@example.com"}'
# Response includes api_key — save it, it won't be shown again

# Use the client API key
curl http://localhost:8000/v1/clients/me \
  -H "Authorization: Bearer kir_xxxxxxxxxxxx"
```

---

## API Reference

### Base URL: `http://localhost:8000/v1`

### Chat

**`POST /v1/chat/completions`** — OpenAI-compatible chat endpoint.

```bash
# Non-streaming
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What is Kirana?"}],
    "channel_id": "<uuid>",
    "session_id": "<uuid>",
    "stream": false
  }'

# Streaming (SSE)
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Tell me a story"}],
    "channel_id": "<uuid>",
    "stream": true
  }'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | array | Yes | OpenAI-format message array `[{"role":"user","content":"..."}]` |
| `channel_id` | UUID | No | Which channel to use (falls back to default) |
| `session_id` | UUID | No | For persistent conversations (Kirana manages history) |
| `stream` | bool | No | Enable SSE streaming (default: false) |
| `visitor_id` | string | No | For embed widget visitor tracking |

**`WS /v1/chat/ws`** — WebSocket for real-time streaming chat.

```
ws://localhost:8000/v1/chat/ws?channel_id=<uuid>&token=<api_key>
```

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/sessions` | Create session |
| `GET` | `/v1/sessions` | List sessions |
| `GET` | `/v1/sessions/{id}` | Get session details |
| `PATCH` | `/v1/sessions/{id}` | Update session |
| `DELETE` | `/v1/sessions/{id}` | Delete session |
| `GET` | `/v1/sessions/{id}/messages` | Get conversation history |

### Knowledge Base (RAG)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/knowledge` | Create text knowledge item |
| `GET` | `/v1/knowledge` | List/search knowledge items |
| `GET` | `/v1/knowledge/{id}` | Get single item |
| `PATCH` | `/v1/knowledge/{id}` | Update item (re-indexes chunks) |
| `DELETE` | `/v1/knowledge/{id}` | Delete item + chunks |
| `POST` | `/v1/knowledge/upload` | Upload file → auto-parse → auto-chunk |
| `POST` | `/v1/knowledge/scrape-web` | Scrape single URL → knowledge |
| `POST` | `/v1/knowledge/crawl-web` | Crawl entire site → knowledge |
| `GET` | `/v1/knowledge/{id}/download` | Download original file |

**Upload supported formats:**

| Format | Extensions | Parser | Notes |
|--------|-----------|--------|-------|
| PDF | `.pdf` | LiteParse (OCR) | Falls back to text extraction + Vision API |
| Word | `.docx` | LiteParse | `.doc` not supported (convert to `.docx`) |
| Excel | `.xlsx` | Vision API | Sheet-by-sheet image analysis |
| PowerPoint | `.pptx` | Text extraction | AI summary appended |
| Text/CSV/Markdown | `.txt`, `.csv`, `.md`, `.json` | Direct | No parsing needed |
| Images | `.png`, `.jpg`, `.jpeg` | Vision API | OCR + description |

```bash
# Upload a document
curl -X POST http://localhost:8000/v1/knowledge/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@document.pdf" \
  -F "title=Company Handbook"

# The file is automatically:
# 1. Parsed (LiteParse for PDF/DOCX, direct for text)
# 2. Chunked into 800-token segments
# 3. Embedded with FastEmbed (384-dim)
# 4. Stored in pgvector with HNSW index
# After this, chat requests will automatically retrieve relevant chunks.
```

### Channels

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/channels` | List channels |
| `POST` | `/v1/channels` | Create channel |
| `GET` | `/v1/channels/{id}` | Get channel |
| `PATCH` | `/v1/channels/{id}` | Update channel |
| `DELETE` | `/v1/channels/{id}` | Delete channel |
| `POST` | `/v1/channels/{id}/set-default` | Set as default channel |
| `POST` | `/v1/channels/{id}/embed` | Enable embed widget |
| `GET` | `/v1/channels/{id}/embed` | Get embed config (auth required) |
| `GET` | `/v1/channels/{id}/embed/public` | Get public embed config (no auth) |
| `DELETE` | `/v1/channels/{id}/embed` | Disable embed |

### Providers

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/providers` | List providers |
| `POST` | `/v1/providers` | Create provider |
| `GET` | `/v1/providers/{id}` | Get provider |
| `PATCH` | `/v1/providers/{id}` | Update provider |
| `DELETE` | `/v1/providers/{id}` | Delete provider |
| `POST` | `/v1/providers/{id}/activate` | Activate provider |
| `POST` | `/v1/providers/{id}/reorder` | Reorder priority |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/admin/login` | Login → admin token |
| `GET` | `/v1/admin/verify` | Verify token valid |
| `GET` | `/v1/admin/config` | Get admin config |

### Clients (External API Consumers)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/clients` | None | Register → get API key |
| `GET` | `/v1/clients/me` | Client key | Get client profile |
| `POST` | `/v1/clients/me/regenerate-key` | Client key | Rotate API key |

### Other

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/config` | Get client config |
| `PATCH` | `/v1/config` | Update client config |
| `GET` | `/v1/personalities` | List personality templates |
| `GET` | `/v1/tools` | List available tools |
| `POST` | `/v1/tools/execute` | Execute a tool directly |
| `GET` | `/v1/usage` | Usage statistics |

---

## Configuration

### Environment Variables

All variables with their defaults. Required ones are marked.

#### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `kirana` | Application name |
| `APP_ENV` | `development` | Environment (`development`, `production`) |
| `DEBUG` | `false` | Debug mode |
| `SECRET_KEY` | (random) | Secret for token generation — **change in production** |

#### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `KIRANA_API_KEY` | `kirana-default-api-key-change-me` | Server API key — **change in production** |
| `ADMIN_PASSWORD` | `admin` | Admin panel password — **change in production** |

#### LLM Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Default LLM API key (used if no provider configured) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Default LLM base URL |
| `DEFAULT_MODEL` | `gpt-4o-mini` | Default model name |
| `LLM_TIMEOUT` | `60` | Request timeout (seconds) |
| `LLM_MAX_RETRIES` | `3` | Max retry attempts |

#### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_USER` | `kirana` | PostgreSQL user |
| `DB_PASS` | `kirana` | PostgreSQL password |
| `DB_NAME` | `kirana` | PostgreSQL database |
| `DB_POOL_SIZE` | `20` | Connection pool size |
| `DB_MAX_OVERFLOW` | `10` | Max overflow connections |
| `DB_POOL_RECYCLE` | `3600` | Connection recycle (seconds) |

#### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |

#### RAG Pipeline

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_ENABLED` | `true` | Enable RAG context injection |
| `RAG_EMBED_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | FastEmbed model |
| `RAG_EMBED_DIM` | `384` | Embedding dimension |
| `RAG_CHUNK_MAX_TOKENS` | `800` | Max tokens per chunk |
| `RAG_CHUNK_OVERLAP_TOKENS` | `120` | Token overlap between chunks |
| `RAG_TOP_K` | `10` | Max chunks retrieved per query |
| `RAG_MAX_CONTEXT_CHARS` | `12000` | Max context characters injected |
| `RAG_EMBED_BATCH_SIZE` | `32` | Batch size for embedding |

#### LiteParse (Document Parsing)

| Variable | Default | Description |
|----------|---------|-------------|
| `LITEPARSE_ENABLED` | `true` | Enable LiteParse for document parsing |
| `LITEPARSE_OCR_LANGUAGE` | `ind` | OCR language code |
| `LITEPARSE_MAX_PAGES` | `1000` | Max pages to parse |
| `LITEPARSE_DPI` | `150` | DPI for OCR rendering |

#### Vision API (Image/Excel Analysis)

| Variable | Default | Description |
|----------|---------|-------------|
| `ZAI_API_KEY` | — | Z.AI API key for Vision (GLM-4V) |
| `ZAI_VISION_BASE_URL` | `https://api.z.ai/api/coding/paas/v4` | Vision API base URL |
| `ZAI_VISION_MODEL` | `glm-4.6v` | Vision model name |

#### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Max requests/minute per client |

#### Session Management

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_EXPIRY_DAYS` | `3` | Days before session considered inactive |
| `SESSION_DELETION_DAYS` | `7` | Days before session is deleted |
| `SESSION_CLEANUP_INTERVAL_HOURS` | `1` | Cleanup interval |

#### CORS & Uploads

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `*` | Allowed origins (comma-separated) |
| `UPLOAD_DIR` | `/app/uploads` | Upload directory path |

---

## Embed Widget

Add a chat widget to any website with a single iframe:

```html
<iframe
  src="http://your-server:8000/embed/CHANNEL_ID?embed_token=YOUR_TOKEN&primary_color=%234f46e5"
  width="400"
  height="600"
  style="border: none; border-radius: 12px;"
></iframe>
```

**URL parameters:**

| Parameter | Description |
|-----------|-------------|
| `embed_token` | Auth token from channel config |
| `primary_color` | Accent color (hex, URL-encoded: `%23` = `#`) |
| `header_title` | Custom header text (URL-encoded) |
| `theme` | `light` or `dark` |

**How visitor isolation works:**
1. First visit → widget generates `visitor_id`, saves to localStorage
2. Backend creates session named `Embed - {visitor_id}`
3. Subsequent visits reuse the same session
4. Each browser/device gets its own session — no cross-user mixing

Enable embed in admin panel: **Channels → Edit → Embed → Enable**.

---

## Client SDK Examples

Kirana is plain HTTP. Any language works. No special SDK needed.

### Python

```python
import requests

KIRANA = "http://localhost:8000/v1"
TOKEN = "kirana-default-api-key-change-me"

def chat(message: str, channel_id: str = None, session_id: str = None) -> str:
    resp = requests.post(
        f"{KIRANA}/chat/completions",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={
            "messages": [{"role": "user", "content": message}],
            "channel_id": channel_id,
            "session_id": session_id,
            "stream": False,
        },
    )
    return resp.json()["choices"][0]["message"]["content"]

# Usage
print(chat("What is RAG?"))

# With session persistence
session = requests.post(
    f"{KIRANA}/sessions/",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"title": "My Chat"},
).json()

print(chat("My name is Bob", session_id=session["id"]))
print(chat("What is my name?", session_id=session["id"]))
# → "Your name is Bob."
```

### JavaScript / TypeScript

```typescript
const KIRANA = "http://localhost:8000/v1";
const TOKEN = "kirana-default-api-key-change-me";

async function chat(message: string, sessionId?: string): Promise<string> {
  const resp = await fetch(`${KIRANA}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      messages: [{ role: "user", content: message }],
      session_id: sessionId,
      stream: false,
    }),
  });
  const data = await resp.json();
  return data.choices[0].message.content;
}

// Streaming
async function* chatStream(message: string) {
  const resp = await fetch(`${KIRANA}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      messages: [{ role: "user", content: message }],
      stream: true,
    }),
  });

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    for (const line of buffer.split("\n")) {
      if (line.startsWith("data: ")) {
        const text = line.slice(6);
        if (text === "[DONE]") return;
        try {
          const chunk = JSON.parse(text);
          yield chunk.choices?.[0]?.delta?.content || "";
        } catch {}
      }
    }
    buffer = buffer.includes("\n") ? buffer.split("\n").pop()! : "";
  }
}
```

### cURL (one-liners)

```bash
# Chat
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hi"}],"stream":false}'

# Create knowledge
curl -X POST http://localhost:8000/v1/knowledge/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"title":"FAQ","content":"Our return policy is 30 days."}'

# Upload file
curl -X POST http://localhost:8000/v1/knowledge/upload \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -F "file=@handbook.pdf" -F "title=Employee Handbook"
```

---

## Deployment

### Docker Image (ghcr.io)

Pre-built multi-arch images (amd64 + arm64):

```bash
docker pull ghcr.io/utsmannn/kirana:latest
```

**Available tags:**

| Tag | Description |
|-----|-------------|
| `latest` | Latest stable release |
| `v1.0.0` | Specific version |
| `1.0` | Major.minor |

### Creating a Release

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions will:
1. Build multi-arch Docker image
2. Push to `ghcr.io/utsmannn/kirana`
3. Create GitHub Release with changelog

### Production Checklist

- [ ] Change `KIRANA_API_KEY` to a strong random value
- [ ] Change `ADMIN_PASSWORD` to a strong password
- [ ] Set `SECRET_KEY` to a random 64-char hex string
- [ ] Set `APP_ENV=production` and `DEBUG=false`
- [ ] Configure CORS origins to your domain (not `*`)
- [ ] Use a reverse proxy (nginx/Caddy) with TLS
- [ ] Set up database backups for PostgreSQL
- [ ] Configure `RATE_LIMIT_REQUESTS_PER_MINUTE` for production load
- [ ] Mount persistent volumes for uploads, postgres, redis

---

## Project Structure

```
kirana/
├── app/                          # FastAPI backend
│   ├── api/
│   │   ├── deps.py               # Auth dependencies
│   │   └── v1/                   # API v1 endpoints
│   │       ├── admin.py          # Admin login/config
│   │       ├── channels.py       # Channel CRUD + embed
│   │       ├── chat.py           # Chat completions + WebSocket
│   │       ├── clients.py        # External client registration
│   │       ├── config.py         # Client config
│   │       ├── knowledge.py      # Knowledge CRUD + upload + RAG indexing
│   │       ├── personalities.py  # Personality templates
│   │       ├── providers.py      # Provider credential CRUD
│   │       ├── router.py         # Route aggregation
│   │       ├── sessions.py       # Session CRUD
│   │       ├── tools.py          # Tool listing + execution
│   │       └── usage.py          # Usage statistics
│   ├── config.py                 # Settings (env vars → Pydantic)
│   ├── core/
│   │   └── security.py           # API key generation + verification
│   ├── db/
│   │   └── session.py            # AsyncSession factory
│   ├── models/                   # SQLAlchemy ORM models
│   │   ├── channel.py
│   │   ├── client.py
│   │   ├── knowledge.py
│   │   ├── knowledge_chunk.py    # pgvector chunks (RAG)
│   │   └── ...
│   ├── schemas/                  # Pydantic request/response schemas
│   ├── services/
│   │   ├── chat_service.py       # Chat orchestration + RAG injection
│   │   ├── file_processor.py     # Legacy file extraction (fallback)
│   │   ├── liteparse_parser.py   # LiteParse document parsing
│   │   ├── mcp_client.py         # MCP server client
│   │   ├── rag_chunking.py       # Text → chunks (tiktoken)
│   │   ├── rag_embeddings.py     # Text → vectors (FastEmbed)
│   │   ├── rag_ingestion.py      # Orchestrates parse → chunk → embed → store
│   │   ├── rag_retrieval.py      # Vector search + context formatting
│   │   └── stream_buffer.py      # SSE stream buffer for resume
│   ├── tasks/                    # Background tasks (cleanup, etc.)
│   ├── tools/                    # LLM tool implementations
│   │   ├── base.py
│   │   ├── datetime_tool.py
│   │   ├── image_analyzer_tool.py
│   │   └── knowledge_tool.py     # query_knowledge (vector-backed)
│   └── main.py                   # FastAPI app factory
├── web/                          # SvelteKit admin panel
│   ├── src/
│   │   ├── routes/               # Page routes
│   │   └── lib/
│   │       ├── api.ts            # API client (typed)
│   │       └── components/       # UI components
│   └── vite.config.ts
├── alembic/                      # Database migrations
│   └── versions/
├── scripts/
│   ├── backfill_knowledge_chunks.py  # Backfill chunk embeddings
│   ├── init_db.py
│   └── seed_personalities.py
├── docs/
│   └── TECH_DOC.md               # Comprehensive technical reference
├── docker-compose.yml            # Infrastructure (PostgreSQL + Redis)
├── Dockerfile                    # Multi-stage production image
├── Makefile                      # Local dev workflow
├── requirements.txt
└── pyproject.toml
```

---

## RAG Behavior

**What happens when you chat after uploading knowledge:**

1. User sends: *"What is the return policy?"*
2. Kirana embeds the user query (FastEmbed, 384-dim)
3. Searches `knowledge_chunks` via pgvector cosine distance
4. Retrieves top-10 most relevant chunks (max 12,000 chars total)
5. Injects into system prompt:
   ```
   ## KNOWLEDGE BASE CONTEXT
   [S1] Return Policy
   Source: knowledge/abc-123 | Type: text
   Our return policy allows returns within 30 days of purchase.
   [S2] Refund Process
   Source: knowledge/abc-123 | Type: text
   Refunds are processed within 5-7 business days.
   ```
6. LLM responds with citations: *"You can return items within 30 days [S1]. Refunds take 5-7 business days [S2]."*

**The LLM is instructed to:**
- Use retrieved context as primary source
- Say "I don't have that information" if answer isn't in context
- Cite sources with `[S1]`, `[S2]` when using knowledge base content
- Respond in the same language the user used

---

## Context Guard

Restrict a channel's AI to a specific domain.

**Config (via admin panel or API):**
- `context`: Short name (e.g., "Acme Corp", "SMK Negeri 1")
- `context_description`: Detailed scope

**Behavior with context guard:**

| User asks | AI responds |
|-----------|------------|
| "What are your business hours?" | ✅ Answers (within context) |
| "How do I apply?" | ✅ Answers (within context) |
| "What's the weather today?" | ❌ "I can only answer questions about Acme Corp" |
| "Tell me a joke" | ❌ Politely declines |

**Without context guard:** AI answers any question freely.

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **Backend** | FastAPI (Python 3.11) | Async, OpenAPI docs, type-safe |
| **Frontend** | SvelteKit | Fast builds, SPA mode, small bundle |
| **Database** | PostgreSQL 16 + pgvector | Vector search without extra service |
| **Cache** | Redis 7 | Rate limiting, session cache |
| **LLM SDK** | OpenAI SDK (openai) | Direct, no litellm wrapper |
| **Embeddings** | FastEmbed (sentence-transformers) | Local, no API calls, 384-dim |
| **Chunking** | tiktoken (cl100k_base) | Same tokenizer as GPT-4 |
| **Parsing** | LiteParse | OCR-enabled, page/bbox provenance |
| **Container** | Docker (multi-arch) | amd64 + arm64, ghcr.io registry |

---

## Troubleshooting

### 401 on chat/upload/download after login
The admin panel login gives you an admin token. Make sure the frontend sends this token correctly. If using API directly, ensure your `Authorization: Bearer <token>` header is set.

### RAG not retrieving
- Check `RAG_ENABLED=true` in `.env`
- Verify chunks exist: knowledge items created before the RAG migration need backfill: `python scripts/backfill_knowledge_chunks.py --only-active`
- Check that the knowledge item is `is_active=true`

### Upload not parsing
- LiteParse handles PDF, DOCX, TXT, CSV natively
- For `.doc` files: convert to `.docx` first
- For scanned PDFs: ensure `LITEPARSE_OCR_ENABLED=true` and Tesseract is installed

### Streaming not working
- Use `-N` flag with curl (disables output buffering)
- Ensure client reads SSE events properly (look for `data: [DONE]`)
- For WebSocket: ensure the connection URL includes auth (`?token=...`)

### Provider not being used (falls back to .env)
- Check the channel's `provider_id` references an active provider
- Check `is_active=true` on the provider
- The `.env` values (`OPENAI_API_KEY`, `OPENAI_BASE_URL`) are only used as fallback when no provider is configured

---

## License

MIT

---

**Built with:** FastAPI · SvelteKit · PostgreSQL/pgvector · Redis · FastEmbed · LiteParse · tiktoken · OpenAI SDK
