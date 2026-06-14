# Kirana API Reference

> **Target audience:** AI agents, LLM code generators, and external integrators building on top of Kirana.
> For a copy-paste setup/exploration prompt, start with [AI_AGENT_PROMPT.md](AI_AGENT_PROMPT.md).
> Use this file for the API contract, then read [TECH_DOC.md](TECH_DOC.md) for internals.

---

## Quick Orientation for AI Agents

Kirana is an AI chat platform with built-in RAG. It exposes a Kirana-native chat endpoint (`POST /v1/chat/send`) with OpenAI-compatible message format on top of a **Provider → Channel → Session** model.

**Architecture summary (read these files to understand):**

| File | What you'll learn |
|------|------------------|
| `app/api/v1/router.py` | All registered routes and their prefixes |
| `app/api/deps.py` | Every auth dependency and how they compose |
| `app/schemas/chat.py` | Chat request/response Pydantic models |
| `app/services/chat_service.py` | Chat orchestration logic (prompt building, RAG injection, LLM call) |
| `app/api/v1/knowledge.py` | Knowledge CRUD + file upload + RAG indexing pipeline |
| `app/services/rag_retrieval.py` | Vector search and context formatting |
| `app/config.py` | All settings with defaults (env vars → Pydantic Settings) |
| `app/core/security.py` | API key generation (SHA256 hashing) |

**Critical concepts:**
- A **Provider** is an AI API credential (OpenAI, Z.AI, or any OpenAI-compatible endpoint).
- A **Channel** binds a provider to a personality, system prompt, tools, and context guard. One provider → many channels.
- A **Session** is one conversation thread under a channel.
- **RAG is deterministic** — relevant knowledge chunks are injected into every chat request automatically. The LLM doesn't decide whether to search.

---

## Base URL

```
http://<host>:8000/v1
```

All endpoints return JSON. Streaming endpoints return SSE (`text/event-stream`).

---

## Authentication

Kirana has **4 auth methods**. All use `Authorization: Bearer <token>` unless otherwise noted.

### 1. Server API Key

- Token: value of `KIRANA_API_KEY` from `.env`
- Scope: **All endpoints**
- Usage: Admin scripts, internal services

```
Authorization: Bearer kirana-default-api-key-change-me
```

### 2. Admin Token

- Token: obtained from `POST /v1/admin/login`
- Scope: **All endpoints** (same as server API key)
- Lifespan: Rotates daily (SHA256 of `SECRET_KEY:ADMIN_PASSWORD:day_number`)
- Accepts yesterday's token for grace period

```
# Obtain token
curl -X POST http://localhost:8000/v1/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password": "admin"}'

# Use token
curl http://localhost:8000/v1/providers/ \
  -H "Authorization: Bearer <admin_token>"
```

### 3. Client API Key

- Token: obtained from `POST /v1/clients/` (one-time display)
- Storage: SHA256-hashed in database (`Client.api_key`)
- Scope: `/v1/clients/me`, `/v1/clients/me/regenerate-key`, chat, knowledge
- Also accepted as `?api_key=<key>` query parameter

```
# Register (no auth required)
curl -X POST http://localhost:8000/v1/clients/ \
  -H "Content-Type: application/json" \
  -d '{"name": "My App", "email": "dev@example.com"}'

# Use the returned api_key
curl http://localhost:8000/v1/clients/me \
  -H "Authorization: Bearer kir_xxxxxxxxxxxx"
```

### 4. Embed Token

- Token: generated per-channel in `Channel.embed_token`
- Scope: Chat only (per-channel isolation)
- Accepted as `?embed_token=<token>` query parameter
- Embed must be enabled on the channel (`Channel.embed_enabled = true`)

### Auth Dependency Map

| Dependency Function | Accepts | Used By |
|--------------------|---------|---------|
| `verify_api_key` | Server API key, Admin token | Admin endpoints, stream resume |
| `verify_api_key_optional` | Server API key, Admin token (header or query param) | Download endpoints (img/iframe-friendly) |
| `verify_api_key_or_admin_token` | Server API key, Admin token | CRUD endpoints (providers, channels, sessions, knowledge, config, tools, personalities) |
| `verify_api_key_or_embed_token` | Server API key, Embed token | Embed-specific endpoints |
| `verify_chat_auth` | Server API key, Admin token, Embed token, Public embed | Chat completions |
| `get_current_client` | Client API key (SHA256 lookup) | `/v1/clients/me`, `/v1/clients/me/regenerate-key` |

---

## Trailing Slash Convention

FastAPI enforces strict trailing slash behavior based on route definition:

