# Kirana — AI Chat Platform with RAG

**Production-ready AI chat API with built-in RAG, multi-provider routing, and embeddable widgets.** Built with FastAPI, SvelteKit, PostgreSQL/pgvector, and Redis.

```
Build me a chatbot app with RAG and knowledge management using Kirana, start with https://raw.githubusercontent.com/utsmannn/kirana/main/docs/AI_AGENT_PROMPT.md
```

---

## What Kirana Does

```mermaid
flowchart LR
    C[Client<br/>simple HTTP] --> K[Kirana Server]
    subgraph K[Kirana Server]
        direction LR
        A[Auth] --> CH[Channel] --> R[RAG] --> L[LLM]
        T[Tools:<br/>knowledge<br/>datetime<br/>image analysis]
    end
    K --> P[AI Provider<br/>OpenAI, Z.AI,<br/>any compatible]
```

**Kirana is the middle layer.** Clients send plain HTTP requests. Kirana handles authentication, channel routing, tool execution, knowledge retrieval (RAG), and LLM communication.

**Key difference from calling an LLM directly:** Kirana deterministically injects relevant channel-scoped knowledge chunks into the LLM context before every request — the LLM always has the right channel context.

### Core Features

| Feature | What it does |
|---------|-------------|
| **RAG Pipeline** | Channel documents → LiteParse → Chunk → Embed (FastEmbed 384d) → pgvector HNSW → deterministic channel-scoped context injection |
| **Multi-Provider** | Configure OpenAI, Z.AI, or any OpenAI-compatible API. Switch per channel. |
| **Channel System** | Each channel = provider + personality + tools + context guard. One server, unlimited use cases. |
| **Tool Calling** | Channel-scoped query_knowledge, get_current_datetime, image analysis (Z.AI Vision → LLM fallback), web search via MCP |
| **Embed Widget** | Drop-in chat iframe with customizable theme and visitor isolation. |
| **Streaming** | SSE streaming + buffer-based resume for reconnection. |
| **Admin Panel** | SvelteKit dashboard at `/panel`. |

---

## Architecture

```mermaid
flowchart TD
    PC[ProviderCredential<br/>API key, base URL, model] -->|1:N| CH
    CH[Channel<br/>Personality, system prompt, tools, context guard] -->|1:N| S
    S[Session<br/>Individual conversations]

    CH --> R[RAG Pipeline<br/>pgvector retrieval]
    R --> LLM[LLM Call<br/>OpenAI SDK]
```

```mermaid
flowchart TD
    A[POST /v1/chat/send] --> B[Authenticate]
    B --> C[Resolve Channel → Provider]
    C --> D[Build System Prompt]
    D --> E[RAG Retrieval → Inject Context]
    E --> F[Call LLM]
    F --> G[Stream or Return Response]
```

**See [`docs/TECH_DOC.md`](docs/TECH_DOC.md)** for RAG pipeline internals, database schema, chat service details, and streaming implementation.

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ and Node.js 22+ (for local dev)
- An OpenAI-compatible API key

### Option 1: Docker

```bash
docker pull ghcr.io/utsmannn/kirana:latest

# Create docker-compose.yml (full example in docs/AI_AGENT_PROMPT.md)
# Start it
docker compose up -d

# Verify
curl http://localhost:8000/health
# → {"app":"kirana","status":"ok","database":"ok","redis":"ok"}
```

### Option 2: Local Development

```bash
make infra              # Start PostgreSQL + Redis in Docker
make install-python     # Install Python deps
make install-web        # Install frontend deps
make migrate            # Run DB migrations
make dev                # Start backend (8000) + frontend (5173)
```

### Quick Test

```bash
# Login
curl -X POST http://localhost:8000/v1/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password":"admin"}'

# List channels
curl http://localhost:8000/v1/channels/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me"

# Chat
curl -X POST http://localhost:8000/v1/chat/send \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello!"}],"channel_id":"<uuid>","stream":false}'
```

Open **http://localhost:8000/panel** for the admin dashboard.

---

## API at a Glance

**Base URL:** `http://<host>:8000/v1` · **Auth:** `Authorization: Bearer <token>`

