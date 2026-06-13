# Kirana — AI Agent Guide

Kirana is a production-ready AI chat platform with built-in RAG. It wraps AI providers (OpenAI, Z.AI, any OpenAI-compatible API) behind a **Provider → Channel → Session** architecture and deterministically injects knowledge base chunks into every chat request so the LLM always has the right context.

Use this guide when an AI agent needs to install Kirana locally, understand its API surface, or build an integration on top of it.

---

## What Kirana Provides

- **`POST /v1/chat/send`** — primary chat endpoint with OpenAI-compatible message format, SSE streaming support, and deterministic RAG context injection.
- **RAG pipeline** — document upload → LiteParse → chunk (tiktoken 800/120) → embed (FastEmbed 384d) → pgvector HNSW storage → automatic context injection at query time.
- **Multi-provider routing** — configure multiple AI APIs, switch per channel, activate/deactivate. No silent fallback when a channel's provider is broken.
- **Channel system** — each channel binds a provider to a personality, system prompt, tools, and context guard. One server, unlimited use cases.
- **Embed widget** — drop-in chat iframe for any website with visitor isolation and customizable theme.
- **Admin panel** — SvelteKit dashboard at `/panel`.

---

## Files to Read (in order)

| # | File | Purpose |
|---|------|---------|
| 1 | `README.md` | Project overview, quick start, deployment, RAG behavior, configuration reference. |
| 2 | `docs/API_REFERENCE.md` | Complete API contract: every endpoint, auth methods, request/response schemas, trailing-slash rules, provider error codes, canonical integration flows. |
| 3 | `docs/TECH_DOC.md` | Internals: chat service orchestration, RAG pipeline, database schema, provider resolution, streaming, error handling, deployment. |
| 4 | `app/api/v1/router.py` | All registered API routes and their prefixes. |
| 5 | `app/api/deps.py` | Authentication dependencies (`verify_api_key`, `verify_api_key_or_admin_token`, `verify_chat_auth`, `get_current_client`, etc.). |
| 6 | `app/schemas/chat.py` | `ChatCompletionRequest` / `ChatCompletionResponse` Pydantic models — the primary API contract. |
| 7 | `app/services/chat_service.py` | Chat orchestration: provider resolution, system prompt building, RAG injection, tool calling, streaming, and provider error mapping. |
| 8 | `app/api/v1/knowledge.py` | Knowledge CRUD, file upload, LiteParse parsing, RAG indexing pipeline. |
| 9 | `app/config.py` | All environment variables with defaults (Pydantic Settings model). |
| 10 | `app/core/security.py` | API key generation and SHA256 hashing. |

---

## Local Development Setup

```bash
# 1. Start infrastructure (PostgreSQL/pgvector + Redis)
make infra

# 2. Install dependencies
make install-python
make install-web

# 3. Run database migrations
make migrate

# 4. Start backend + frontend
make dev

# 5. Verify
curl http://localhost:8000/health
# Open http://localhost:8000/panel
```

Backend runs on port 8000, frontend dev server on port 5173. Ctrl+C stops both.

---

## API Exploration Order

When exploring the API to build an integration, follow this order:

1. **`POST /v1/admin/login`** — get an admin token.
2. **`GET /v1/providers/`** — inspect current provider configuration.
3. **`POST /v1/providers/`** + **`POST /v1/providers/{id}/activate`** — add and activate an AI provider if none is configured.
4. **`GET /v1/channels/`** — list channels, note the `default_channel` or pick a specific `channel_id`.
5. **`POST /v1/sessions/`** — create a session with `channel_id`.
6. **`POST /v1/chat/send`** — send chat messages with `channel_id` and optional `session_id`.
7. **`POST /v1/knowledge/upload`** — upload documents for RAG.
8. **`POST /v1/chat/send`** — ask a grounded question that should use uploaded knowledge.

---

## API Rules

### Base URL
```
http://localhost:8000/v1
```

### Auth
All endpoints use `Authorization: Bearer <token>`. Four auth methods:
- **Server API key** (`KIRANA_API_KEY` from `.env`) — full access.
- **Admin token** (from `POST /v1/admin/login`) — full access, rotates daily.
- **Client API key** (from `POST /v1/clients/`) — SHA256-hashed, external consumers.
- **Embed token** (from channel config) — chat only, per-channel isolation.

### Chat Endpoint
Use `POST /v1/chat/send` for chat. It accepts OpenAI-compatible request/response format with Kirana extensions:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | array | Yes | OpenAI-format `[{role, content}]` |
| `channel_id` | UUID | Recommended | Channel to use for provider/personality/tools |
| `session_id` | UUID | No | For persistent conversation history |
| `stream` | bool | No | Enable SSE streaming |
| `visitor_id` | string | No | Embed widget visitor tracking |

**Always pass `channel_id`** when chatting. Without it, Kirana cannot resolve the intended provider, personality, tools, or context guard.

### Trailing Slashes
FastAPI enforces strict trailing slash behavior:
- Collection endpoints need `/`: `GET /v1/providers/`, `POST /v1/knowledge/`, `POST /v1/sessions/`
- Singular endpoints must not have `/`: `GET /v1/clients/me`, `GET /v1/providers/{id}`
- Wrong slash → `307` redirect.

### Provider Errors
Provider/configuration failures return structured errors. Do not silently ignore them:

| Code | Status | Meaning |
|------|--------|---------|
| `provider_config_error` | 502 | Channel has inactive/missing provider, or no API key configured. Fix provider config — do not retry blindly. |
| `provider_error` + `AuthenticationError` | 502 | Provider rejected API key. Update credentials. |
| `provider_error` + `RateLimitError` | 429 | Upstream rate limit. Retry with backoff. |
| `provider_error` + `APITimeoutError`/`APIConnectionError` | 504 | Provider unreachable. Check base URL/network, retry with backoff. |
| `provider_error` | 502 | Generic provider API error. |

Streaming chat sends these as SSE `error` payloads before `[DONE]`:
```text
data: {"error":{"code":"provider_error","message":"...","status_code":502}}

data: [DONE]
```

### RAG Behavior
- RAG is **deterministic**, not tool-based. Relevant chunks are automatically retrieved and injected into the system prompt before every chat request.
- Citations use `[S1]`, `[S2]` format. Each maps to a chunk with provenance metadata (page number, source document, etc.).
- No relevant chunks found → no RAG context injected. LLM answers from training data.
- Updating knowledge via `PATCH` triggers full re-indexing.

---

## Canonical Flow for Building an Integration

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

## Docker Deployment

Pre-built multi-arch image (amd64 + arm64):
```bash
docker pull ghcr.io/utsmannn/kirana:latest
```

Infrastructure (PostgreSQL/pgvector + Redis) via Docker Compose. App image runs the full stack (backend + frontend + entrypoint).

---

## Tech Stack

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
| Container | Docker multi-arch, ghcr.io |