| Route defined as | Access without `/` | Access with `/` |
|-----------------|-------------------|-----------------|
| `@router.get("/")` | **307 redirect** | ✅ 200 |
| `@router.post("/")` | **307 redirect** | ✅ 200/201 |
| `@router.get("/me")` | ✅ 200 | **307 redirect** |
| `@router.get("/{id}")` | ✅ 200 | **307 redirect** |

**AI agent rule:** Collection endpoints require trailing slash (`/providers/`, `/channels/`, `/sessions/`, `/knowledge/`, `/clients/`). Singular endpoints (`/me`, `/{id}`) must NOT have a trailing slash.

---

## Endpoints

### Health

#### `GET /health`
No auth required.

**Response `200`:**
```json
{
  "app": "kirana",
  "status": "ok",
  "database": "ok",
  "redis": "ok"
}
```

---

### Admin

#### `POST /v1/admin/login`
No auth required. Login to get an admin token.

**Request:**
```json
{
  "password": "admin"
}
```

**Response `200`:**
```json
{
  "token": "abc123def456..."
}
```

**Errors:** `401` — Invalid password.

#### `GET /v1/admin/verify`
Auth: `Authorization: Bearer <admin_token>`

**Response `200`:**
```json
{
  "valid": true
}
```

**Errors:** `401` — Missing or invalid/expired token.

#### `GET /v1/admin/config`
Auth: Admin token (via `Request.headers.authorization`)

Returns admin-level configuration including the admin password hash and secret key.

---

### Chat

#### `POST /v1/chat/send`
Auth: `verify_chat_auth` — accepts Server API key, Admin token, Embed token, or public embed (no auth if channel has `embed_enabled=true` and `embed_config.public=true`).

Kirana's primary chat endpoint — uses OpenAI-compatible request/response format. This is the **primary API surface**.

**Request body (`ChatCompletionRequest`):**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `messages` | `[{role, content}]` | **Yes** | — | OpenAI-format message array |
| `model` | string | No | `"default"` | Ignored (provider model used instead) |
| `stream` | bool | No | `false` | Enable SSE streaming |
| `temperature` | float | No | `0.7` | 0.0 – 2.0 |
| `max_tokens` | int | No | `null` | 1 – 128000 |
| `top_p` | float | No | `1.0` | 0.0 – 1.0 |
| `presence_penalty` | float | No | `0.0` | -2.0 – 2.0 |
| `frequency_penalty` | float | No | `0.0` | -2.0 – 2.0 |
| `tools` | string or array | No | `null` | Tool definitions or `"all"` for all registered tools |
| `tool_choice` | string or object | No | `"auto"` | Tool selection strategy |
| `channel_id` | UUID | Recommended | `null` | Channel to use. Pass this explicitly to select the intended provider/personality. |
| `session_id` | UUID | No | `null` | For persistent conversations |
| `visitor_id` | string | No | `null` | Embed widget visitor tracking |
| `stream_id` | string | No | `null` | Resume a buffered stream |
| `kirana` | object | No | `null` | Kirana-specific extensions |

**Non-streaming response `200` (`ChatCompletionResponse`):**
```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "gpt-4o-mini",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 10,
    "total_tokens": 110
  },
  "session": {
    "id": "...",
    "name": "..."
  }
}
```