| Group | Key endpoints |
|-------|--------------|
| Chat | `POST /v1/chat/send` · `WS /v1/chat/ws` · `GET /v1/chat/stream/{id}` |
| Knowledge | `POST /v1/channels/{channel_id}/knowledge/upload` · `GET/POST/PATCH/DELETE /v1/channels/{channel_id}/knowledge/` |
| Channels | `GET/POST /v1/channels/` · `POST /v1/channels/{id}/embed` · per-channel knowledge management |
| Providers | `GET/POST /v1/providers/` · `POST /v1/providers/{id}/activate` |
| Sessions | `GET/POST /v1/sessions/` · `GET /v1/sessions/{id}/messages` |
| Admin | `POST /v1/admin/login` |
| Clients | `POST /v1/clients/` (register) · `GET /v1/clients/me` |
| Other | `GET /v1/config/` · `GET /v1/personalities/` · `GET /v1/tools/` · `GET /v1/usage/` |

> Trailing slash on collection endpoints: `/v1/providers/` ✅ · `/v1/providers` ❌

**Full API contract with request/response schemas, auth details, error codes, and integration flows: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)**

---

## Authentication

| Method | Token source | Scope |
|--------|-------------|-------|
| **Server API Key** | `KIRANA_API_KEY` from `.env` | All endpoints |
| **Admin Token** | `POST /v1/admin/login` (rotates daily) | All endpoints |
| **Client API Key** | `POST /v1/clients/` (SHA256-hashed, shown once) | Chat, knowledge, `/v1/clients/me` |
| **Embed Token** | Channel config (`?embed_token=...`) | Chat only, per-channel |

---

## Embed Widget

```html
<iframe
  src="http://your-server:8000/embed/CHANNEL_ID?embed_token=TOKEN&primary_color=%234f46e5"
  width="400" height="600"
  style="border: none; border-radius: 12px;"
></iframe>
```

URL params: `embed_token`, `primary_color`, `header_title`, `theme` (`light`|`dark`).

Enable in admin panel: **Channels → Edit → Embed → Enable**.

---

## RAG — Knowledge Upload & Retrieval

```bash
curl -X POST http://localhost:8000/v1/channels/<channel_id>/knowledge/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@handbook.pdf" -F "title=Employee Handbook"
```

**Pipeline:** Upload → LiteParse → Chunk (tiktoken 800/120) → Embed (FastEmbed 384d) → pgvector HNSW

**Upload is fire-and-forget.** `POST /v1/channels/{channel_id}/knowledge/upload` returns immediately with `"processing_status": "processing"`. Heavy work (parsing, vision, indexing) runs in the background. Poll `GET /v1/channels/{channel_id}/knowledge/{id}` — when `processing_status` becomes `"ready"` the document is indexed and queryable. Check `metadata.processing_error` if status is `"failed"`.

Knowledge is scoped per channel. RAG retrieval and the `query_knowledge` tool require the chat channel and do not fall back to global or unassigned knowledge.

**At query time:** User message → channel-scoped embed search → top-10 chunks → inject `[S1] [S2]` citations into system prompt → LLM responds with sourced answers.

RAG is **deterministic** — it runs before every chat request automatically.

---

## Provider Error Handling

Kirana does **not** silently fallback to `.env` when a channel's provider is misconfigured.

| Error | Status | What to do |
|-------|--------|------------|
| `provider_config_error` | 502 | Fix provider config — inactive/missing provider |
| `provider_error` (AuthenticationError) | 502 | Update API key |
| `provider_error` (RateLimitError) | 429 | Retry with backoff |
| `provider_error` (APITimeoutError/APIConnectionError) | 504 | Check base URL, retry with backoff |

Streaming errors are sent as SSE payloads before `[DONE]`.

---

## Configuration

All environment variables with defaults are in **[`.env.example`](.env.example)** and **[`app/config.py`](app/config.py)**.

Key vars:

| Variable | Default | Notes |
|----------|---------|-------|
| `KIRANA_API_KEY` | `kirana-default-api-key-change-me` | **Change in production** |
| `ADMIN_PASSWORD` | `admin` | **Change in production** |
| `SECRET_KEY` | (random) | **Change in production** |
| `OPENAI_API_KEY` | — | Default LLM API key |
| `DEFAULT_MODEL` | `gpt-4o-mini` | Fallback model |
| `RAG_ENABLED` | `true` | Enable RAG |
| `ZAI_API_KEY` | — | Optional — Z.AI Vision API key. Falls back to LLM provider if not set |

