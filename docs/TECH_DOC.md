# Kirana - AI Chat Service API

## Technical Documentation

**Version:** 1.0.0
**Author:** Development Team
**Last Updated:** 2026-01-21

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Database Schema](#4-database-schema)
5. [Authentication & Security](#5-authentication--security)
6. [API Endpoints](#6-api-endpoints)
7. [Session Management](#7-session-management)
8. [Tools System](#8-tools-system)
9. [Client Configuration](#9-client-configuration)
10. [OpenAI Compatible API](#10-openai-compatible-api)
11. [MCP Integration](#11-mcp-integration)
12. [Error Handling](#12-error-handling)
13. [Rate Limiting](#13-rate-limiting)
14. [Background Tasks](#14-background-tasks)
15. [Deployment](#15-deployment)
16. [Project Structure](#16-project-structure)

---

## 1. Overview

### 1.1 What is Kirana?

Kirana adalah API service untuk AI chat yang menyediakan:
- **OpenAI-compatible API** - Drop-in replacement untuk OpenAI Chat Completions API
- **Multi-tenant client system** - Setiap client memiliki API key dan konfigurasi sendiri
- **Session Management** - Multi-session support dengan auto-cleanup setelah 3 hari tidak aktif
- **Custom Knowledge Base** - Client dapat menyimpan knowledge dalam bentuk text
- **Personality Templates** - Template personality yang bisa dipilih atau custom
- **Tool Integration** - Built-in tools untuk datetime, web search, dan knowledge retrieval
- **Thinking Mode** - Support untuk extended thinking/reasoning mode

### 1.2 Key Features

| Feature | Description |
|---------|-------------|
| Client Registration | Register client dengan API key untuk akses service |
| Session Management | Multi-session support dengan auto-cleanup (3 hari inaktif) |
| Custom Knowledge | Upload dan manage knowledge base per client |
| Personality System | Template personality + custom personality support |
| Thinking Mode | Toggle extended thinking untuk reasoning tasks |
| AI Naming | Custom nama untuk AI assistant per client |
| Tool Calling | Datetime, web search (MCP), knowledge retrieval |
| OpenAI Compatible | Compatible dengan OpenAI SDK dan API format |

### 1.3 Use Cases

1. **SaaS Chatbot Platform** - Provide AI chat untuk multiple tenants
2. **Custom AI Assistant** - Build AI dengan personality dan knowledge spesifik
3. **RAG Application** - Knowledge-augmented AI responses
4. **Agent System** - AI dengan tool calling capabilities

---

## 2. Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT APPLICATIONS                          │
│    (Web Apps, Mobile Apps, CLI Tools, OpenAI SDK Compatible)        │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         KIRANA API GATEWAY                           │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │   Auth       │  │   Rate       │  │   Request                │  │
│  │   Middleware │  │   Limiter    │  │   Validation             │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         CORE SERVICES                                │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │ Chat Service    │  │ Client Service  │  │ Knowledge Service   │ │
│  │                 │  │                 │  │                     │ │
│  │ - Completions   │  │ - Registration  │  │ - CRUD Knowledge    │ │
│  │ - Streaming     │  │ - API Keys      │  │ - Search/Retrieve   │ │
│  │ - Tool Calling  │  │ - Configuration │  │ - Embedding         │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘ │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │ Personality     │  │ Tools Service   │  │ Thinking Service    │ │
│  │ Service         │  │                 │  │                     │ │
│  │ - Templates     │  │ - Datetime      │  │ - Mode Toggle       │ │
│  │ - Custom        │  │ - Web Search    │  │ - Reasoning         │ │
│  │ - System Prompt │  │ - Knowledge     │  │ - Chain of Thought  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────────┐
│   PostgreSQL  │      │    Redis      │      │   External APIs   │
│               │      │               │      │                   │
│ - Clients     │      │ - Sessions    │      │ - OpenAI/Claude   │
│ - Knowledge   │      │ - Rate Limit  │      │ - MCP Search      │
│ - Configs     │      │ - Cache       │      │                   │
└───────────────┘      └───────────────┘      └───────────────────┘
```

### 2.2 Request Flow

```
Client Request
     │
     ▼
┌─────────────┐
│ API Gateway │
└─────┬───────┘
      │
      ▼
┌─────────────────┐     ┌──────────────┐
│ Auth Middleware │────▶│ Validate     │
│ (API Key Check) │     │ API Key      │
└─────────────────┘     └──────────────┘
      │
      ▼
┌─────────────────┐
│ Load Client     │
│ Configuration   │
│ - Personality   │
│ - Knowledge     │
│ - Thinking Mode │
│ - AI Name       │
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Build System    │
│ Prompt          │
│ + Context       │
└─────────────────┘
      │
      ▼
┌─────────────────┐     ┌──────────────┐
│ LLM Provider    │────▶│ Tool Calls   │
│ (OpenAI/Claude) │     │ (if needed)  │
└─────────────────┘     └──────────────┘
      │                        │
      │◀───────────────────────┘
      ▼
┌─────────────────┐
│ Response        │
│ (Stream/Normal) │
└─────────────────┘
```

---

## 3. Technology Stack

### 3.1 Core Technologies

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Runtime | Python | 3.11+ | Main runtime |
| Framework | FastAPI | 0.109+ | API framework |
| ASGI Server | Uvicorn | 0.27+ | Production server |
| Database | PostgreSQL | 15+ | Primary data store |
| Cache | Redis | 7+ | Caching & rate limiting |
| ORM | SQLAlchemy | 2.0+ | Database ORM |
| Migration | Alembic | 1.13+ | Database migrations |
| Validation | Pydantic | 2.0+ | Data validation |
| Scheduler | APScheduler | 3.10+ | Background task scheduling |

### 3.2 AI & LLM

| Component | Technology | Purpose |
|-----------|------------|---------|
| OpenAI SDK | openai | OpenAI API client |
| Anthropic SDK | anthropic | Claude API client |
| LiteLLM | litellm | Multi-provider abstraction |
| Tiktoken | tiktoken | Token counting |

### 3.3 External Services

| Service | Provider | Purpose |
|---------|----------|---------|
| LLM Provider | OpenAI / Anthropic | Chat completions |
| Web Search | Z.AI MCP | Web search tool |

### 3.4 Development Tools

| Tool | Purpose |
|------|---------|
| pytest | Testing framework |
| ruff | Linting & formatting |
| mypy | Type checking |
| pre-commit | Git hooks |
| docker-compose | Local development |

---

## 4. Database Schema

### 4.1 Entity Relationship Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                           clients                                 │
├──────────────────────────────────────────────────────────────────┤
│ id              UUID          PK                                 │
│ name            VARCHAR(255)  NOT NULL                           │
│ email           VARCHAR(255)  UNIQUE, NOT NULL                   │
│ api_key         VARCHAR(64)   UNIQUE, NOT NULL (hashed)          │
│ api_key_prefix  VARCHAR(8)    NOT NULL (for display: "kir_xxx")  │
│ is_active       BOOLEAN       DEFAULT TRUE                       │
│ created_at      TIMESTAMP     DEFAULT NOW()                      │
│ updated_at      TIMESTAMP     DEFAULT NOW()                      │
└──────────────────────────────────────────────────────────────────┘
                                 │
                                 │ 1:1
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                       client_configs                              │
├──────────────────────────────────────────────────────────────────┤
│ id              UUID          PK                                 │
│ client_id       UUID          FK -> clients.id, UNIQUE           │
│ ai_name         VARCHAR(100)  DEFAULT 'Kirana'                   │
│ personality_id  UUID          FK -> personalities.id, NULLABLE   │
│ custom_personality TEXT       NULLABLE (override template)       │
│ thinking_mode   VARCHAR(20)   DEFAULT 'normal'                   │
│                              ENUM: 'normal', 'extended'          │
│ model           VARCHAR(100)  DEFAULT 'gpt-4o-mini'              │
│ max_tokens      INTEGER       DEFAULT 4096                       │
│ temperature     FLOAT         DEFAULT 0.7                        │
│ tools_enabled   JSONB         DEFAULT '["datetime", "search",    │
│                                         "knowledge"]'            │
│ created_at      TIMESTAMP     DEFAULT NOW()                      │
│ updated_at      TIMESTAMP     DEFAULT NOW()                      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                        personalities                              │
├──────────────────────────────────────────────────────────────────┤
│ id              UUID          PK                                 │
│ name            VARCHAR(100)  UNIQUE, NOT NULL                   │
│ slug            VARCHAR(100)  UNIQUE, NOT NULL                   │
│ description     TEXT          NOT NULL                           │
│ system_prompt   TEXT          NOT NULL                           │
│ is_template     BOOLEAN       DEFAULT TRUE                       │
│ client_id       UUID          FK -> clients.id, NULLABLE         │
│                              (NULL = global template)            │
│ created_at      TIMESTAMP     DEFAULT NOW()                      │
│ updated_at      TIMESTAMP     DEFAULT NOW()                      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                         knowledge                                 │
├──────────────────────────────────────────────────────────────────┤
│ id              UUID          PK                                 │
│ client_id       UUID          FK -> clients.id                   │
│ title           VARCHAR(255)  NOT NULL                           │
│ content         TEXT          NOT NULL                           │
│ content_type    VARCHAR(50)   DEFAULT 'text'                     │
│                              ENUM: 'text', 'markdown', 'json'    │
│ metadata        JSONB         DEFAULT '{}'                       │
│ embedding       VECTOR(1536)  NULLABLE (for semantic search)     │
│ is_active       BOOLEAN       DEFAULT TRUE                       │
│ created_at      TIMESTAMP     DEFAULT NOW()                      │
│ updated_at      TIMESTAMP     DEFAULT NOW()                      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                      conversation_logs                            │
├──────────────────────────────────────────────────────────────────┤
│ id              UUID          PK                                 │
│ client_id       UUID          FK -> clients.id                   │
│ session_id      UUID          FK -> sessions.id, NOT NULL        │
│ role            VARCHAR(20)   NOT NULL                           │
│                              ENUM: 'system', 'user', 'assistant',│
│                                    'tool'                        │
│ content         TEXT          NOT NULL                           │
│ tool_calls      JSONB         NULLABLE                           │
│ tool_call_id    VARCHAR(100)  NULLABLE                           │
│ tokens_used     INTEGER       DEFAULT 0                          │
│ model           VARCHAR(100)  NOT NULL                           │
│ created_at      TIMESTAMP     DEFAULT NOW()                      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                        usage_logs                                 │
├──────────────────────────────────────────────────────────────────┤
│ id              UUID          PK                                 │
│ client_id       UUID          FK -> clients.id                   │
│ endpoint        VARCHAR(100)  NOT NULL                           │
│ tokens_input    INTEGER       DEFAULT 0                          │
│ tokens_output   INTEGER       DEFAULT 0                          │
│ model           VARCHAR(100)  NOT NULL                           │
│ latency_ms      INTEGER       DEFAULT 0                          │
│ status_code     INTEGER       NOT NULL                           │
│ created_at      TIMESTAMP     DEFAULT NOW()                      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                          sessions                                 │
├──────────────────────────────────────────────────────────────────┤
│ id              UUID          PK                                 │
│ client_id       UUID          FK -> clients.id                   │
│ name            VARCHAR(255)  NULLABLE (optional session name)   │
│ metadata        JSONB         DEFAULT '{}'                       │
│ message_count   INTEGER       DEFAULT 0                          │
│ total_tokens    INTEGER       DEFAULT 0                          │
│ is_active       BOOLEAN       DEFAULT TRUE                       │
│ created_at      TIMESTAMP     DEFAULT NOW()                      │
│ updated_at      TIMESTAMP     DEFAULT NOW()                      │
│ last_activity   TIMESTAMP     DEFAULT NOW()                      │
│ expires_at      TIMESTAMP     GENERATED (last_activity + 3 days) │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 Indexes

```sql
-- clients
CREATE INDEX idx_clients_api_key ON clients(api_key);
CREATE INDEX idx_clients_email ON clients(email);
CREATE INDEX idx_clients_is_active ON clients(is_active);

-- client_configs
CREATE UNIQUE INDEX idx_client_configs_client_id ON client_configs(client_id);

-- knowledge
CREATE INDEX idx_knowledge_client_id ON knowledge(client_id);
CREATE INDEX idx_knowledge_client_active ON knowledge(client_id, is_active);
CREATE INDEX idx_knowledge_embedding ON knowledge USING ivfflat (embedding vector_cosine_ops);

-- sessions
CREATE INDEX idx_sessions_client_id ON sessions(client_id);
CREATE INDEX idx_sessions_client_active ON sessions(client_id, is_active);
CREATE INDEX idx_sessions_last_activity ON sessions(last_activity);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
CREATE INDEX idx_sessions_cleanup ON sessions(is_active, expires_at)
    WHERE is_active = TRUE;

-- conversation_logs
CREATE INDEX idx_conversation_logs_session_id ON conversation_logs(session_id);
CREATE INDEX idx_conversation_logs_client_session ON conversation_logs(client_id, session_id);
CREATE INDEX idx_conversation_logs_created_at ON conversation_logs(created_at);

-- usage_logs
CREATE INDEX idx_usage_logs_client_id ON usage_logs(client_id);
CREATE INDEX idx_usage_logs_created_at ON usage_logs(created_at);
```

### 4.3 Default Personality Templates

```sql
INSERT INTO personalities (id, name, slug, description, system_prompt, is_template) VALUES
(
    uuid_generate_v4(),
    'Helpful Assistant',
    'helpful-assistant',
    'A helpful, harmless, and honest AI assistant',
    'You are a helpful AI assistant named {ai_name}. You are helpful, harmless, and honest. You answer questions accurately and concisely. If you do not know something, you say so.',
    TRUE
),
(
    uuid_generate_v4(),
    'Professional Expert',
    'professional-expert',
    'A professional expert for business and technical queries',
    'You are {ai_name}, a professional AI expert. You provide detailed, accurate, and well-structured responses. You cite sources when possible and maintain a professional tone. You are knowledgeable in business, technology, and general topics.',
    TRUE
),
(
    uuid_generate_v4(),
    'Creative Writer',
    'creative-writer',
    'A creative and imaginative writing assistant',
    'You are {ai_name}, a creative writing assistant. You help with creative writing, storytelling, and brainstorming. You are imaginative, expressive, and can adapt to different writing styles. You provide vivid descriptions and engaging narratives.',
    TRUE
),
(
    uuid_generate_v4(),
    'Code Assistant',
    'code-assistant',
    'A technical coding assistant for developers',
    'You are {ai_name}, a coding assistant. You help with programming questions, code reviews, debugging, and explaining technical concepts. You write clean, efficient, and well-documented code. You follow best practices and explain your reasoning.',
    TRUE
),
(
    uuid_generate_v4(),
    'Friendly Companion',
    'friendly-companion',
    'A friendly and casual conversational companion',
    'You are {ai_name}, a friendly AI companion. You are warm, empathetic, and conversational. You engage in casual conversations, provide emotional support, and maintain a positive tone. You use a friendly and approachable language style.',
    TRUE
);
```

---

## 5. Authentication & Security

### 5.1 API Key Format

```
Format: kir_{random_32_chars}
Example: kir_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

Storage:
- Plain key shown ONCE during registration
- Hashed (SHA-256 + salt) stored in database
- Prefix stored for identification: "kir_a1b2"
```

### 5.2 Authentication Flow

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────┐
│   Client    │────▶│ Authorization   │────▶│ Hash & Match │
│   Request   │     │ Header: Bearer  │     │ API Key      │
└─────────────┘     │ kir_xxx...      │     └──────────────┘
                    └─────────────────┘              │
                                                     ▼
                                            ┌──────────────┐
                                            │ Load Client  │
                                            │ & Config     │
                                            └──────────────┘
```

### 5.3 Security Headers

```python
# Required headers for all requests
headers = {
    "Authorization": "Bearer kir_your_api_key",
    "Content-Type": "application/json"
}

# Response security headers
response_headers = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
}
```

### 5.4 API Key Management

| Operation | Endpoint | Description |
|-----------|----------|-------------|
| Generate | POST /v1/clients | Create client + generate key |
| Regenerate | POST /v1/clients/{id}/regenerate-key | Generate new key, invalidate old |
| Revoke | DELETE /v1/clients/{id}/api-key | Revoke key (deactivate client) |
| List | GET /v1/clients/{id}/api-keys | List key prefixes (not full keys) |

---

## 6. API Endpoints

### 6.1 Client Management

#### Register Client

```http
POST /v1/clients
Content-Type: application/json

{
    "name": "My Company",
    "email": "admin@mycompany.com"
}
```

**Response (201 Created):**

```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "My Company",
    "email": "admin@mycompany.com",
    "api_key": "kir_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
    "api_key_prefix": "kir_a1b2",
    "is_active": true,
    "created_at": "2026-01-21T10:00:00Z",
    "config": {
        "ai_name": "Kirana",
        "personality": "helpful-assistant",
        "thinking_mode": "normal",
        "model": "gpt-4o-mini",
        "tools_enabled": ["datetime", "search", "knowledge"]
    }
}
```

> **Warning:** API key ditampilkan sekali saja. Simpan dengan aman!

#### Get Client Info

```http
GET /v1/clients/me
Authorization: Bearer kir_xxx
```

**Response:**

```json
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "My Company",
    "email": "admin@mycompany.com",
    "api_key_prefix": "kir_a1b2",
    "is_active": true,
    "created_at": "2026-01-21T10:00:00Z",
    "updated_at": "2026-01-21T10:00:00Z"
}
```

#### Update Client

```http
PATCH /v1/clients/me
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "name": "My Updated Company"
}
```

#### Regenerate API Key

```http
POST /v1/clients/me/regenerate-key
Authorization: Bearer kir_xxx
```

**Response:**

```json
{
    "api_key": "kir_new_key_here_32_characters",
    "api_key_prefix": "kir_new_",
    "message": "New API key generated. Old key is now invalid."
}
```

---

### 6.2 Configuration Management

#### Get Configuration

```http
GET /v1/config
Authorization: Bearer kir_xxx
```

**Response:**

```json
{
    "ai_name": "Kirana",
    "personality": {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "Helpful Assistant",
        "slug": "helpful-assistant",
        "description": "A helpful, harmless, and honest AI assistant"
    },
    "custom_personality": null,
    "thinking_mode": "normal",
    "model": "gpt-4o-mini",
    "max_tokens": 4096,
    "temperature": 0.7,
    "tools_enabled": ["datetime", "search", "knowledge"]
}
```

#### Update Configuration

```http
PATCH /v1/config
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "ai_name": "Luna",
    "personality_slug": "professional-expert",
    "thinking_mode": "extended",
    "model": "gpt-4o",
    "max_tokens": 8192,
    "temperature": 0.5,
    "tools_enabled": ["datetime", "search"]
}
```

#### Set Custom Personality

```http
PUT /v1/config/personality
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "custom_personality": "You are Luna, a wise and thoughtful AI mentor. You provide guidance with patience and wisdom. You use metaphors and stories to explain complex concepts. You encourage growth and learning."
}
```

**Note:** Custom personality overrides template. Set to `null` to use template.

---

### 6.3 Personality Templates

#### List Templates

```http
GET /v1/personalities
Authorization: Bearer kir_xxx
```

**Response:**

```json
{
    "templates": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "name": "Helpful Assistant",
            "slug": "helpful-assistant",
            "description": "A helpful, harmless, and honest AI assistant",
            "preview": "You are a helpful AI assistant..."
        },
        {
            "id": "550e8400-e29b-41d4-a716-446655440002",
            "name": "Professional Expert",
            "slug": "professional-expert",
            "description": "A professional expert for business and technical queries",
            "preview": "You are {ai_name}, a professional AI expert..."
        }
    ]
}
```

#### Get Template Detail

```http
GET /v1/personalities/{slug}
Authorization: Bearer kir_xxx
```

**Response:**

```json
{
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Helpful Assistant",
    "slug": "helpful-assistant",
    "description": "A helpful, harmless, and honest AI assistant",
    "system_prompt": "You are a helpful AI assistant named {ai_name}. You are helpful, harmless, and honest...",
    "variables": ["ai_name"]
}
```

---

### 6.4 Knowledge Management

#### Create Knowledge

```http
POST /v1/knowledge
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "title": "Company Information",
    "content": "Our company, Acme Corp, was founded in 2020. We specialize in AI solutions for enterprise...",
    "content_type": "text",
    "metadata": {
        "category": "company",
        "tags": ["about", "company-info"]
    }
}
```

**Response (201 Created):**

```json
{
    "id": "550e8400-e29b-41d4-a716-446655440010",
    "title": "Company Information",
    "content": "Our company, Acme Corp, was founded in 2020...",
    "content_type": "text",
    "metadata": {
        "category": "company",
        "tags": ["about", "company-info"]
    },
    "is_active": true,
    "created_at": "2026-01-21T10:00:00Z"
}
```

#### List Knowledge

```http
GET /v1/knowledge
Authorization: Bearer kir_xxx
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int | Page number (default: 1) |
| `limit` | int | Items per page (default: 20, max: 100) |
| `search` | string | Search in title and content |
| `content_type` | string | Filter by type: text, markdown, json |
| `is_active` | bool | Filter by active status |

**Response:**

```json
{
    "items": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440010",
            "title": "Company Information",
            "content_preview": "Our company, Acme Corp, was founded in...",
            "content_type": "text",
            "metadata": {"category": "company"},
            "is_active": true,
            "created_at": "2026-01-21T10:00:00Z"
        }
    ],
    "total": 15,
    "page": 1,
    "limit": 20,
    "pages": 1
}
```

#### Get Knowledge by ID

```http
GET /v1/knowledge/{id}
Authorization: Bearer kir_xxx
```

#### Update Knowledge

```http
PATCH /v1/knowledge/{id}
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "title": "Updated Company Information",
    "content": "Updated content here...",
    "is_active": true
}
```

#### Delete Knowledge

```http
DELETE /v1/knowledge/{id}
Authorization: Bearer kir_xxx
```

**Response (204 No Content)**

#### Bulk Upload Knowledge

```http
POST /v1/knowledge/bulk
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "items": [
        {
            "title": "FAQ 1",
            "content": "Question 1 answer...",
            "metadata": {"category": "faq"}
        },
        {
            "title": "FAQ 2",
            "content": "Question 2 answer...",
            "metadata": {"category": "faq"}
        }
    ]
}
```

**Response:**

```json
{
    "created": 2,
    "failed": 0,
    "items": [
        {"id": "...", "title": "FAQ 1", "status": "created"},
        {"id": "...", "title": "FAQ 2", "status": "created"}
    ]
}
```

---

### 6.5 Chat Completions (OpenAI Compatible)

#### Non-Streaming

```http
POST /v1/chat/completions
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "messages": [
        {"role": "user", "content": "What is the capital of France?"}
    ],
    "stream": false
}
```

**Response:**

```json
{
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "created": 1706348400,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "The capital of France is Paris."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 15,
        "completion_tokens": 10,
        "total_tokens": 25
    }
}
```

#### Streaming

```http
POST /v1/chat/completions
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "messages": [
        {"role": "user", "content": "Tell me a short story"}
    ],
    "stream": true
}
```

**Response (SSE):**

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706348400,"model":"gpt-4o-mini","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706348400,"model":"gpt-4o-mini","choices":[{"index":0,"delta":{"content":"Once"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1706348400,"model":"gpt-4o-mini","choices":[{"index":0,"delta":{"content":" upon"},"finish_reason":null}]}

data: [DONE]
```

#### With Tool Calls

```http
POST /v1/chat/completions
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "messages": [
        {"role": "user", "content": "What time is it now and search for today's news?"}
    ],
    "tools": "auto"
}
```

**Response with Tool Calls:**

```json
{
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "created": 1706348400,
    "model": "gpt-4o-mini",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": null,
                "tool_calls": [
                    {
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "get_current_datetime",
                            "arguments": "{\"timezone\": \"UTC\"}"
                        }
                    },
                    {
                        "id": "call_def456",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": "{\"query\": \"today's news January 2026\"}"
                        }
                    }
                ]
            },
            "finish_reason": "tool_calls"
        }
    ]
}
```

---

### 6.6 Tools Endpoint

#### List Available Tools

```http
GET /v1/tools
Authorization: Bearer kir_xxx
```

**Response:**

```json
{
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_current_datetime",
                "description": "Get current date and time in specified timezone",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": "Timezone name (e.g., 'UTC', 'Asia/Jakarta')"
                        },
                        "format": {
                            "type": "string",
                            "description": "Output format (e.g., 'ISO', 'human')"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_knowledge",
                "description": "Retrieve relevant knowledge from the client's knowledge base",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for knowledge retrieval"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]
}
```

#### Execute Tool (Internal)

Tools are executed automatically during chat completions when the AI determines they are needed. However, for testing purposes:

```http
POST /v1/tools/execute
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "tool": "get_current_datetime",
    "arguments": {
        "timezone": "Asia/Jakarta",
        "format": "human"
    }
}
```

**Response:**

```json
{
    "tool": "get_current_datetime",
    "result": {
        "datetime": "Tuesday, January 21, 2026 at 5:00 PM WIB",
        "timestamp": 1706360400,
        "timezone": "Asia/Jakarta"
    }
}
```

---

### 6.7 Usage & Analytics

#### Get Usage Stats

```http
GET /v1/usage
Authorization: Bearer kir_xxx
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `start_date` | string | Start date (ISO 8601) |
| `end_date` | string | End date (ISO 8601) |
| `group_by` | string | Group by: day, week, month |

**Response:**

```json
{
    "period": {
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-21T23:59:59Z"
    },
    "totals": {
        "requests": 1500,
        "tokens_input": 450000,
        "tokens_output": 150000,
        "total_tokens": 600000
    },
    "by_model": {
        "gpt-4o-mini": {
            "requests": 1200,
            "tokens": 480000
        },
        "gpt-4o": {
            "requests": 300,
            "tokens": 120000
        }
    },
    "daily": [
        {
            "date": "2026-01-21",
            "requests": 100,
            "tokens_input": 30000,
            "tokens_output": 10000
        }
    ]
}
```

---

## 7. Session Management

### 7.1 Overview

Sessions memungkinkan client untuk mengelola conversation context secara terpisah. Setiap session menyimpan history percakapan dan akan otomatis dihapus setelah 3 hari tidak ada aktivitas.

**Key Features:**
- Client dapat membuat multiple sessions
- Setiap session memiliki conversation history sendiri
- Auto-cleanup: sessions yang tidak aktif selama 3 hari akan otomatis dihapus
- Session metadata untuk tracking dan analytics

### 7.2 Session Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                      SESSION LIFECYCLE                               │
└─────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │    CREATE    │  Client creates a new session
    │   SESSION    │  POST /v1/sessions
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │    ACTIVE    │  Session is active
    │   SESSION    │  - Receives messages
    │              │  - last_activity updated on each interaction
    └──────┬───────┘
           │
           │  ◀─────────────────────────────────┐
           │                                     │
           ▼                                     │
    ┌──────────────┐     Activity within    ┌───┴──────────┐
    │   IDLE       │     3 days             │   MESSAGE    │
    │   SESSION    │  ──────────────────▶   │   RECEIVED   │
    │              │                        │              │
    └──────┬───────┘                        └──────────────┘
           │
           │  No activity for 3 days
           ▼
    ┌──────────────┐
    │   EXPIRED    │  Background job marks as inactive
    │   SESSION    │  + Deletes conversation logs
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │   DELETED    │  Session and logs removed from database
    │              │
    └──────────────┘
```

### 7.3 Session API Endpoints

#### Create Session

```http
POST /v1/sessions
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "name": "Customer Support Chat",
    "metadata": {
        "user_id": "user_123",
        "channel": "web"
    }
}
```

**Response (201 Created):**

```json
{
    "id": "550e8400-e29b-41d4-a716-446655440020",
    "name": "Customer Support Chat",
    "metadata": {
        "user_id": "user_123",
        "channel": "web"
    },
    "message_count": 0,
    "total_tokens": 0,
    "is_active": true,
    "created_at": "2026-01-21T10:00:00Z",
    "last_activity": "2026-01-21T10:00:00Z",
    "expires_at": "2026-01-24T10:00:00Z"
}
```

#### List Sessions

```http
GET /v1/sessions
Authorization: Bearer kir_xxx
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int | Page number (default: 1) |
| `limit` | int | Items per page (default: 20, max: 100) |
| `is_active` | bool | Filter by active status |
| `sort_by` | string | Sort by: `created_at`, `last_activity`, `name` |
| `order` | string | Order: `asc`, `desc` (default: `desc`) |

**Response:**

```json
{
    "items": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440020",
            "name": "Customer Support Chat",
            "message_count": 15,
            "total_tokens": 3500,
            "is_active": true,
            "created_at": "2026-01-21T10:00:00Z",
            "last_activity": "2026-01-21T14:30:00Z",
            "expires_at": "2026-01-24T14:30:00Z"
        }
    ],
    "total": 5,
    "page": 1,
    "limit": 20,
    "pages": 1
}
```

#### Get Session by ID

```http
GET /v1/sessions/{session_id}
Authorization: Bearer kir_xxx
```

**Response:**

```json
{
    "id": "550e8400-e29b-41d4-a716-446655440020",
    "name": "Customer Support Chat",
    "metadata": {
        "user_id": "user_123",
        "channel": "web"
    },
    "message_count": 15,
    "total_tokens": 3500,
    "is_active": true,
    "created_at": "2026-01-21T10:00:00Z",
    "last_activity": "2026-01-21T14:30:00Z",
    "expires_at": "2026-01-24T14:30:00Z"
}
```

#### Update Session

```http
PATCH /v1/sessions/{session_id}
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "name": "Updated Session Name",
    "metadata": {
        "user_id": "user_123",
        "channel": "web",
        "priority": "high"
    }
}
```

#### Delete Session

```http
DELETE /v1/sessions/{session_id}
Authorization: Bearer kir_xxx
```

**Response (204 No Content)**

> **Note:** Deleting a session also deletes all associated conversation logs.

#### Get Session Messages (Conversation History)

```http
GET /v1/sessions/{session_id}/messages
Authorization: Bearer kir_xxx
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int | Page number (default: 1) |
| `limit` | int | Items per page (default: 50, max: 200) |
| `order` | string | Order: `asc`, `desc` (default: `asc`) |

**Response:**

```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440020",
    "messages": [
        {
            "id": "msg_001",
            "role": "user",
            "content": "Hello, I need help with my order",
            "created_at": "2026-01-21T10:00:00Z"
        },
        {
            "id": "msg_002",
            "role": "assistant",
            "content": "Hello! I'd be happy to help you with your order. Could you please provide your order number?",
            "created_at": "2026-01-21T10:00:05Z"
        }
    ],
    "total": 15,
    "page": 1,
    "limit": 50
}
```

#### Clear Session Messages

```http
DELETE /v1/sessions/{session_id}/messages
Authorization: Bearer kir_xxx
```

**Response:**

```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440020",
    "deleted_count": 15,
    "message": "All messages cleared. Session retained."
}
```

### 7.4 Using Sessions in Chat Completions

Untuk menggunakan session dalam chat, tambahkan `session_id` di request:

```http
POST /v1/chat/completions
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "messages": [
        {"role": "user", "content": "What was my previous question?"}
    ],
    "session_id": "550e8400-e29b-41d4-a716-446655440020"
}
```

**Behavior:**
1. Jika `session_id` diberikan:
   - Conversation history dari session akan di-include sebagai context
   - New messages akan disimpan ke session
   - `last_activity` akan di-update
   - `expires_at` akan di-reset ke 3 hari dari sekarang

2. Jika `session_id` tidak diberikan:
   - Request bersifat stateless (no history)
   - Messages tidak disimpan

**Auto-create Session:**

```http
POST /v1/chat/completions
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "messages": [
        {"role": "user", "content": "Hello!"}
    ],
    "kirana": {
        "create_session": true,
        "session_name": "New Conversation"
    }
}
```

**Response** akan include session info:

```json
{
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "session": {
        "id": "550e8400-e29b-41d4-a716-446655440021",
        "name": "New Conversation",
        "is_new": true
    },
    "choices": [...],
    "usage": {...}
}
```

### 7.5 Session Expiration & Cleanup

**Expiration Rules:**

| Condition | Action |
|-----------|--------|
| No activity for 3 days | Session marked as `is_active = false` |
| 7 days after expiration | Session and logs permanently deleted |

**Cleanup Process:**

```python
# Background task runs every hour
async def cleanup_expired_sessions():
    """
    1. Mark expired sessions as inactive
    2. Delete sessions inactive for 7+ days
    """
    now = datetime.utcnow()
    expiry_threshold = now - timedelta(days=3)
    deletion_threshold = now - timedelta(days=7)

    # Mark as inactive
    await db.execute(
        update(Session)
        .where(Session.last_activity < expiry_threshold)
        .where(Session.is_active == True)
        .values(is_active=False)
    )

    # Delete old inactive sessions
    old_sessions = await db.execute(
        select(Session.id)
        .where(Session.is_active == False)
        .where(Session.last_activity < deletion_threshold)
    )

    for session_id in old_sessions:
        # Delete conversation logs first (cascade)
        await db.execute(
            delete(ConversationLog)
            .where(ConversationLog.session_id == session_id)
        )
        # Delete session
        await db.execute(
            delete(Session)
            .where(Session.id == session_id)
        )
```

### 7.6 Session Limits

| Tier | Max Active Sessions | Max Messages/Session |
|------|---------------------|---------------------|
| Free | 5 | 100 |
| Basic | 50 | 500 |
| Pro | 500 | 2000 |
| Enterprise | Unlimited | Unlimited |

---

## 8. Tools System

### 8.1 Overview

Kirana menyediakan 3 built-in tools:

| Tool | Name | Description |
|------|------|-------------|
| DateTime | `get_current_datetime` | Get current date/time |
| Web Search | `web_search` | Search web via MCP |
| Knowledge | `get_knowledge` | Retrieve from knowledge base |

### 8.2 DateTime Tool

**Function Definition:**

```python
@tool
def get_current_datetime(
    timezone: str = "UTC",
    format: str = "ISO"
) -> dict:
    """
    Get current date and time.

    Args:
        timezone: Timezone name (e.g., 'UTC', 'Asia/Jakarta', 'America/New_York')
        format: Output format - 'ISO', 'human', 'unix'

    Returns:
        dict with datetime, timestamp, timezone
    """
```

**Example Output:**

```json
{
    "datetime": "2026-01-21T10:00:00+00:00",
    "timestamp": 1706348400,
    "timezone": "UTC",
    "formatted": "Tuesday, January 21, 2026 at 10:00 AM UTC"
}
```

### 8.3 Web Search Tool (MCP Integration)

**Function Definition:**

```python
@tool
def web_search(query: str, limit: int = 5) -> dict:
    """
    Search the web for information using Z.AI MCP.

    Args:
        query: Search query string
        limit: Maximum number of results (1-10)

    Returns:
        dict with search results
    """
```

**MCP Integration:**

```python
# MCP Configuration
MCP_CONFIG = {
    "type": "http",
    "url": "https://api.z.ai/api/mcp/web_search_prime/mcp",
    "headers": {
        "Authorization": f"Bearer {settings.ZAI_API_KEY}"
    }
}

# Tool call to MCP
async def call_mcp_search(query: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            MCP_CONFIG["url"],
            headers=MCP_CONFIG["headers"],
            json={
                "method": "tools/call",
                "params": {
                    "name": "webSearchPrime",
                    "arguments": {"query": query}
                }
            }
        )
        return response.json()
```

**Example Output:**

```json
{
    "query": "AI news January 2026",
    "results": [
        {
            "title": "Latest AI Developments",
            "url": "https://example.com/ai-news",
            "summary": "Recent advancements in AI technology...",
            "site_name": "TechNews",
            "icon": "https://example.com/favicon.ico"
        }
    ],
    "total_results": 5
}
```

### 8.4 Knowledge Tool

**Function Definition:**

```python
@tool
def get_knowledge(
    query: str,
    limit: int = 3,
    threshold: float = 0.7
) -> dict:
    """
    Retrieve relevant knowledge from client's knowledge base.

    Args:
        query: Search query for knowledge retrieval
        limit: Maximum number of results
        threshold: Similarity threshold (0-1)

    Returns:
        dict with relevant knowledge items
    """
```

**Search Strategy:**

1. **Keyword Search** - Full-text search pada title dan content
2. **Semantic Search** - Vector similarity search menggunakan embeddings (jika tersedia)
3. **Hybrid** - Kombinasi keyword + semantic dengan re-ranking

**Example Output:**

```json
{
    "query": "company founding",
    "results": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440010",
            "title": "Company Information",
            "content": "Our company, Acme Corp, was founded in 2020...",
            "relevance_score": 0.92,
            "metadata": {"category": "company"}
        }
    ],
    "total_results": 1
}
```

### 8.5 Tool Execution Flow

```
┌─────────────────┐
│ User Message    │
│ "What time is   │
│  it now?"       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ LLM Determines  │
│ Tool Call       │
│ Needed          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│ Tool Router     │────▶│ Execute Tool     │
│                 │     │ get_current_     │
│                 │     │ datetime()       │
└─────────────────┘     └────────┬─────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │ Tool Result      │
                        │ {"datetime":...} │
                        └────────┬─────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │ LLM Processes    │
                        │ Result & Responds│
                        └────────┬─────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │ Final Response   │
                        │ "It's 10 AM UTC" │
                        └──────────────────┘
```

---

## 9. Client Configuration

### 9.1 AI Name

Client dapat mengatur nama AI yang akan digunakan dalam conversation.

**Set AI Name:**

```http
PATCH /v1/config
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "ai_name": "Luna"
}
```

**Usage in System Prompt:**

```
You are {ai_name}, a helpful AI assistant...
→ "You are Luna, a helpful AI assistant..."
```

### 9.2 Personality System

#### Using Templates

```http
PATCH /v1/config
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "personality_slug": "professional-expert"
}
```

#### Custom Personality

```http
PUT /v1/config/personality
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "custom_personality": "You are {ai_name}, a specialized medical information assistant. You provide accurate health information with appropriate disclaimers. You always recommend consulting healthcare professionals for medical advice."
}
```

**Template Variables:**

| Variable | Description |
|----------|-------------|
| `{ai_name}` | Client's configured AI name |
| `{knowledge_context}` | Injected knowledge (if available) |
| `{current_date}` | Current date |
| `{client_name}` | Client's company/name |

### 9.3 Thinking Mode

| Mode | Description | Use Case |
|------|-------------|----------|
| `normal` | Standard response generation | General Q&A, quick responses |
| `extended` | Extended thinking/reasoning | Complex analysis, problem solving |

**Set Thinking Mode:**

```http
PATCH /v1/config
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "thinking_mode": "extended"
}
```

**Extended Thinking Implementation:**

```python
def build_system_prompt(config: ClientConfig) -> str:
    base_prompt = get_personality_prompt(config)

    if config.thinking_mode == "extended":
        base_prompt += """

When answering complex questions:
1. First, analyze the question and identify key components
2. Think through the problem step by step
3. Consider multiple perspectives or approaches
4. Provide a well-reasoned, structured response
5. If uncertain, acknowledge limitations
"""

    return base_prompt
```

### 9.4 Model Selection

**Available Models:**

| Model | Provider | Description |
|-------|----------|-------------|
| `gpt-4o-mini` | OpenAI | Fast, cost-effective |
| `gpt-4o` | OpenAI | Most capable |
| `gpt-4-turbo` | OpenAI | Fast GPT-4 |
| `claude-3-5-sonnet` | Anthropic | Claude Sonnet |
| `claude-3-5-haiku` | Anthropic | Fast Claude |

**Set Model:**

```http
PATCH /v1/config
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "model": "gpt-4o",
    "max_tokens": 8192,
    "temperature": 0.5
}
```

### 9.5 Tools Configuration

**Enable/Disable Tools:**

```http
PATCH /v1/config
Authorization: Bearer kir_xxx
Content-Type: application/json

{
    "tools_enabled": ["datetime", "knowledge"]
}
```

**Available Tools:**
- `datetime` - Date/time tool
- `search` - Web search (MCP)
- `knowledge` - Knowledge retrieval

---

## 10. OpenAI Compatible API

### 10.1 Compatibility

Kirana API designed to be compatible with OpenAI's Chat Completions API format.

**Compatible SDK Usage:**

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.kirana.ai/v1",
    api_key="kir_your_api_key"
)

response = client.chat.completions.create(
    model="gpt-4o-mini",  # Will use client's configured model
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

### 10.2 Supported Parameters

| Parameter | Supported | Notes |
|-----------|-----------|-------|
| `messages` | Yes | Full support |
| `model` | Partial | Can override, uses client config by default |
| `stream` | Yes | SSE streaming |
| `temperature` | Yes | 0-2 |
| `max_tokens` | Yes | - |
| `tools` | Partial | Uses built-in tools, `auto` or specific list |
| `tool_choice` | Yes | `auto`, `none`, or specific |
| `n` | No | Always returns 1 choice |
| `presence_penalty` | Yes | - |
| `frequency_penalty` | Yes | - |
| `logit_bias` | No | Not supported |
| `user` | Yes | For logging |

### 10.3 Extensions

Kirana adds custom parameters:

```json
{
    "messages": [...],
    "kirana": {
        "session_id": "custom-session-123",
        "include_knowledge": true,
        "thinking_mode": "extended"
    }
}
```

---

## 11. MCP Integration

### 11.1 MCP Server Configuration

```python
# config/mcp.py
from pydantic_settings import BaseSettings

class MCPSettings(BaseSettings):
    # Z.AI Web Search MCP
    ZAI_API_KEY: str
    ZAI_MCP_URL: str = "https://api.z.ai/api/mcp/web_search_prime/mcp"

    # MCP Request timeout
    MCP_TIMEOUT: int = 30

    class Config:
        env_file = ".env"
```

### 11.2 MCP Client Implementation

```python
# services/mcp_client.py
import httpx
from typing import Any

class MCPClient:
    def __init__(self, url: str, api_key: str):
        self.url = url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call MCP tool."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.url,
                headers=self.headers,
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }
            )
            response.raise_for_status()
            return response.json()

    async def list_tools(self) -> list:
        """List available MCP tools."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.url,
                headers=self.headers,
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/list"
                }
            )
            response.raise_for_status()
            return response.json().get("result", {}).get("tools", [])
```

### 11.3 Web Search Tool Implementation

```python
# tools/web_search.py
from services.mcp_client import MCPClient
from config import settings

mcp_client = MCPClient(
    url=settings.ZAI_MCP_URL,
    api_key=settings.ZAI_API_KEY
)

async def web_search(query: str, limit: int = 5) -> dict:
    """
    Search the web using Z.AI MCP.
    """
    try:
        result = await mcp_client.call_tool(
            tool_name="webSearchPrime",
            arguments={"query": query}
        )

        # Process and format results
        content = result.get("result", {}).get("content", [])

        return {
            "query": query,
            "results": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "summary": item.get("summary"),
                    "site_name": item.get("siteName"),
                    "icon": item.get("icon")
                }
                for item in content[:limit]
            ],
            "total_results": len(content)
        }
    except Exception as e:
        return {
            "query": query,
            "error": str(e),
            "results": []
        }
```

---

## 12. Error Handling

### 12.1 Error Response Format

```json
{
    "error": {
        "code": "invalid_api_key",
        "message": "The API key provided is invalid.",
        "type": "authentication_error",
        "param": null
    }
}
```

### 12.2 Error Codes

| HTTP Code | Error Code | Description |
|-----------|------------|-------------|
| 400 | `invalid_request` | Malformed request |
| 400 | `invalid_parameter` | Invalid parameter value |
| 401 | `invalid_api_key` | Invalid or missing API key |
| 401 | `expired_api_key` | API key has been revoked |
| 403 | `permission_denied` | Not authorized for this action |
| 404 | `not_found` | Resource not found |
| 409 | `conflict` | Resource already exists |
| 422 | `validation_error` | Request validation failed |
| 429 | `rate_limit_exceeded` | Too many requests |
| 500 | `internal_error` | Server error |
| 502 | `provider_error` | LLM provider error |
| 503 | `service_unavailable` | Service temporarily unavailable |

### 12.3 Validation Errors

```json
{
    "error": {
        "code": "validation_error",
        "message": "Request validation failed",
        "type": "invalid_request_error",
        "details": [
            {
                "field": "messages",
                "message": "messages is required"
            },
            {
                "field": "temperature",
                "message": "temperature must be between 0 and 2"
            }
        ]
    }
}
```

---

## 13. Rate Limiting

### 13.1 Default Limits

| Tier | Requests/min | Tokens/day |
|------|--------------|------------|
| Free | 10 | 10,000 |
| Basic | 60 | 100,000 |
| Pro | 300 | 1,000,000 |
| Enterprise | Custom | Custom |

### 13.2 Rate Limit Headers

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1706348460
```

### 13.3 Rate Limit Response

```json
{
    "error": {
        "code": "rate_limit_exceeded",
        "message": "Rate limit exceeded. Please try again in 30 seconds.",
        "type": "rate_limit_error",
        "retry_after": 30
    }
}
```

---

## 14. Background Tasks

### 14.1 Overview

Kirana menggunakan background tasks untuk operasi yang tidak perlu blocking request. Tasks dijalankan menggunakan kombinasi:
- **APScheduler** - Untuk scheduled/periodic tasks
- **Redis** - Untuk task queue dan distributed locking
- **Asyncio** - Untuk async task execution

### 14.2 Session Cleanup Task

Task utama untuk membersihkan sessions yang expired.

```python
# app/tasks/session_cleanup.py
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db.session import async_session
from app.models.session import Session
from app.models.conversation import ConversationLog
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Configuration
SESSION_EXPIRY_DAYS = 3      # Mark inactive after 3 days
SESSION_DELETION_DAYS = 7    # Delete after 7 days of inactivity
CLEANUP_INTERVAL_HOURS = 1   # Run every hour

async def cleanup_expired_sessions():
    """
    Background task to cleanup expired sessions.

    Process:
    1. Mark sessions as inactive if no activity for 3 days
    2. Delete sessions (and their logs) that have been inactive for 7 days
    """
    async with async_session() as db:
        try:
            now = datetime.utcnow()
            expiry_threshold = now - timedelta(days=SESSION_EXPIRY_DAYS)
            deletion_threshold = now - timedelta(days=SESSION_DELETION_DAYS)

            # Step 1: Mark expired sessions as inactive
            result = await db.execute(
                update(Session)
                .where(Session.last_activity < expiry_threshold)
                .where(Session.is_active == True)
                .values(is_active=False, updated_at=now)
            )
            expired_count = result.rowcount

            if expired_count > 0:
                logger.info(f"Marked {expired_count} sessions as expired")

            # Step 2: Get sessions to delete
            sessions_to_delete = await db.execute(
                select(Session.id)
                .where(Session.is_active == False)
                .where(Session.last_activity < deletion_threshold)
            )
            session_ids = [row[0] for row in sessions_to_delete.fetchall()]

            if session_ids:
                # Delete conversation logs first
                await db.execute(
                    delete(ConversationLog)
                    .where(ConversationLog.session_id.in_(session_ids))
                )

                # Delete sessions
                await db.execute(
                    delete(Session)
                    .where(Session.id.in_(session_ids))
                )

                logger.info(f"Deleted {len(session_ids)} old sessions and their logs")

            await db.commit()

        except Exception as e:
            logger.error(f"Session cleanup failed: {e}")
            await db.rollback()
            raise


def setup_scheduler() -> AsyncIOScheduler:
    """Setup and return the background task scheduler."""
    scheduler = AsyncIOScheduler()

    # Session cleanup - runs every hour
    scheduler.add_job(
        cleanup_expired_sessions,
        'interval',
        hours=CLEANUP_INTERVAL_HOURS,
        id='session_cleanup',
        name='Cleanup Expired Sessions',
        replace_existing=True
    )

    return scheduler
```

### 14.3 Scheduler Integration

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.tasks.session_cleanup import setup_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler = setup_scheduler()
    scheduler.start()

    yield

    # Shutdown
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
```

### 14.4 Task Monitoring

**Health Check Endpoint:**

```http
GET /v1/health/tasks
Authorization: Bearer kir_xxx (admin only)
```

**Response:**

```json
{
    "scheduler_running": true,
    "tasks": [
        {
            "id": "session_cleanup",
            "name": "Cleanup Expired Sessions",
            "next_run": "2026-01-21T11:00:00Z",
            "last_run": "2026-01-21T10:00:00Z",
            "status": "success"
        }
    ]
}
```

### 14.5 Manual Trigger

For admin/maintenance purposes:

```http
POST /v1/admin/tasks/session-cleanup/run
Authorization: Bearer kir_xxx (admin only)
```

**Response:**

```json
{
    "task": "session_cleanup",
    "status": "completed",
    "expired_sessions": 15,
    "deleted_sessions": 5,
    "duration_ms": 234
}
```

---

## 15. Deployment

### 15.1 Environment Variables

```bash
# .env.example

# Application
APP_NAME=kirana
APP_ENV=production
DEBUG=false
SECRET_KEY=your-secret-key-here

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/kirana

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM Providers
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx

# MCP - Z.AI
ZAI_API_KEY=your-zai-api-key

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Session Management
SESSION_EXPIRY_DAYS=3
SESSION_DELETION_DAYS=7
SESSION_CLEANUP_INTERVAL_HOURS=1

# Logging
LOG_LEVEL=INFO
```

### 15.2 Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://kirana:kirana@db:5432/kirana
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    volumes:
      - ./:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  db:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_USER=kirana
      - POSTGRES_PASSWORD=kirana
      - POSTGRES_DB=kirana
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

### 15.3 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 16. Project Structure

```
kirana/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry
│   ├── config.py               # Configuration settings
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py             # Dependencies (auth, db session)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py       # API router aggregation
│   │       ├── clients.py      # Client endpoints
│   │       ├── config.py       # Configuration endpoints
│   │       ├── sessions.py     # Session endpoints
│   │       ├── knowledge.py    # Knowledge endpoints
│   │       ├── chat.py         # Chat completions endpoints
│   │       ├── personalities.py # Personality endpoints
│   │       ├── tools.py        # Tools endpoints
│   │       └── usage.py        # Usage endpoints
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py             # Base model class
│   │   ├── client.py           # Client model
│   │   ├── client_config.py    # ClientConfig model
│   │   ├── personality.py      # Personality model
│   │   ├── knowledge.py        # Knowledge model
│   │   ├── session.py          # Session model
│   │   ├── conversation.py     # ConversationLog model
│   │   └── usage.py            # UsageLog model
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── client.py           # Client Pydantic schemas
│   │   ├── config.py           # Config schemas
│   │   ├── session.py          # Session schemas
│   │   ├── knowledge.py        # Knowledge schemas
│   │   ├── chat.py             # Chat request/response schemas
│   │   ├── personality.py      # Personality schemas
│   │   └── common.py           # Common schemas (pagination, etc.)
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── client_service.py   # Client business logic
│   │   ├── session_service.py  # Session management
│   │   ├── chat_service.py     # Chat completions logic
│   │   ├── knowledge_service.py # Knowledge management
│   │   ├── personality_service.py # Personality management
│   │   ├── tool_service.py     # Tool execution
│   │   └── mcp_client.py       # MCP client
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py             # Base tool class
│   │   ├── datetime_tool.py    # DateTime tool
│   │   ├── search_tool.py      # Web search tool
│   │   ├── knowledge_tool.py   # Knowledge retrieval tool
│   │   └── registry.py         # Tool registry
│   │
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── session_cleanup.py  # Session cleanup background task
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py         # API key hashing, auth
│   │   ├── rate_limiter.py     # Rate limiting
│   │   └── exceptions.py       # Custom exceptions
│   │
│   └── db/
│       ├── __init__.py
│       ├── session.py          # Database session
│       └── init_db.py          # Database initialization
│
├── alembic/
│   ├── env.py
│   ├── versions/               # Migration files
│   └── alembic.ini
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Test fixtures
│   ├── test_clients.py
│   ├── test_sessions.py        # Session tests
│   ├── test_chat.py
│   ├── test_knowledge.py
│   └── test_tools.py
│
├── docs/
│   ├── TECH_DOC.md             # This document
│   └── API.md                  # API reference
│
├── scripts/
│   ├── init_db.py              # Initialize database
│   └── seed_personalities.py   # Seed personality templates
│
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Appendix A: Personality Template Examples

### A.1 Helpful Assistant

```
You are {ai_name}, a helpful, harmless, and honest AI assistant.

Your core principles:
- Be helpful: Provide accurate, relevant, and useful information
- Be harmless: Never provide harmful, dangerous, or unethical advice
- Be honest: If you don't know something, say so. Don't make up information.

When responding:
- Be concise but thorough
- Use clear, simple language
- Structure complex answers with bullet points or numbered lists
- Ask clarifying questions when the request is ambiguous

{knowledge_context}
```

### A.2 Professional Expert

```
You are {ai_name}, a professional AI expert serving {client_name}.

Your expertise areas include business strategy, technology, and general knowledge.

Professional guidelines:
- Maintain a professional, respectful tone
- Provide detailed, well-structured responses
- Cite sources or reasoning when possible
- Acknowledge uncertainty and limitations
- Offer actionable recommendations

When answering:
- Start with a direct answer, then provide context
- Use industry-appropriate terminology
- Consider multiple perspectives
- Highlight risks and considerations

{knowledge_context}
```

### A.3 Code Assistant

```
You are {ai_name}, an expert coding assistant.

Your capabilities:
- Write clean, efficient, well-documented code
- Debug and fix issues
- Explain technical concepts clearly
- Review code and suggest improvements
- Follow best practices and design patterns

Coding principles:
- Write readable, maintainable code
- Include appropriate error handling
- Add comments for complex logic
- Consider performance implications
- Follow language-specific conventions

Response format for code:
- Explain the approach briefly
- Provide the code solution
- Explain key parts if complex
- Suggest improvements or alternatives if applicable

{knowledge_context}
```

---

## Appendix B: SDK Examples

### B.1 Python (OpenAI SDK)

```python
from openai import OpenAI

# Initialize client
client = OpenAI(
    base_url="https://api.kirana.ai/v1",
    api_key="kir_your_api_key"
)

# Simple chat
response = client.chat.completions.create(
    model="default",  # Uses client's configured model
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)
print(response.choices[0].message.content)

# Streaming
stream = client.chat.completions.create(
    model="default",
    messages=[
        {"role": "user", "content": "Tell me a story"}
    ],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### B.2 JavaScript/TypeScript

```typescript
import OpenAI from 'openai';

const client = new OpenAI({
  baseURL: 'https://api.kirana.ai/v1',
  apiKey: 'kir_your_api_key',
});

async function chat() {
  const response = await client.chat.completions.create({
    model: 'default',
    messages: [
      { role: 'user', content: 'Hello!' }
    ]
  });

  console.log(response.choices[0].message.content);
}

// Streaming
async function streamChat() {
  const stream = await client.chat.completions.create({
    model: 'default',
    messages: [
      { role: 'user', content: 'Tell me a story' }
    ],
    stream: true
  });

  for await (const chunk of stream) {
    process.stdout.write(chunk.choices[0]?.delta?.content || '');
  }
}
```

### B.3 cURL

```bash
# Simple request
curl -X POST https://api.kirana.ai/v1/chat/completions \
  -H "Authorization: Bearer kir_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'

# Streaming
curl -X POST https://api.kirana.ai/v1/chat/completions \
  -H "Authorization: Bearer kir_your_api_key" \
  -H "Content-Type: application/json" \
  -N \
  -d '{
    "messages": [
      {"role": "user", "content": "Tell me a story"}
    ],
    "stream": true
  }'
```

---

## Appendix C: Changelog

### Version 1.0.0 (Initial Release)

- Client registration with API key
- Knowledge management (CRUD)
- Personality templates + custom personality
- Thinking mode (normal/extended)
- AI naming
- Built-in tools: datetime, web search (MCP), knowledge
- OpenAI-compatible chat completions API
- Streaming support
- Usage tracking

---

**End of Technical Documentation**