**Streaming response `200`:** SSE (`text/event-stream`)
```
data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

**Auth errors:** `401` — Invalid/missing auth. `403` — Embed not enabled for channel.

**Provider/config errors:**
- `502 provider_config_error` — selected channel has inactive/missing provider, or no provider API key is configured.
- `502 provider_error` — upstream provider rejected the request or credentials.
- `429 provider_error` — upstream provider rate limit.
- `504 provider_error` — upstream provider timeout/connection failure.

For streaming requests, these are sent as SSE `error` payloads before `[DONE]`.

**What happens internally on each request:**
1. Auth verified
2. Channel resolved (from `channel_id` or default)
3. Provider credentials loaded from channel
4. System prompt built (personality + context guard + tool definitions)
5. **RAG context retrieved** (embeds user query → pgvector search → formats `[S1]`, `[S2]` citations)
6. RAG context injected into system prompt (deterministic, not tool-based)
7. LLM called via OpenAI SDK using channel's provider
8. Response returned or streamed

#### `GET /v1/chat/stream/{stream_id}?offset=0`
Auth: Server API key or Admin token.

Poll-based stream resume. Kirana buffers SSE chunks in memory. If a client disconnects mid-stream, it can resume from an offset.

**Response `200`:**
```json
{
  "stream_id": "abc-123",
  "chunks": ["Hello", " ", "world"],
  "offset": 0,
  "total": 3,
  "done": true
}
```

**Errors:** `404` — Stream not found or expired.

#### `WS /v1/chat/ws?channel_id=<uuid>&token=<api_key>`
WebSocket for real-time streaming chat. Auth via `token` query parameter (Server API key or Admin token).

---

### Providers

All endpoints auth: Server API key or Admin token.

#### `GET /v1/providers/`
List all providers ordered by priority.

**Response `200`:**
```json
{
  "providers": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "OpenAI",
      "model": "gpt-4o-mini",
      "base_url": null,
      "is_active": true,
      "is_default": false,
      "priority_order": 1,
      "created_at": "2025-01-01T00:00:00"
    }
  ],
  "active_provider": { "..." }
}
```

Note: `active_provider` is the first provider with `is_active=true` (lowest `priority_order`). `null` if none active.

#### `POST /v1/providers/`
Create a new provider credential.

**Request:**
```json
{
  "name": "My OpenAI",
  "model": "gpt-4o",
  "api_key": "sk-...",
  "base_url": null
}
```

`base_url` is optional. When omitted, defaults to OpenAI's production API.

**Response `201`:** Provider object (same shape as list item).

#### `GET /v1/providers/{provider_id}`
Get a single provider.

**Errors:** `404` — Not found.

#### `PATCH /v1/providers/{provider_id}`
Partial update. All fields optional.

**Errors:** `400` — Cannot modify default provider (created from `.env`). `404` — Not found.

#### `DELETE /v1/providers/{provider_id}`
**Errors:** `400` — Cannot delete default provider. `404` — Not found.

**Response:** `204 No Content`

#### `POST /v1/providers/{provider_id}/activate`
Set this provider as the active one (deactivates all others). Only one provider can be active at a time.

#### `POST /v1/providers/{provider_id}/reorder?new_order=<int>`
Change priority order (lower = higher priority). Used for provider fallback ordering.

---

### Channels

All endpoints auth: Server API key or Admin token (except `/embed/public` which has no auth).

#### `GET /v1/channels/`
List all channels with their provider names.

**Response `200`:**
```json
{
  "channels": [
    {
      "id": "550e8400-...",
      "name": "Support Bot",
      "provider_id": "660e8400-...",
      "provider_name": "OpenAI",
      "system_prompt": "You are a helpful support agent.",
      "personality_name": null,
      "context": "Acme Corp",
      "context_description": "You answer questions about Acme Corp products.",
      "is_default": true,
      "created_at": "2025-01-01T00:00:00",
      "embed_enabled": false,
      "embed_config": null
    }
  ],
  "default_channel": { "..." }
}
```

#### `POST /v1/channels/`
Create a channel. Must reference an existing provider.

**Request:**
```json
{
  "name": "Support Bot",
  "provider_id": "660e8400-...",
  "system_prompt": "You are a helpful support agent.",
  "personality_name": null,
  "context": "Acme Corp",
  "context_description": "You answer questions about Acme Corp products."
}
```

All fields except `name` and `provider_id` are optional.

**Errors:** `404` — Provider not found.

#### `GET /v1/channels/{channel_id}`
Get channel with provider name.

#### `PATCH /v1/channels/{channel_id}`
Partial update. All fields optional.

#### `DELETE /v1/channels/{channel_id}`
**Errors:** `400` — Cannot delete default channel. `404` — Not found.

#### `POST /v1/channels/{channel_id}/set-default`
Make this channel the default (unsets all others).

#### MCP Server Configuration

MCP servers are configured per channel. A channel can have multiple active MCP servers; Kirana discovers tools from all active servers for that channel at chat-request time.

Supported transports:
- `sse` — legacy MCP SSE endpoint
- `http` — MCP Streamable HTTP endpoint
- `stdio` — local MCP child process launched by the backend

Supported auth types:
- `none` — no extra auth headers
- `bearer` — pass `Authorization: Bearer <token>` from `auth_config.token` for remote transports
- `custom_header` — pass headers from `auth_config.headers` for remote transports

`server_url` is required for `sse`/`http` and must use `http://` or `https://`. For `stdio`, use `server_config` instead:

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-everything"],
  "env": {},
  "cwd": null
}
```

`auth_config` and `server_config` are write-only. Responses expose `auth_configured: boolean` and `server_configured: boolean`, and never return raw credentials, command env, or server config.

##### `GET /v1/channels/{channel_id}/mcp-servers/`
List MCP servers configured for a channel.

**Response `200`:**
```json
[
  {
    "id": "770e8400-...",
    "channel_id": "550e8400-...",
    "name": "Database MCP",
    "server_url": "https://db.example.com/mcp",
    "transport": "http",
    "auth_type": "bearer",
    "auth_configured": true,
    "server_configured": false,
    "is_active": true,
    "created_at": "2026-06-15T00:00:00",
    "updated_at": "2026-06-15T00:00:00"
  }
]
```

##### `POST /v1/channels/{channel_id}/mcp-servers/`
Add an MCP server to a channel.

**Request:**
```json
{
  "name": "Database MCP",
  "server_url": "https://db.example.com/mcp",
  "transport": "http",
  "auth_type": "bearer",
  "auth_config": {
    "token": "secret-token"
  }
}
```

**Stdio request:**
```json
{
  "name": "Local Filesystem MCP",
  "transport": "stdio",
  "auth_type": "none",
  "server_config": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
    "env": {}
  }
}
```

**Response `201`:** MCP server object with `auth_configured` and `server_configured`, without raw `auth_config` or `server_config`.

**Errors:** `404` — Channel not found. `422` — Invalid URL, transport, auth type, stdio config, or payload.

##### `GET /v1/channels/{channel_id}/mcp-servers/{server_id}`
Get a single MCP server configuration.

##### `PATCH /v1/channels/{channel_id}/mcp-servers/{server_id}`
Partial update. All fields are optional: `name`, `server_url`, `transport`, `auth_type`, `auth_config`, `server_config`, `is_active`. Omit `auth_config` or `server_config` to preserve the existing stored value.

##### `DELETE /v1/channels/{channel_id}/mcp-servers/{server_id}`
Delete an MCP server configuration. Returns `204`.

##### `POST /v1/channels/{channel_id}/mcp-servers/{server_id}/activate`
Activate an MCP server. Active servers are included in channel tool discovery.

##### `POST /v1/channels/{channel_id}/mcp-servers/{server_id}/deactivate`
Deactivate an MCP server. Inactive servers remain configured but are skipped during chat tool discovery.

##### `POST /v1/channels/{channel_id}/mcp-servers/{server_id}/test`
Connect to the MCP server and list discovered tools without changing channel state.

**Response `200`:**
```json
{
  "success": true,
  "message": "Connected successfully",
  "tools": [
    {
      "name": "query_database",
      "description": "Run a read-only database query",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": { "type": "string" }
        }
      }
    }
  ]
}
```

#### Embed Configuration

##### `POST /v1/channels/{channel_id}/embed`
Enable/configure embed widget for a channel.

**Request (`EmbedConfigUpdate`):**
```json
{
  "public": true,
  "save_history": true,
  "stream_mode": true,
  "regenerate_token": false,
  "header_title": "Chat with us",
  "theme": "dark",
  "primary_color": "#6366f1",
  "bg_color": null,
  "text_color": null,
  "font_family": null,
  "google_fonts_url": null,
  "bubble_style": "rounded",
  "custom_css_url": null
}
```

**Response `200`:**
```json
{
  "embed_enabled": true,
  "embed_url": "/embed/550e8400-...?theme=dark",
  "public": true,
  "save_history": true,
  "stream_mode": true,
  "has_token": true,
  "header_title": "Chat with us",
  "theme": "dark",
  "primary_color": "#6366f1",
  "bg_color": null,
  "text_color": null,
  "font_family": null,
  "google_fonts_url": null,
  "bubble_style": "rounded",
  "custom_css_url": null
}
```

If `regenerate_token` is `true` (or no token exists yet), a new `embed_token` is generated.

##### `GET /v1/channels/{channel_id}/embed`
Get embed config (auth required). Returns same shape as POST response.

##### `GET /v1/channels/{channel_id}/embed/public`
**No auth required.** Returns only safe, non-sensitive embed config for the widget to consume.

```json
{
  "save_history": true,
  "header_title": "Chat with us",
  "theme": "dark",
  "primary_color": "#6366f1",
  "bg_color": null,
  "text_color": null,
  "font_family": null,
  "google_fonts_url": null,
  "bubble_style": "rounded",
  "custom_css_url": null
}
```

**Errors:** `403` — Embed not enabled for this channel. `404` — Channel not found.

##### `DELETE /v1/channels/{channel_id}/embed`
Disable embed. Keeps the token for future re-enable. Returns `204`.

#### Brand Style Extraction

##### `POST /v1/channels/extract-brand-style`
Extract brand colors and font from a website URL. Uses Jina.ai for screenshot capture + Z.AI Vision for analysis.

**Request:**
```json
{
  "url": "https://example.com"
}
```

**Response `200`:**
```json
{
  "success": true,
  "primary_color": "#1a73e8",
  "secondary_color": "#ea4335",
  "bg_color": "#ffffff",
  "text_color": "#202124",
  "font_family": "Roboto",
  "google_fonts_name": "Roboto",
  "google_fonts_url": "https://fonts.googleapis.com/css2?family=Roboto",
  "error": null
}
```

##### `GET /v1/channels/fonts?q=<query>&limit=20`
Search Google Fonts by name. Returns matching font names.

---

### Sessions

All endpoints auth: Server API key or Admin token.

#### `POST /v1/sessions/`
Create a new chat session.

**Request:**
```json
{
  "name": "My Chat",
  "channel_id": "550e8400-...",
  "metadata": {}
}
```

`channel_id` is optional — if omitted, the default channel is used.

**Response `201`:** Session object.

#### `GET /v1/sessions/?page=1&limit=20&is_active=true`
Paginated list of sessions. `is_active` filter is optional.

**Response `200`:**
```json
{
  "items": [ { "...session..." } ],
  "total": 42,
  "page": 1,
  "limit": 20,
  "pages": 3
}
```

#### `GET /v1/sessions/{session_id}`
Get single session.

#### `PATCH /v1/sessions/{session_id}`
Partial update. Supports `name`, `is_active`, `metadata`.

#### `DELETE /v1/sessions/{session_id}`
Soft-delete (sets `is_active=false`). Returns `204`.

#### `GET /v1/sessions/{session_id}/messages?page=1&limit=50`
Get conversation history for a session. Messages are ordered by `created_at` ascending.

**Response `200`:**
```json
{
  "session_id": "550e8400-...",
  "messages": [
    {
      "id": "...",
      "role": "user",
      "content": "Hello",
      "created_at": "2025-01-01T00:00:00"
    },
    {
      "id": "...",
      "role": "assistant",
      "content": "Hi! How can I help?",
      "created_at": "2025-01-01T00:00:01"
    }
  ],
  "total": 2,
  "page": 1,
  "limit": 50
}
```

---

### Knowledge Base (RAG)

All endpoints auth: Server API key or Admin token.

#### `POST /v1/knowledge/`
Create a text knowledge item. Triggers chunking → embedding → pgvector indexing.

**Request (`KnowledgeCreate`):**
```json
{
  "title": "FAQ",
  "content": "Our return policy is 30 days...",
  "content_type": "text",
  "source_type": "manual",
  "source_url": null,
  "is_active": true,
  "metadata": {}
}
```

**Response `201`:** Knowledge object with `id`.

#### `GET /v1/knowledge/?page=1&limit=20&search=<query>&is_active=true&source_type=<type>`
Paginated list with optional search and filters.

#### `GET /v1/knowledge/{knowledge_id}`
Get single knowledge item.

#### `PATCH /v1/knowledge/{knowledge_id}`
Partial update. Changing `title` or `content` triggers **re-indexing** (delete old chunks → re-chunk → re-embed → re-store).

#### `DELETE /v1/knowledge/{knowledge_id}`
Deletes knowledge item + all associated chunks (cascade). Also deletes the uploaded file from disk if present. Returns `204`.

#### `POST /v1/knowledge/upload`
Upload a file for RAG processing. Multipart form data.

**Request:** `multipart/form-data`
- `file`: The file (required)
- `title`: Display title (optional, defaults to filename)

**This endpoint is fire-and-forget.** It returns immediately with `processing_status: "processing"`. Heavy work (parsing, chunking, embedding, indexing) runs in the background. Poll `GET /v1/knowledge/{id}` until `processing_status` becomes `"ready"` or `"failed"`.

**Processing pipeline (runs in background):**
1. File saved to `UPLOAD_DIR/knowledge/<uuid>_<ext>`
2. **LiteParse** (for PDF, DOCX): Smart OCR parsing with page/bbox metadata
3. Fallback to **FileProcessor** or **Vision API** if LiteParse fails
4. Optional AI analysis/summarization via configured LLM
5. Text stored in `Knowledge.content`
6. **Chunking** (tiktoken cl100k_base, 800 tokens, 120 overlap)
7. **Embedding** (FastEmbed, 384-dim, batch size 32)
8. **pgvector insert** with HNSW index
9. Status updated to `"ready"` — document is now queryable via RAG

**Supported formats:**

| Format | Extensions | Parser | Notes |
|--------|-----------|--------|-------|
| PDF | `.pdf` | LiteParse (OCR) | Falls back to text extraction + Vision API |
| Word | `.docx` | LiteParse | `.doc` NOT supported (convert first) |
| Excel | `.xlsx` | Vision API | Sheet-by-sheet image analysis |
| PowerPoint | `.pptx` | Text extraction | AI summary appended |
| Text/CSV/Markdown | `.txt`, `.csv`, `.md`, `.json` | Direct | No parsing needed |
| Images | `.png`, `.jpg`, `.jpeg` | Vision API | OCR + description |

**Response `201` (immediate — processing not yet complete):**
```json
{
  "id": "550e8400-...",
  "title": "handbook.pdf",
  "content": "",
  "content_type": "pdf",
  "source_type": "upload",
  "file_path": "/app/uploads/knowledge/abc123_handbook.pdf",
  "file_name": "handbook.pdf",
  "file_size": 1024000,
  "mime_type": "application/pdf",
  "is_active": true,
  "processing_status": "processing",
  "metadata": {
    "original_filename": "handbook.pdf",
    "mime_type": "application/pdf",
    "file_size": 1024000
  },
  "has_file": true,
  "created_at": "2025-01-01T00:00:00"
}
```

**Response `200` from `GET /v1/knowledge/{id}` after processing completes:**
```json
{
  "id": "550e8400-...",
  "title": "handbook.pdf",
  "content": "## Summary\nThis handbook covers...\n\n---\n\n## Original Document\n\nFull extracted text...",
  "content_type": "pdf",
  "source_type": "upload",
  "file_path": "/app/uploads/knowledge/abc123_handbook.pdf",
  "file_name": "handbook.pdf",
  "file_size": 1024000,
  "mime_type": "application/pdf",
  "is_active": true,
  "processing_status": "ready",
  "metadata": {
    "analysis_method": "liteparse_ai_analyze",
    "analysis_success": true,
    "parser": "liteparse",
    "pages": 42,
    "extracted_length": 45210,
    "original_filename": "handbook.pdf"
  },
  "has_file": true,
  "created_at": "2025-01-01T00:00:00"
}
```

**Polling pattern (recommended):**
```
POST /v1/knowledge/upload  →  201 { processing_status: "processing" }
loop:
  GET /v1/knowledge/{id}   →  check processing_status
  if "ready"   → done, content + chunks available
  if "failed"  → check metadata.processing_error
  if "processing" → wait 2-3s, poll again
