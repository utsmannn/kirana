# Kirana — Technical Reference

**Comprehensive developer documentation.** Covers architecture internals, RAG pipeline, database schema, deployment, and advanced configuration.

> For getting started and architecture overview, see [README.md](../README.md).
> For the complete API contract (endpoints, auth, schemas), see [API_REFERENCE.md](API_REFERENCE.md).

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [RAG Pipeline](#2-rag-pipeline)
3. [Database Schema](#3-database-schema)
4. [Authentication & Security](#4-authentication--security)
5. [Chat Service Internals](#5-chat-service-internals)
6. [Knowledge Ingestion](#6-knowledge-ingestion)
7. [Tool System](#7-tool-system)
8. [MCP Integration](#8-mcp-integration)
9. [Background Tasks](#9-background-tasks)
10. [Error Handling](#10-error-handling)
11. [Rate Limiting](#11-rate-limiting)
12. [Deployment](#12-deployment)
13. [Local Development](#13-local-development)

---

## 1. Architecture

### 1.1 Request Flow

```mermaid
flowchart TD
    HTTP[HTTP Request] --> Router
    Router[FastAPI Router<br/>Route matching /v1/...] --> Auth
    Auth[Auth Dependency<br/>Bearer token → API key / admin / client key / embed token] --> RL
    RL[Rate Limiter<br/>Redis-backed sliding window] --> Logic
    Logic[Endpoint Logic<br/>CRUD / chat / upload / etc.] --> DB
    DB[(AsyncSession<br/>PostgreSQL via SQLAlchemy<br/>+ Redis)]
```

### 1.2 Component Diagram

```mermaid
flowchart TB
    subgraph API[API Layer]
        Admin[Admin Panel]
        Chat[Chat API<br/>REST + WS]
        Knowledge[Knowledge API]
        Embed[Embed Widget<br/>iframe + SSE]
    end

    subgraph Core[Core Services]
        CS[Chat Service]
        subgraph CS_Internals[Chat Service Internals]
            SP[System Prompt Builder]
            RI[RAG Injection]
            PR[Provider Resolver]
            SB[Stream Buffer]
        end
        CS --- CS_Internals
    end

    subgraph RAG[RAG Services]
        LP[LiteParse Parser]
        CK[Chunking<br/>tiktoken]
        EM[Embedding<br/>FastEmbed 384d]
        RV[Retrieval<br/>pgvector cosine]
    end

    subgraph Infra[Infrastructure]
        SM[Session Manager]
        TR[Tool Registry]
        FP[File Processor]
        MC[MCP Client]
    end

    API --> Core
    Core --> RAG
    Core --> Infra
```

### 1.3 Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **API Framework** | FastAPI | 0.115+ | Async HTTP, OpenAPI auto-docs |
| **ASGI Server** | Uvicorn | 0.34+ | Production ASGI server |
| **ORM** | SQLAlchemy | 2.0+ | Async ORM with PostgreSQL |
| **Vector DB** | pgvector | 0.8+ | HNSW vector index, cosine distance |
| **Migrations** | Alembic | 1.15+ | Schema versioning |
| **Cache** | Redis | 7.x | Rate limiting, session cache |
| **LLM Client** | OpenAI SDK | 1.x | Direct API calls (no wrapper) |
| **Embeddings** | FastEmbed | 0.8+ | Local embedding model (384-dim) |
| **Chunking** | tiktoken | 0.9+ | cl100k_base tokenizer |
| **Parsing** | LiteParse | 0.1+ | Smart + OCR document parsing |
| **Frontend** | SvelteKit | 2.x | Admin panel SPA |
| **Container** | Docker | — | Multi-arch (amd64, arm64) |

---

## 2. RAG Pipeline

### 2.1 Architecture

Kirana uses **deterministic RAG**, not tool-based. The knowledge retrieval happens automatically before every chat completion — the LLM doesn't decide whether to search.

**Write path — Knowledge ingestion:**

```mermaid
flowchart TD
    UP[Document Upload] --> FS[File Saved<br/>→ /uploads/knowledge/uuid.ext]
    FS --> PA

    subgraph PA[Parse]
        LP[LiteParse — PDF/DOCX → ParsedDocument]
        DR[Direct read — TXT/CSV/MD/JSON]
        FB[FileProcessor — legacy fallback]
    end

    PA --> CH

    subgraph CH[Chunk — tiktoken cl100k_base]
        SP[Split by paragraphs]
        TK[800 tokens max per chunk]
        OV[120 tokens overlap]
        PV[Preserve page/bbox/font metadata]
    end

    CH --> RC[List of RagChunk<br/>text + provenance metadata]

    subgraph EM[Embed — FastEmbed async asyncio.to_thread]
        FE[Model: paraphrase-multilingual-MiniLM-L12-v2]
        DIM[Dimension: 384]
        BAT[Batch: 32 texts at a time]
    end

    RC --> EM

    subgraph ST[Store — INSERT INTO knowledge_chunks]
        TXT[text, chunk_index, token_count]
        VEC[embedding VECTOR 384]
        META[extra_metadata JSONB — provenance]
    end

    EM --> ST
```

**Read path — Knowledge retrieval at query time:**

```mermaid
flowchart TD
    UM[User Message<br/>latest in chat] --> BQ

    BQ[Build Query<br/>Combine: user message +<br/>channel context + description] --> EQ

    EQ[Embed Query<br/>Same FastEmbed model, 384-dim] --> VS

    VS[Vector Search<br/>SELECT FROM knowledge_chunks<br/>JOIN knowledge — active rows only<br/>ORDER BY embedding <=> query_vector<br/>LIMIT RAG_TOP_K × 2 — oversample] --> DT

    DT[Deduplicate + Truncate<br/>One chunk per knowledge_id<br/>Cap to RAG_TOP_K — 10 chunks<br/>Cap to RAG_MAX_CONTEXT_CHARS — 12k] --> FC

    FC[Format Context<br/>[S1] Title + Source + Text<br/>[S2] Title + Source + Text] --> INJ

    INJ[Inject into System Prompt<br/>Appended before user messages<br/>'Use context as primary source. Cite [S1].']
```

### 2.2 Chunking Details

**Tokenizer:** `tiktoken.get_encoding("cl100k_base")` — the same tokenizer used by GPT-4 and GPT-3.5-turbo.

**Algorithm:**
1. Split input text by paragraphs (`\n\n`)
2. For each paragraph:
   - If it fits in `RAG_CHUNK_MAX_TOKENS` (800), use as-is
   - If not, split by sentences (`\n`)
   - If still too large, split by tokens at max boundary
3. Add overlap: each chunk starts `RAG_CHUNK_OVERLAP_TOKENS` (120) tokens before the previous chunk's end
4. Store provenance: `page`, `page_start`, `page_end`, `source_spans`, `bboxes`

**For LiteParse documents:**
- Chunks are built from `ParsedPage.text` with additional metadata:
  - `bbox_coordinate_system`: `"pdf_points"`
  - `extraction`: `{"parser": "liteparse", "parsing_status": "success", "coordinate_system": "pdf_points"}`
  - `page`, `page_start`, `page_end` per chunk

### 2.3 Embedding Model

**Model:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

- **Dimension:** 384
- **Languages:** 50+ (including Indonesian, English)
- **Max sequence:** 512 tokens
- **Performance:** ~200 texts/sec on CPU (batch inference)
- **Memory:** ~470MB loaded

**Startup preload:** The model is downloaded (if not cached) and loaded during app startup via a warmup call in `lifespan()`. This ensures the first user request doesn't block on a ~118MB download. The singleton `_get_model()` with `@lru_cache` ensures the model is reused for all subsequent embeddings. Embedding calls are wrapped in `asyncio.to_thread()` to avoid blocking the event loop.

### 2.4 Vector Search

**Index:** HNSW (Hierarchical Navigable Small World)
```sql
CREATE INDEX ix_knowledge_chunks_embedding_hnsw
ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
```

**Query:**
```python
distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
results = (
    select(KnowledgeChunk, Knowledge)
    .join(Knowledge, Knowledge.id == KnowledgeChunk.knowledge_id)
    .where(Knowledge.is_active == True)
    .order_by(distance)
    .limit(top_k * 2)
)
```

**Score normalization:** `score = 1 - cosine_distance` (range: 0 to 1, higher is better).

### 2.5 Context Injection Format

The retrieved context is formatted and injected into the system prompt:

```
## KNOWLEDGE BASE CONTEXT
Use the following context as your primary source when answering.
If information is not in the context, honestly say it is not available.
Cite [S1], [S2], etc. when relevant.

[S1] Employee Handbook — Section 3: Leave Policy
Source: knowledge/abc-123-def | Type: pdf | Page: 12
Employees are entitled to 12 days of paid leave per year.
Leave must be requested at least 2 weeks in advance.

[S2] Employee Handbook — Section 5: Remote Work
Source: knowledge/abc-123-def | Type: pdf | Page: 18
Remote work is available for employees who have completed
their 3-month probation period.
```

The LLM is also instructed:
- Always respond in the same language the user used in their query
- If context is insufficient, say so honestly
- Cite `[S1]`, `[S2]` when using knowledge base content

---

## 3. Database Schema

### 3.1 Entity Relationship

```mermaid
erDiagram
    clients ||--o| client_configs : "1:1"
    clients ||--o{ sessions : "1:N"
    clients ||--o{ knowledge : "1:N"
    clients ||--o{ conversation_logs : "1:N"
    clients ||--o{ usage_logs : "1:N"
    knowledge ||--o{ knowledge_chunks : "1:N"
    provider_credentials ||--o{ channels : "1:N"
    channels ||--o{ sessions : "1:N"
    sessions ||--o{ conversation_logs : "1:N"
    personalities {
        uuid id PK
        varchar name
        varchar slug "unique"
        text system_prompt
    }
```

### 3.2 Table Reference

#### `clients`
External API consumers. Each client gets a unique API key (SHA256-hashed).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `name` | VARCHAR(255) | Display name |
| `email` | VARCHAR(255) | Unique, indexed |
| `api_key` | VARCHAR(64) | SHA256 hash of raw key |
| `api_key_prefix` | VARCHAR(8) | First 8 chars for display (`kir_xxxx`) |
| `is_active` | BOOLEAN | Soft disable |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `client_configs`
Per-client configuration (1:1 with clients).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `client_id` | UUID FK | → clients.id |
| `ai_name` | VARCHAR | Custom AI name |
| `personality_id` | UUID FK | → personalities.id |
| `model` | VARCHAR | Default model override |
| `thinking_mode` | VARCHAR | `normal` / `extended` |
| `tools_enabled` | JSONB | Array of enabled tool names |

#### `provider_credentials`
LLM API provider configuration.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `name` | VARCHAR | e.g. "OpenAI", "Z.AI" |
| `api_key` | VARCHAR | Provider API key |
| `base_url` | VARCHAR | API base URL |
| `model` | VARCHAR | Default model |
| `is_active` | BOOLEAN | Enable/disable |
| `is_default` | BOOLEAN | Default provider |
| `priority_order` | INTEGER | Order for fallback |

#### `channels`
Use-case configurations. Each channel = provider + personality + tools + context guard.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `name` | VARCHAR(100) | Channel name |
| `provider_id` | UUID FK | → provider_credentials.id |
| `system_prompt` | TEXT | Custom system prompt |
| `personality_name` | VARCHAR(100) | Personality slug |
| `context` | VARCHAR(255) | Context guard name |
| `context_description` | TEXT | Context guard details |
| `is_default` | BOOLEAN | Default channel |
| `embed_enabled` | BOOLEAN | Embed widget on/off |
| `embed_token` | VARCHAR(64) | Embed auth token |
| `embed_config` | JSONB | `{save_history, public, theme, ...}` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `knowledge`
Knowledge base source documents.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `client_id` | UUID FK | → clients.id (nullable) |
| `title` | VARCHAR(500) | Document title |
| `content` | TEXT | Full text content |
| `content_type` | VARCHAR(50) | `text`, `pdf`, `docx`, `xlsx`, `pptx`, `image` |
| `source_type` | VARCHAR(20) | `manual`, `upload`, `scrape`, `crawl` |
| `source_url` | VARCHAR(1000) | Origin URL (for scraped content) |
| `is_active` | BOOLEAN | Soft delete |
| `has_file` | BOOLEAN | Whether file is attached |
| `file_name` | VARCHAR | Original filename |
| `file_path` | VARCHAR | Filesystem path |
| `file_size` | INTEGER | Bytes |
| `mime_type` | VARCHAR | MIME type |
| `extra_metadata` | JSONB | Parser provenance, OCR info |
| `embedding` | JSONB | Deprecated — kept for backward compat |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `knowledge_chunks` (RAG)
Derived chunk embeddings. One knowledge row → many chunks.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `knowledge_id` | UUID FK | → knowledge.id (CASCADE DELETE) |
| `client_id` | UUID FK | → clients.id (denormalized) |
| `title` | VARCHAR | Denormalized from knowledge |
| `text` | TEXT | Chunk text |
| `content_type` | VARCHAR | Denormalized |
| `source_type` | VARCHAR | Denormalized |
| `source_url` | VARCHAR | Denormalized |
| `chunk_index` | INTEGER | Position in document |
| `token_count` | INTEGER | Token count (cl100k_base) |
| **`embedding`** | **VECTOR(384)** | **pgvector embedding** |
| `extra_metadata` | JSONB | Page, bbox, parser provenance |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**Indexes:**
```sql
CREATE INDEX ix_knowledge_chunks_knowledge_id ON knowledge_chunks(knowledge_id);
CREATE INDEX ix_knowledge_chunks_client_id ON knowledge_chunks(client_id);
CREATE INDEX ix_knowledge_chunks_knowledge_chunk_index ON knowledge_chunks(knowledge_id, chunk_index);
CREATE INDEX ix_knowledge_chunks_embedding_hnsw ON knowledge_chunks
  USING hnsw (embedding vector_cosine_ops);
```

#### `sessions`
Chat sessions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `client_id` | UUID FK | → clients.id |
| `channel_id` | UUID FK | → channels.id |
| `title` | VARCHAR | Session name |
| `visitor_id` | VARCHAR | For embed sessions |
| `is_archived` | BOOLEAN | Auto-archived after inactivity |
| `last_activity` | TIMESTAMPTZ | Last message timestamp |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `conversation_logs`
Individual messages within sessions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `session_id` | UUID FK | → sessions.id |
| `client_id` | UUID FK | → clients.id |
| `role` | VARCHAR | `user`, `assistant`, `system`, `tool` |
| `content` | TEXT | Message content |
| `tool_calls` | JSONB | Tool call data |
| `tool_call_id` | VARCHAR | Tool call correlation ID |
| `tokens_used` | INTEGER | Token count if available |
| `created_at` | TIMESTAMPTZ | |

#### `personalities`
Reference personality templates.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `name` | VARCHAR | Display name |
| `slug` | VARCHAR | URL-safe identifier |
| `description` | TEXT | |
| `system_prompt` | TEXT | Default system prompt |
| `icon` | VARCHAR | Emoji/icon |
| `is_default` | BOOLEAN | |

---

## 4. Authentication & Security

### 4.1 Auth Methods

Kirana has four authentication methods. All use `Authorization: Bearer <token>`.

| # | Method | Token Source | Hash | Scope |
|---|--------|-------------|------|-------|
| 1 | **Server API Key** | `KIRANA_API_KEY` in `.env` | Plain comparison | Full access |
| 2 | **Admin Token** | `POST /v1/admin/login` | SHA256(secret:password:day) | Full access, rotates daily |
| 3 | **Client API Key** | `POST /v1/clients` (register) | SHA256 in DB | Per-client, own resources |
| 4 | **Embed Token** | Channel config | Plain comparison | Chat only, per channel |

### 4.2 Auth Flow Diagram

```mermaid
flowchart TD
    REQ[Request<br/>Authorization: Bearer token] --> E1{Is it a Channel<br/>embed_token?}
    E1 -->|Yes| AUTH1[Embed Auth<br/>Channel-scoped access]
    E1 -->|No| E2{Is it<br/>KIRANA_API_KEY?}
    E2 -->|Yes| AUTH2[Server API Key Auth<br/>Full access]
    E2 -->|No| E3{Is it a valid<br/>admin token?}
    E3 -->|Yes| AUTH3[Admin Auth<br/>Daily rotation<br/>Full access]
    E3 -->|No| E4{Is it a<br/>client API key?}
    E4 -->|Yes| AUTH4[Client Auth<br/>SHA256 lookup<br/>in clients table]
    E4 -->|No| ERR[401 Unauthorized]
```

### 4.3 Security Design Decisions

**Client API keys are hashed.** Raw key is shown only once at registration. The database stores `SHA256(raw_key)`. Verification hashes the incoming token and compares hashes.

**Admin tokens rotate daily.** Token = `SHA256(SECRET_KEY + ADMIN_PASSWORD + day_number)`. Yesterday's token is also accepted to prevent midnight logout. No token storage needed — stateless verification.

**Embed tokens are per-channel.** Each channel's embed has its own token. No cross-channel access. Chats via embed are scoped to that channel only.

**`register_client` is public (no auth).** This is intentional — allows open registration for external API consumers. Protect this behind a firewall or require admin approval if needed for production.

### 4.4 CORS

CORS origins are configurable via `CORS_ORIGINS` env var. Default: `*` (all origins). For production, set to your domain:
```env
CORS_ORIGINS=["https://myapp.com","https://admin.myapp.com"]
```

---

## 5. Chat Service Internals

### 5.1 Completion Flow

```python
# app/services/chat_service.py

class ChatService:
    async def create_chat_completion(self, request, auth_info, db):
        # 1. Prepare: resolve channel, build system prompt, retrieve RAG context
        completion_kwargs, session, channel_id, messages, client = (
            await self._prepare_completion(request, auth_info, db)
        )

        # 2. Call LLM
        if request.stream:
            return StreamingResponse(self._stream_response(...))
        else:
            response = await client.chat.completions.create(**completion_kwargs)
            await self._save_conversation(...)
            return formatted_response
```

### 5.2 Provider Resolution

```python
def _resolve_provider(request, channel, db):
    # Preferred path: explicit request.channel_id → Channel.provider_id → active ProviderCredential
    if channel:
        provider = await db.get(ProviderCredential, channel.provider_id)
        if not provider or not provider.is_active:
            raise provider_config_error(
                "The selected channel's AI provider is inactive or no longer exists."
            )
        return AsyncOpenAI(
            api_key=provider.api_key,
            base_url=provider.base_url,
        ), provider.model

    # Only used when no channel/session was provided/resolved.
    # This is a fallback for bare API calls, not for misconfigured channels.
    if not settings.OPENAI_API_KEY:
        raise provider_config_error("No AI provider API key is configured.")

    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    ), settings.DEFAULT_MODEL
```

Kirana intentionally does **not** fallback to `.env` when a selected channel has an inactive or missing provider. That would hide configuration errors and may route user chats to the wrong model. Provider/API failures are mapped to structured `provider_config_error` or `provider_error` responses.

### 5.3 System Prompt Assembly

The system prompt is assembled in this order:

```
1. Personality system_prompt (from personality template or channel)
2. Context guard instructions (if channel has context set)
3. Tool definitions (if tools enabled on channel)
4. RAG context (deterministic injection of knowledge chunks)
5. Language instruction ("respond in the same language as the user")
```

### 5.4 Streaming Implementation

```python
async def _stream_response(self, client, completion_kwargs, ...):
    stream_id = str(uuid.uuid4())
    buffer = StreamBuffer(stream_id)

    # First message: stream_id for client reference
    yield f"data: {json.dumps({'stream_id': stream_id})}\n\n"

    # Stream from OpenAI
    stream = await client.chat.completions.create(**completion_kwargs, stream=True)
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            buffer.append(delta.content)
            yield f"data: {json.dumps(chunk.model_dump())}\n\n"

    yield "data: [DONE]\n\n"
```

**Stream buffer:** Allows clients to reconnect and resume from where they left off. The buffer stores recent chunks keyed by `stream_id`. Clients can poll `GET /v1/chat/stream/{stream_id}?offset=N` to catch up.

---

## 6. Knowledge Ingestion

### 6.1 Upload Pipeline

```python
# app/api/v1/knowledge.py — upload_knowledge_file

async def upload_knowledge_file(file: UploadFile, title: str, auth, db):
    # 1. Save file to disk
    file_path = UPLOAD_DIR / "knowledge" / f"{uuid}.{ext}"
    content = await file.read()
    file_path.write_bytes(content)

    # 2. Determine MIME type
    mime_type = mimetypes.guess_type(file.filename)[0]

    # 3. Parse document
    parsed_doc = None
    extracted_text = None

    if mime_type in LITEPARSE_TYPES:
        # Try LiteParse smart parsing (OCR enabled)
        parsed_doc = _try_liteparse(file_path, mime_type)

    if not parsed_doc:
        # Fall back to legacy FileProcessor or direct read
        extracted_text = await _extract_text_legacy(file_path, mime_type)

    # 4. Create Knowledge row
    knowledge = Knowledge(
        title=title or file.filename,
        content=parsed_doc.full_text if parsed_doc else extracted_text,
        content_type=...,
        has_file=True,
        file_name=file.filename,
        file_path=str(file_path),
        file_size=len(content),
        mime_type=mime_type,
    )
    db.add(knowledge)
    await db.flush()

    # 5. Index chunks (RAG pipeline)
    from app.services.rag_ingestion import index_knowledge
    await index_knowledge(db, knowledge, parsed_document=parsed_doc)

    await db.commit()
    return knowledge
```

### 6.2 LiteParse Integration

```python
# app/services/liteparse_parser.py

def parse_document_smart(path: Path) -> ParsedDocument:
    """OCR-enabled parsing for PDFs and documents."""
    parser = LiteParse(
        ocr_enabled=True,
        ocr_language=settings.LITEPARSE_OCR_LANGUAGE,  # "ind"
        max_pages=settings.LITEPARSE_MAX_PAGES,        # 1000
        dpi=settings.LITEPARSE_DPI,                    # 150
    )
    result = parser.parse(path)
    return _normalize_result(result)

def parse_document_generic(path: Path) -> ParsedDocument:
    """Generic parsing without OCR (faster, for text-based PDFs)."""
    parser = LiteParse(
        ocr_enabled=False,
        max_pages=settings.LITEPARSE_MAX_PAGES,
    )
    result = parser.parse(path)
    return _normalize_result(result)
```

**ParsedDocument structure:**
```python
@dataclass
class ParsedTextItem:
    text: str
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    font_name: str | None
    font_size: float | None
    confidence: float | None

@dataclass
class ParsedPage:
    page_number: int
    width: float
    height: float
    text_items: list[ParsedTextItem]
    text: str  # Concatenated text_items

@dataclass
class ParsedDocument:
    pages: list[ParsedPage]
    full_text: str  # All pages concatenated
    page_count: int
    parser_metadata: dict
```

### 6.3 Indexing (Chunk + Embed + Store)

```python
# app/services/rag_ingestion.py

async def index_knowledge(db, knowledge, parsed_document=None):
    # 1. Delete existing chunks (idempotent)
    await db.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.knowledge_id == knowledge.id)
    )

    # 2. Chunk
    if parsed_document:
        chunks = chunk_document(parsed_document)
    else:
        chunks = chunk_text(knowledge.content)

    # 3. Embed (batched)
    texts = [c.text for c in chunks]
    embeddings = await embed_texts(texts)

    # 4. Store
    for chunk, embedding in zip(chunks, embeddings):
        db.add(KnowledgeChunk(
            knowledge_id=knowledge.id,
            client_id=knowledge.client_id,
            title=knowledge.title,
            text=chunk.text,
            content_type=knowledge.content_type,
            source_type=knowledge.source_type,
            source_url=knowledge.source_url,
            chunk_index=chunk.index,
            token_count=chunk.token_count,
            embedding=embedding,
            extra_metadata=chunk.metadata,
        ))

    await db.flush()
    return len(chunks)
```

### 6.4 Backfill

Existing knowledge rows created before the RAG migration don't have chunks. Use the backfill script:

```bash
# Backfill all active knowledge
python scripts/backfill_knowledge_chunks.py --only-active

# Backfill specific knowledge
python scripts/backfill_knowledge_chunks.py --knowledge-id <uuid>

# Backfill with file re-parsing (uses LiteParse if file exists)
python scripts/backfill_knowledge_chunks.py --only-active --reparse-files --limit 50
```

The script is idempotent — safe to re-run. It deletes existing chunks and recreates them.

---

## 7. Tool System

### 7.1 Architecture

Tools are Python classes extending `BaseTool`. Each tool defines:
- `name`: Unique identifier
- `description`: LLM-readable description
- `parameters`: JSON Schema for function calling
- `internal`: If True, hidden from user-facing tool lists
- `execute(**kwargs)`: Async method implementing the tool

```python
# app/tools/base.py
class BaseTool:
    internal: bool = False

    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def parameters(self) -> dict: ...
    async def execute(self, **kwargs) -> dict: ...
```

### 7.2 Available Tools

| Tool | Internal | Description |
|------|----------|-------------|
| `query_knowledge` | No | Vector search over knowledge base (pgvector-backed) |
| `get_current_datetime` | No | Get current time in specified timezone |
| `analyze_image` | **Yes** | Vision API image analysis (internal use only) |

### 7.3 Tool as OpenAI Function

Tools are converted to OpenAI function-calling format:

```python
def to_openai_function(self) -> dict:
    return {
        "type": "function",
        "function": {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        },
    }
```

When a channel has tools enabled, these function definitions are included in the system prompt and passed to the LLM as available tools.

### 7.4 `query_knowledge` — Vector-Backed

```python
# app/tools/knowledge_tool.py

async def execute(self, query: str, top_k: int = 5):
    result = await retrieve_context(
        db=self.db,
        query=query,
        top_k=top_k or settings.RAG_TOP_K,
    )
    return {
        "success": True,
        "results": [
            {
                "title": c.title,
                "text": c.text,
                "score": c.score,
                "citation": c.citation,
                "source_type": c.source_type,
            }
            for c in result.chunks
        ],
        "context": result.formatted_context,
    }
```

Unlike the old keyword-search implementation, this tool now uses the same pgvector retrieval pipeline as the deterministic RAG injection. Results are bounded and traceable.

---

## 8. MCP Integration

### 8.1 MCP Client

Kirana connects to Model Context Protocol (MCP) servers for extended capabilities:

```python
# app/services/mcp_client.py

class MCPManager:
    """Manages connections to MCP servers."""
    
    def get_available_servers(self) -> list[str]:
        """Returns list of connected server names."""
    
    async def call_tool(self, tool_name: str, arguments: dict, server_name: str):
        """Call a tool on an MCP server."""
```

### 8.2 Z.AI MCP Server

Currently used for:
- **Image analysis** (`analyze_image` tool via `image_analyzer_tool.py`)
- **Web search** (optional)

Configure via environment:
```env
ZAI_API_KEY=your-zai-api-key
```

---

## 9. Background Tasks

### 9.1 Session Cleanup

Runs periodically to clean up inactive sessions:

- **Expiry:** Sessions without activity for `SESSION_EXPIRY_DAYS` (3) are marked archived
- **Deletion:** Archived sessions older than `SESSION_DELETION_DAYS` (7) are deleted
- **Interval:** Runs every `SESSION_CLEANUP_INTERVAL_HOURS` (1)

### 9.2 Usage Logging

Every chat completion is logged to `usage_logs`:
- `client_id`
- `channel_id`
- `session_id`
- `tokens_used` (prompt + completion)
- `model`
- `timestamp`

Usage stats are available at `GET /v1/usage`.

---

## 10. Error Handling

### 10.1 HTTP Error Codes

| Code | When |
|------|------|
| **400** | Invalid request body, bad UUID format |
| **401** | Missing or invalid auth token |
| **403** | Valid auth but insufficient permissions (e.g., embed disabled) |
| **404** | Resource not found |
| **409** | Conflict (e.g., duplicate email, duplicate channel) |
| **422** | Validation error (Pydantic) |
| **429** | Rate limit exceeded (Kirana or upstream provider) |
| **500** | Internal server error |
| **502** | AI provider/configuration error |
| **504** | AI provider timeout or connection failure |

### 10.2 Error Response Format

```json
{
  "detail": "Human-readable error message"
}
```

Or for validation errors:
```json
{
  "detail": [
    {
      "loc": ["body", "title"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

Provider/chat failures use structured details:
```json
{
  "detail": {
    "code": "provider_error",
    "message": "AI provider authentication failed. Check the provider API key.",
    "provider_error_type": "AuthenticationError",
    "provider_message": "...",
    "model": "gpt-4o-mini"
  }
}
```

Streaming chat sends provider errors as SSE payloads:
```text
data: {"error":{"code":"provider_error","message":"AI provider returned an error.","status_code":502}}

data: [DONE]
```

### 10.3 Graceful Degradation

- **LiteParse fails** → falls back to `FileProcessor` or direct text read
- **Vision API fails** → returns extracted text only (no AI analysis)
- **Embedding model fails to load** → RAG retrieval is skipped, chat can continue without knowledge context
- **Provider misconfigured** → chat returns structured `provider_config_error`; it does not silently fallback to another provider
- **Provider API fails** → chat returns structured `provider_error` (`502`, `429`, or `504` depending on failure type)
- **MCP server unavailable** → `analyze_image` returns error, doesn't crash

---

## 11. Rate Limiting

### 11.1 Implementation

Sliding window rate limiter backed by Redis:

```
Key: rate_limit:{client_id}:{minute_bucket}
TTL: 60 seconds
Increment on each request
Reject if count > RATE_LIMIT_REQUESTS_PER_MINUTE
```

### 11.2 Configuration

```env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

Rate limiting is per-client (identified by auth token). Unauthenticated requests share a default bucket.

---

## 12. Deployment

### 12.1 Docker Image

Multi-arch image (linux/amd64 + linux/arm64) on GitHub Container Registry:

```bash
docker pull ghcr.io/utsmannn/kirana:latest
```

**Image contents:**
- Python 3.11-slim base
- Node.js 22 (for MCP server support)
- poppler-utils (for PDF processing)
- All Python dependencies from `requirements.txt`
- Pre-built SvelteKit frontend (from multi-stage build)
- Alembic migrations

**Entrypoint:** `docker-entrypoint.sh`
1. Run `alembic upgrade head`
2. Start `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### 12.2 Docker Compose (Production)

```yaml
services:
  kirana:
    image: ghcr.io/utsmannn/kirana:latest
    ports:
      - "8000:8000"
    environment:
      - KIRANA_API_KEY=${KIRANA_API_KEY}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - SECRET_KEY=${SECRET_KEY}
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
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "2"

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
    deploy:
      resources:
        limits:
          memory: 512M

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

### 12.3 Environment Variables for Production

```bash
# Generate secure values
export KIRANA_API_KEY=$(openssl rand -hex 32)
export ADMIN_PASSWORD=$(openssl rand -hex 16)
export SECRET_KEY=$(openssl rand -hex 32)
```

### 12.4 Reverse Proxy (nginx)

```nginx
server {
    listen 443 ssl;
    server_name kirana.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;  # Long timeout for streaming
    }
}
```

### 12.5 Resource Planning

| Component | Memory | CPU | Disk |
|-----------|--------|-----|------|
| Kirana app | 500MB-1GB | 1-2 cores | 1GB for uploads |
| PostgreSQL | 256MB-512MB | 1 core | Depends on data volume |
| Redis | 64MB-128MB | 0.5 core | Minimal |

**Embedding model memory:** The FastEmbed model (`paraphrase-multilingual-MiniLM-L12-v2`) loads ~470MB into RAM. This happens once at startup. Plan for at least 1GB total for the Kirana container.

---

## 13. Local Development

### 13.1 Makefile Workflow

```bash
make infra           # Start PostgreSQL + Redis in Docker
make install-python  # pip install -r requirements.txt
make install-web     # npm install in web/
make migrate         # alembic upgrade head
make seed            # Seed personalities
make dev             # Start backend + frontend (concurrent, logs to console)
```

### 13.2 Manual (without Make)

```bash
# Terminal 1: Infrastructure
docker compose up -d

# Terminal 2: Backend
export PYTHONPATH=$(pwd)
export DATABASE_URL=postgresql+asyncpg://kirana:kirana@localhost:5432/kirana
export REDIS_URL=redis://localhost:6379/0
export UPLOAD_DIR=./uploads
uvicorn app.main:app --reload --port 8000

# Terminal 3: Frontend
cd web
BACKEND_PORT=8000 npm run dev
```

### 13.3 Database Migrations

```bash
# Create migration after model changes
alembic revision --autogenerate -m "description"

# Apply
alembic upgrade head

# Roll back one
alembic downgrade -1

# View history
alembic history
```

---

## Appendix: Key File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `app/services/chat_service.py` | ~400 | Chat orchestration, RAG injection, streaming |
| `app/services/rag_retrieval.py` | ~180 | Vector search, context formatting |
| `app/services/liteparse_parser.py` | ~150 | LiteParse integration, ParsedDocument types |
| `app/services/rag_chunking.py` | ~200 | tiktoken chunking, text + parsed docs |
| `app/services/rag_embeddings.py` | ~60 | FastEmbed wrapper, async embedding |
| `app/services/rag_ingestion.py` | ~100 | Chunk + embed + store orchestration |
| `app/api/v1/knowledge.py` | ~900 | Knowledge CRUD, upload, LiteParse integration |
| `app/api/v1/chat.py` | ~300 | Chat completions, WebSocket, stream buffer |
| `app/api/deps.py` | ~215 | Auth dependencies (5 auth methods) |
| `app/models/knowledge_chunk.py` | ~60 | pgvector chunk model |
| `app/tools/knowledge_tool.py` | ~120 | Vector-backed query_knowledge tool |

---

*Last updated: June 2026*