---

## Deployment

```bash
docker pull ghcr.io/utsmannn/kirana:latest
```

Multi-arch image (amd64 + arm64). GitHub Actions builds on release/tag.

### Production Checklist

- [ ] Change `KIRANA_API_KEY`, `ADMIN_PASSWORD`, `SECRET_KEY`
- [ ] Set `APP_ENV=production`, `DEBUG=false`
- [ ] Restrict `CORS_ORIGINS` to your domain
- [ ] Use a reverse proxy (nginx/Caddy) with TLS
- [ ] Set up PostgreSQL backups
- [ ] Mount persistent volumes for uploads, postgres, redis

**Full deployment guide:** [`docs/AI_AGENT_PROMPT.md`](docs/AI_AGENT_PROMPT.md)

---

## Client SDK Example

Kirana is plain HTTP. No special SDK needed.

**Python:**
```python
import requests

def chat(msg: str, channel_id: str, token: str, session_id: str = None) -> str:
    r = requests.post("http://localhost:8000/v1/chat/send",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"role":"user","content":msg}],
              "channel_id": channel_id, "session_id": session_id, "stream": False})
    return r.json()["choices"][0]["message"]["content"]
```

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/chat/send \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hi"}],"channel_id":"<id>","stream":false}'
```

---

## Project Structure

```
kirana/
├── app/                    # FastAPI backend
│   ├── api/v1/             # Route handlers
│   ├── services/           # Chat, RAG, LiteParse, MCP
│   ├── models/             # SQLAlchemy ORM
│   └── config.py           # Settings
├── web/                    # SvelteKit admin panel
├── alembic/                # DB migrations
├── scripts/                # Backfill, seed
├── docs/                   # TECH_DOC, API_REFERENCE, AI_AGENT_PROMPT
├── docker-compose.yml      # Infrastructure services
├── Dockerfile              # Multi-stage production image
├── Makefile                # Local dev workflow
└── requirements.txt
```

**Full tree:** [`docs/TECH_DOC.md`](docs/TECH_DOC.md)

---

## Context Guard

Restrict a channel's AI to a specific domain by setting `context` and `context_description` on the channel. The AI will politely decline out-of-scope questions.

See channel config in admin panel: **Channels → Edit → Context Guard**.

---

## Troubleshooting

### Provider falls back to wrong model
- Pass `channel_id` in every chat request
- Verify the channel's provider is active (`GET /v1/providers/`)
- Kirana returns structured `provider_config_error` when a channel has a broken provider — it does **not** silently fallback to `.env`

### RAG not retrieving
- `RAG_ENABLED=true` in `.env`
- Backfill pre-RAG knowledge chunks if needed: `python scripts/backfill_knowledge_chunks.py --only-active`
- Verify the knowledge item belongs to the same channel used by the chat request

### Upload not parsing
- LiteParse handles PDF, DOCX, TXT, CSV; `.doc` → convert to `.docx` first
- Scanned PDFs need Tesseract installed

### Streaming not working
- curl: use `-N` flag (disables output buffering)
- WebSocket: include auth (`?token=...`)

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI (Python 3.11) |
| Frontend | SvelteKit |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| LLM SDK | OpenAI SDK (AsyncOpenAI) |
| Embeddings | FastEmbed (paraphrase-multilingual-MiniLM-L12-v2, 384d) |
| Chunking | tiktoken (cl100k_base) |
| Parsing | LiteParse (OCR-enabled) |
| Image Analysis | Z.AI GLM-4.6V (falls back to configured LLM provider if ZAI_API_KEY not set) |
| Container | Docker multi-arch (ghcr.io) |

---

## Docs Index

| Doc | Contents |
|-----|----------|
| [`docs/AI_AGENT_PROMPT.md`](docs/AI_AGENT_PROMPT.md) | AI agent guide: install, deploy, API exploration, integration flow |
| [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) | Full API contract: endpoints, auth, schemas, error codes, canonical flows |
| [`docs/TECH_DOC.md`](docs/TECH_DOC.md) | Internals: RAG pipeline, DB schema, chat service, streaming, deployment |
| [`.env.example`](.env.example) | All environment variables with defaults |
| [`app/config.py`](app/config.py) | Pydantic Settings model |

---

## License

MIT