```

**Processing status values:**

| Status | Meaning | What to do |
|--------|---------|------------|
| `"processing"` | Background worker is parsing/indexing | Poll again in 2-3 seconds |
| `"ready"` | Document is fully indexed | Chunks are queryable via RAG |
| `"failed"` | Processing error | Read `metadata.processing_error` for the failure reason |

**Errors:** `400` — File too large (max 50MB) or unsupported type.

#### `POST /v1/knowledge/scrape-web`
Scrape a single URL into knowledge.

**Request:**
```json
{
  "url": "https://example.com/page",
  "title": "Optional Title"
}
```

**Response `200`:** Knowledge object (same shape as upload).

#### `POST /v1/knowledge/crawl-web`
Crawl an entire website (same domain only).

**Request:**
```json
{
  "url": "https://example.com",
  "max_pages": 10
}
```

**Response `200`:** Knowledge object with combined crawl content.

#### `GET /v1/knowledge/{knowledge_id}/download`
Auth: Server API key or Admin token (via `verify_api_key_optional` — header or `?api_key=` query param).

Download the original uploaded file. Returns `FileResponse` with appropriate content type.

**Errors:** `404` — Knowledge not found or no file attached.

---

### Clients (External API Consumers)

#### `POST /v1/clients/`
**No auth required.** Register as an external API consumer.

**Request:**
```json
{
  "name": "My App",
  "email": "dev@example.com"
}
```

**Response `201`:**
```json
{
  "id": "550e8400-...",
  "name": "My App",
  "email": "dev@example.com",
  "api_key": "kir_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "api_key_prefix": "kir_xxxx",
  "is_active": true,
  "created_at": "2025-01-01T00:00:00",
  "config": {
    "ai_name": null,
    "personality": "helpful-assistant",
    "thinking_mode": false,
    "model": "gpt-4o-mini",
    "tools_enabled": true
  }
}
```

**⚠️ IMPORTANT:** The `api_key` is shown **only once**. The server stores only its SHA256 hash. If lost, the client must regenerate (old key becomes invalid).

What happens internally:
1. Generates raw API key (`kir_` + 32 random chars)
2. SHA256-hashes the raw key → stored in `Client.api_key`
3. Prefix saved in `Client.api_key_prefix` (for display)
4. Default `ClientConfig` created with `helpful-assistant` personality
5. Returns raw key in response (one time only)

**Errors:** `400` — Email already registered.

#### `GET /v1/clients/me`
Auth: Client API key (via `get_current_client`).

Returns the authenticated client's profile.

#### `POST /v1/clients/me/regenerate-key`
Auth: Client API key.

Generates a new API key. **Old key is immediately invalidated.**

**Response `200`:**
```json
{
  "api_key": "kir_newxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "api_key_prefix": "kir_newx",
  "message": "New API key generated. Old key is now invalid."
}
```

---

### Config

Auth: Server API key or Admin token.

#### `GET /v1/config/`
Get active provider configuration (what the chat service will use).

**Response `200`:**
```json
{
  "provider": {
    "id": "550e8400-...",
    "name": "OpenAI",
    "model": "gpt-4o-mini",
    "base_url": null,
    "is_default": false
  },
  "timeout": 60,
  "max_retries": 3
}
```

If no provider is active, falls back to `.env` values (`DEFAULT_MODEL`, `OPENAI_BASE_URL`).

#### `PATCH /v1/config/`
Legacy endpoint. Returns a message directing to use `/v1/providers` API instead.

#### `PUT /v1/config/personality`
Legacy endpoint. Directs to use `/v1/providers` API.

---

### Personalities

Auth: Server API key or Admin token.

#### `GET /v1/personalities/`
List all personality templates.

```json
{
  "templates": [
    {
      "id": "...",
      "name": "Helpful Assistant",
      "slug": "helpful-assistant",
      "description": "A general-purpose helpful assistant",
      "system_prompt": "You are a helpful assistant...",
      "is_template": true
    }
  ]
}
```

#### `GET /v1/personalities/{slug}`
Get a specific personality template by slug.

**Errors:** `404` — Not found.

---

### Tools

Auth: Server API key or Admin token.

#### `GET /v1/tools/`
List user-facing tools (excludes internal-only tools).

```json
{
  "tools": [
    {
      "name": "query_knowledge",
      "description": "Search the knowledge base for relevant information"
    },
    {
      "name": "get_current_datetime",
      "description": "Get the current date and time"
    }
  ]
}
```

#### `POST /v1/tools/execute`
Execute a tool directly (without going through chat).

**Request:**
```json
{
  "tool": "query_knowledge",
  "arguments": {
    "query": "return policy"
  }
}
```

**Errors:** `404` — Tool not found. `400` — Invalid arguments.

---

### Usage

Auth: Server API key or Admin token.

#### `GET /v1/usage/`
Usage statistics endpoint. Returns token usage, request counts, etc.

---

## Canonical Flows

### Flow 1: External Client Integration

```
1. POST /v1/clients/              → get api_key (save it)
2. GET  /v1/channels/             → choose channel_id
3. POST /v1/sessions/             → create session with channel_id
4. POST /v1/chat/send             → chat with channel_id and session_id
5. GET  /v1/sessions/{id}/messages → retrieve history
```

### Flow 2: Knowledge → RAG → Chat

```
1. POST /v1/knowledge/upload     → returns immediately (201, processing_status: "processing")
2. GET  /v1/knowledge/{id}       → poll until processing_status is "ready"
3. POST /v1/chat/send            → ask question with channel_id (RAG automatically injects relevant chunks)
4. Response includes [S1], [S2] citations
```

### Flow 3: Admin Setup

```
1. POST /v1/admin/login         → get admin token
2. POST /v1/providers/          → add AI provider credential
3. POST /v1/providers/{id}/activate → activate it
4. POST /v1/channels/           → create channel linked to provider
5. POST /v1/channels/{id}/set-default → make it default (optional)
6. POST /v1/channels/{id}/embed → configure embed widget (optional)
```

### Flow 4: Embed Widget

```
1. POST /v1/channels/{id}/embed  → enable embed, get embed_url
2. GET  /v1/channels/{id}/embed/public → widget fetches config (no auth)
3. POST /v1/chat/send?embed_token=... → widget chats
```

---

## Error Response Format

Most errors follow this simple format:

```json
{
  "detail": "Human-readable error message"
}
```

Provider/chat errors can return structured details so clients can show actionable UI messages:

```json
{
  "detail": {
    "code": "provider_error",
    "message": "AI provider authentication failed. Check the provider API key.",
    "provider_error_type": "AuthenticationError",
    "provider_message": "...raw provider/SDK message...",
    "model": "gpt-4o-mini"
  }
}
```

Streaming chat sends provider errors as SSE payloads before `[DONE]`:

```text
data: {"error":{"code":"provider_error","message":"AI provider returned an error.","status_code":502}}

data: [DONE]
```

Common HTTP status codes:

| Status | Meaning |
|--------|---------|
| `200` | Success |
| `201` | Created |
| `204` | No Content (successful delete) |
| `307` | Temporary Redirect (trailing slash mismatch) |
| `400` | Bad Request (validation error, cannot delete default, email already registered) |
| `401` | Unauthorized (missing/invalid auth) |
| `403` | Forbidden (embed not enabled, insufficient scope) |
| `404` | Not Found |
| `422` | Validation Error (Pydantic schema mismatch) |
| `429` | Rate Limit Exceeded (Kirana or upstream provider) |
| `500` | Internal Server Error |
| `502` | AI provider/configuration error |
| `504` | AI provider timeout or unreachable |

### Provider Error Codes

| Code | Status | Meaning | Recommended client behavior |
|------|--------|---------|-----------------------------|
| `provider_config_error` | `502` | No provider API key configured, or the selected channel points to an inactive/missing provider | Show an admin-facing configuration message; do not retry blindly |
| `provider_error` | `502` | Upstream provider returned a generic API error | Show provider message if useful; suggest checking provider settings |
| `provider_error` + `AuthenticationError` | `502` | Upstream provider rejected the API key | Ask admin to update provider credentials |
| `provider_error` + `BadRequestError` | `502` | Provider rejected the model/request parameters | Ask admin to check selected model and provider compatibility |
| `provider_error` + `RateLimitError` | `429` | Upstream provider rate limited the request | Retry later/backoff |
| `provider_error` + `APITimeoutError`/`APIConnectionError` | `504` | Provider is unreachable or timed out | Retry with backoff; check base URL/network |

Kirana intentionally does **not** silently fallback to `.env` when a selected channel has an invalid provider. This prevents confusing responses from the wrong model/provider.

---

## Rate Limiting

When `RATE_LIMIT_ENABLED=true`, requests are limited per client IP:
- Default: 60 requests/minute
- Configurable via `RATE_LIMIT_REQUESTS_PER_MINUTE`
- Returns `429` when exceeded

---

## Idempotency

- **Knowledge upload:** `POST /v1/knowledge/upload` is **fire-and-forget** — returns `201` with `processing_status: "processing"`. Heavy work runs async. Poll `GET /v1/knowledge/{id}` for completion. Repeated uploads of the same file create duplicate items.
- **Knowledge updates:** `PATCH` triggers re-indexing each time (delete old chunks + re-chunk + re-embed). Avoid unnecessary updates.
- **Client registration:** `POST /v1/clients/` is idempotent by email — returns `400` if email already registered.
- **Channel/provider CRUD:** Standard REST semantics. `PUT` not supported; use `PATCH` for partial updates.

---

## Session Lifecycle

- Sessions auto-expire after `SESSION_EXPIRY_DAYS` (default 3) of inactivity
- Expired sessions are soft-deleted after `SESSION_DELETION_DAYS` (default 7)
- Cleanup runs every `SESSION_CLEANUP_INTERVAL_HOURS` (default 1)
- Embed visitor sessions: named `Embed - {visitor_id}`, keyed by localStorage `visitor_id`

---

## RAG Behavior Notes for AI Agents

- **RAG is deterministic, not tool-based.** The system always retrieves and injects relevant chunks before every chat request. The LLM does not decide whether to search.
- **The `query_knowledge` tool** is an additional explicit search path, not the primary RAG mechanism.
- **Retrieval query** is built from the latest user message + optional channel context.
- **Results are bounded:** Top-10 chunks, max 12,000 characters total.
- **Citations** use `[S1]`, `[S2]` format. Each citation maps to a specific chunk with provenance (page number, bbox coordinates, source document).
- **If no relevant chunks found:** No RAG context is injected. The LLM answers from its training data.
- **Re-indexing:** Updating knowledge content/title via `PATCH` triggers full re-indexing. The old chunks are deleted first, then new ones created.
- **Backfill:** Knowledge items created before the pgvector migration need `python scripts/backfill_knowledge_chunks.py --only-active`.

---

## Environment Variables

See `.env.example` for the complete list. Key variables for API consumers:

| Variable | Default | Description |
|----------|---------|-------------|
| `KIRANA_API_KEY` | `kirana-default-api-key-change-me` | Server API key |
| `ADMIN_PASSWORD` | `admin` | Admin login password |
| `DEFAULT_MODEL` | `gpt-4o-mini` | Fallback model |
| `RAG_ENABLED` | `true` | Enable/disable RAG |
| `RAG_TOP_K` | `10` | Chunks retrieved per query |
| `RAG_MAX_CONTEXT_CHARS` | `12000` | Max context injected |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Rate limit threshold |

---

## Files Reference for AI Agents

When analyzing this codebase, read files in this order:

1. **`app/main.py`** — FastAPI app factory, middleware, lifespan events
2. **`app/api/v1/router.py`** — All routes and prefixes (single source of truth)
3. **`app/api/deps.py`** — All auth dependency functions
4. **`app/schemas/chat.py`** — Chat request/response models
5. **`app/api/v1/chat.py`** — Chat endpoint implementation
6. **`app/services/chat_service.py`** — Chat orchestration (prompt building, RAG injection, LLM call)
7. **`app/api/v1/knowledge.py`** — Knowledge CRUD + upload pipeline
8. **`app/services/rag_retrieval.py`** — Vector search + context formatting
9. **`app/services/rag_ingestion.py`** — Parse → chunk → embed → store pipeline
10. **`app/config.py`** — All settings with defaults
11. **`app/core/security.py`** — API key generation/hashing
12. **`app/models/`** — SQLAlchemy ORM models (database truth)
13. **`docs/TECH_DOC.md`** — Deep technical reference (architecture, internals, deployment)
