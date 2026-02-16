# Kirana - AI Chat Service API

Kirana is a **wrapper service** for AI chatbots built with **FastAPI** and **SvelteKit**. It provides a simple HTTP API that abstracts all AI complexity - clients don't need OpenAI SDK, tool configuration, or provider management. Just simple HTTP requests.

**Key Philosophy:** *Client simplicity. Server handles the complexity.*

## Features

**🎯 Wrapper Philosophy: Simple clients, powerful server**

- **Dead-Simple HTTP API** - No SDK needed. Just POST JSON, get response.
- **Channel System** - Configure AI Provider + Personality once, use everywhere
- **Session Management** - Persistent conversations without client state management
- **Built-in Tools** - Knowledge search, datetime (configured server-side)
- **Streaming Support** - Real-time SSE streaming for chat completions
- **Custom Knowledge Base** - Upload docs, Kirana auto-searches when relevant
- **Web Admin Panel** - Manage providers, channels, sessions via GUI
- **Rate Limiting & Auth** - Built-in security layer
- **Docker Ready** - One command to run everything

## Architecture

### Wrapper Pattern

```
┌──────────┐     ┌──────────────┐     ┌────────────────┐
│  Client  │────▶│   Kirana     │────▶│  AI Provider   │
│ (Simple) │     │  (Wrapper)   │     │ (OpenAI, etc.) │
└──────────┘     └──────────────┘     └────────────────┘
                       │
                       ▼
                ┌──────────────┐
                │   Tools      │
                │  - Knowledge │
                │  - Datetime  │
                └──────────────┘
```

**Client just sends:** `{ "messages": [...] }`

**Kirana handles:** Auth, tools, knowledge, streaming, session history, rate limiting

### Provider + Channel System

Kirana uses a flexible two-layer configuration:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Provider   │────▶│   Channel   │────▶│   Session   │
│  (AI API)   │     │(Personality)│     │  (Chat)     │
└─────────────┘     └─────────────┘     └─────────────┘
```

- **Provider** - LLM API configuration (OpenAI, Z.AI, etc.) - Admin sets up once
- **Channel** - Personality, tools, system prompt - Admin configures
- **Session** - Individual chat conversations - Client just uses

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI-compatible API key (OpenAI, Z.AI, etc.)

### Option 1: Using Pre-built Image (Recommended)

Pull the latest image from GitHub Container Registry:

```bash
docker pull ghcr.io/utsmannn/kirana:latest
```

Create a `docker-compose.yml`:

```yaml
services:
  kirana:
    image: ghcr.io/utsmannn/kirana:latest
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=your-api-key
      - KIRANA_API_KEY=your-secure-api-key
      - ADMIN_PASSWORD=your-admin-password
      - DB_HOST=postgres
      - DB_USER=kirana
      - DB_PASS=kirana
      - DB_NAME=kirana
      - REDIS_HOST=redis
    depends_on:
      - postgres
      - redis
    volumes:
      - kirana-uploads:/app/uploads

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=kirana
      - POSTGRES_PASSWORD=kirana
      - POSTGRES_DB=kirana
    volumes:
      - postgres-data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data

volumes:
  kirana-uploads:
  postgres-data:
  redis-data:
```

Start services:
```bash
docker compose up -d
```

### Option 2: Build from Source

**1. Clone and Configure**

```bash
git clone <repository-url>
cd kirana

# Copy environment file
cp .env.example .env

# Edit .env with your API keys
vim .env
```

**2. Start Services**

```bash
docker compose up -d
```

Verify services are healthy:
```bash
curl http://localhost:8000/health
# {"app": "kirana", "status": "ok", "database": "ok", "redis": "ok"}
```

Services will be available at:
- **API**: http://localhost:8000
- **Admin Panel**: http://localhost:8000/panel
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

### Quick Test

**API Call:**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model": "default", "messages": [{"role": "user", "content": "Hello!"}]}'
```

**Admin Panel:**

Open http://localhost:8000/panel and login with:
- **Password**: `admin` (or your `ADMIN_PASSWORD` from .env)

### Available Docker Tags

| Tag | Description |
|-----|-------------|
| `ghcr.io/utsmannn/kirana:latest` | Latest stable release |
| `ghcr.io/utsmannn/kirana:main` | Latest development build |
| `ghcr.io/utsmannn/kirana:v1.0.0` | Specific version |
| `ghcr.io/utsmannn/kirana:1.0` | Major.minor version |

### Creating a Release

To create a new release with automatic Docker image and GitHub Release:

```bash
# Create and push a version tag
git tag v1.0.0
git push origin v1.0.0
```

This will:
1. Build Docker image for `linux/amd64` and `linux/arm64`
2. Push to `ghcr.io/utsmannn/kirana:v1.0.0`, `ghcr.io/utsmannn/kirana:1.0`, `ghcr.io/utsmannn/kirana:1`
3. Create GitHub Release with changelog from `CHANGELOG.md`

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KIRANA_API_KEY` | API key for client authentication | `kirana-default-api-key-change-me` |
| `ADMIN_PASSWORD` | Admin panel login password | `admin` |
| `SECRET_KEY` | Secret for admin token generation | (random) |
| `APP_PORT` | Application port | `8000` |
| **LLM Provider** |||
| `OPENAI_API_KEY` | Your LLM API key (OpenAI, Z.AI, etc.) | - |
| `OPENAI_BASE_URL` | Custom provider base URL | `https://api.openai.com/v1` |
| `DEFAULT_MODEL` | Default model identifier | `gpt-4o-mini` |
| `LLM_TIMEOUT` | LLM request timeout (seconds) | `120` |
| `LLM_MAX_RETRIES` | Max retry attempts | `3` |
| **Database** |||
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_USER` | PostgreSQL username | `kirana` |
| `DB_PASS` | PostgreSQL password | `kirana` |
| `DB_NAME` | PostgreSQL database name | `kirana` |
| **Redis** |||
| `REDIS_HOST` | Redis host | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| **Rate Limiting** |||
| `RATE_LIMIT_ENABLED` | Enable request rate limiting | `true` |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | Max requests per minute per client | `60` |
| **Features** |||
| `SESSION_EXPIRY_DAYS` | Auto-archive sessions after N days | `3` |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `*` |
| **Optional Services** |||
| `ZAI_API_KEY` | Z.AI API key for Vision and MCP | - |

## API Reference

### Authentication

All API endpoints require authentication via Bearer token:

```bash
Authorization: Bearer <API_KEY>
```

The default API key is set in your `.env` or can be configured per-client.

### Chat Completions

#### Non-Streaming Chat

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "stream": false
  }'
```

**Response:**
```json
{
  "id": "chat-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "glm-4.7",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello! I'm doing well, thank you for asking..."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

#### Streaming Chat

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [
      {"role": "user", "content": "Tell me a joke"}
    ],
    "stream": true
  }'
```

**Stream Response:**
```
data: {"id":"...","choices":[{"delta":{"content":"Why"}}]}
data: {"id":"...","choices":[{"delta":{"content":" did"}}]}
data: {"id":"...","choices":[{"delta":{"content":" the"}}]}
...
data: [DONE]
```

### Session Management

#### Create Session

```bash
curl -X POST http://localhost:8000/v1/sessions/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Chat Session",
    "channel_id": "<channel-uuid>",
    "metadata": {"topic": "support"}
  }'
```

**Response:**
```json
{
  "id": "session-uuid",
  "name": "My Chat Session",
  "channel_id": "channel-uuid",
  "message_count": 0,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### List Sessions

```bash
curl http://localhost:8000/v1/sessions/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me"
```

#### Chat with Session (Persistent)

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "session_id": "<session-uuid>",
    "messages": [
      {"role": "user", "content": "Remember this number: 42"}
    ]
  }'
```

#### Get Session Messages

```bash
curl http://localhost:8000/v1/sessions/<session-uuid>/messages \
  -H "Authorization: Bearer kirana-default-api-key-change-me"
```

**Response:**
```json
{
  "session_id": "session-uuid",
  "messages": [
    {"id": "msg-1", "role": "user", "content": "Hello", "created_at": "..."},
    {"id": "msg-2", "role": "assistant", "content": "Hi there!", "created_at": "..."}
  ],
  "total": 2,
  "page": 1,
  "limit": 50
}
```

### Channel Management

#### List Channels

```bash
curl http://localhost:8000/v1/channels/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me"
```

#### Create Channel

```bash
curl -X POST http://localhost:8000/v1/channels/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Support Bot",
    "provider_id": "<provider-uuid>",
    "system_prompt": "You are a helpful customer support agent.",
    "temperature": 0.7,
    "max_tokens": 2000
  }'
```

### Provider Management

#### List Providers

```bash
curl http://localhost:8000/v1/providers/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me"
```

#### Create Provider

```bash
curl -X POST http://localhost:8000/v1/providers/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Z.AI API",
    "api_key": "your-api-key",
    "base_url": "https://api.z.ai/api/coding/paas/v4",
    "default_model": "glm-4.7",
    "is_active": true
  }'
```

### Knowledge Base

Kirana provides a built-in knowledge base that can be used to store documents, FAQs, and other information. The AI automatically searches this knowledge base when relevant to user queries.

#### List Knowledge Items

```bash
curl "http://localhost:8000/v1/knowledge/?page=1&limit=20&search=faq" \
  -H "Authorization: Bearer kirana-default-api-key-change-me"
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `limit` | int | 20 | Items per page |
| `search` | string | - | Search in title/content |

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "title": "Product FAQ",
      "content": "Our product supports...",
      "content_type": "text",
      "has_file": false,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20,
  "pages": 1
}
```

#### Get Single Knowledge Item

```bash
curl http://localhost:8000/v1/knowledge/<knowledge-id> \
  -H "Authorization: Bearer kirana-default-api-key-change-me"
```

**Response:**
```json
{
  "id": "uuid",
  "title": "Product FAQ",
  "content": "Our product supports...",
  "content_type": "text",
  "has_file": false,
  "file_name": null,
  "file_size": null,
  "mime_type": null,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

#### Create Knowledge (Text)

```bash
curl -X POST http://localhost:8000/v1/knowledge/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Product FAQ",
    "content": "Our product supports the following features...",
    "content_type": "text"
  }'
```

**Request Body:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes | Title of the knowledge item |
| `content` | string | Yes | Text content |
| `content_type` | string | Yes | Type: `text`, `markdown`, `html`, `json` |

#### Update Knowledge

```bash
curl -X PATCH http://localhost:8000/v1/knowledge/<knowledge-id> \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Title",
    "content": "Updated content..."
  }'
```

#### Delete Knowledge

```bash
curl -X DELETE http://localhost:8000/v1/knowledge/<knowledge-id> \
  -H "Authorization: Bearer kirana-default-api-key-change-me"
```

#### Upload File (AI-Powered Analysis)

Upload documents for automatic AI analysis and content extraction. Supported formats:

| Format | Extension | Processing Method |
|--------|-----------|-------------------|
| PDF | `.pdf` | Native text extraction + Vision API fallback for scanned PDFs |
| Word | `.docx` | Text extraction + AI summary |
| Excel | `.xlsx`, `.xls` | Converted to images + Vision API analysis |
| PowerPoint | `.pptx` | Text extraction + AI summary |
| Images | `.png`, `.jpg`, `.jpeg` | Vision API analysis |

```bash
curl -X POST http://localhost:8000/v1/knowledge/upload \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -F "file=@document.pdf" \
  -F "title=Annual Report 2024"
```

**Form Data:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | Document file (PDF, Word, Excel, PPT, or image) |
| `title` | string | No | Custom title (defaults to filename) |

**Response:**
```json
{
  "id": "uuid",
  "title": "Annual Report 2024",
  "content": "# Document Summary\n\n[AI-generated summary of the document content...]\n\n---\n\n## Raw Content\n\n[Original extracted text from the document...]",
  "content_type": "pdf",
  "has_file": true,
  "file_name": "document.pdf",
  "file_size": 245760,
  "mime_type": "application/pdf",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Processing Pipeline:**

1. **PDF Files:**
   - Native text extraction using OCR
   - If successful → AI analysis → Save summary + raw text
   - If scanned/empty → Convert to images → Vision API → Save analysis

2. **Excel Files:**
   - Each sheet converted to image
   - Vision API analyzes all images
   - Detailed data extraction (values, formulas, charts)

3. **Word/PowerPoint:**
   - Text extraction
   - AI summary generation
   - Combined summary + raw text saved

4. **Images:**
   - Direct Vision API analysis
   - Detailed description saved

#### Download Original File

Download the original uploaded file:

```bash
curl http://localhost:8000/v1/knowledge/<knowledge-id>/download \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -o downloaded_file.pdf
```

**Response:** Binary file with appropriate `Content-Type` and `Content-Disposition` headers.

#### Knowledge Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (UUID) |
| `title` | string | Title of the knowledge item |
| `content` | string | AI-generated summary + raw text content |
| `content_type` | string | Type: `text`, `markdown`, `pdf`, `word`, `excel`, `ppt`, `image` |
| `has_file` | boolean | Whether a file is attached |
| `file_name` | string | Original filename (if uploaded) |
| `file_size` | integer | File size in bytes (if uploaded) |
| `mime_type` | string | Original MIME type (if uploaded) |
| `created_at` | string | ISO 8601 timestamp |
| `updated_at` | string | ISO 8601 timestamp |

#### Environment Variables for File Processing

| Variable | Description | Required |
|----------|-------------|----------|
| `ZAI_API_KEY` | Z.AI API key for Vision API | Yes (for file uploads) |
| `POPPLER_PATH` | Path to poppler binaries (Windows) | Optional |

### Admin Endpoints

#### Health Check

```bash
curl http://localhost:8000/health
```

#### Get Config

```bash
curl http://localhost:8000/v1/config/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me"
```

#### Get Usage Stats

```bash
curl http://localhost:8000/v1/usage/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me"
```

## Client Implementation Examples

**Note:** Kirana abstracts all AI complexity. Clients just make simple HTTP requests - no OpenAI SDK needed, no tool configuration, no provider management. Kirana handles everything server-side.

### Python (Standard Library)

```python
import urllib.request
import json

KIRANA_URL = "http://localhost:8000/v1/chat/completions"
API_KEY = "kirana-default-api-key-change-me"

# Simple non-streaming request
def chat_simple(message):
    req = urllib.request.Request(
        KIRANA_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        data=json.dumps({
            "model": "default",
            "messages": [{"role": "user", "content": message}]
        }).encode()
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]

print(chat_simple("Hello!"))

# With session (persistent conversation history)
def chat_with_session(session_id, message):
    req = urllib.request.Request(
        KIRANA_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        data=json.dumps({
            "model": "default",
            "session_id": session_id,  # Kirana manages history
            "messages": [{"role": "user", "content": message}]
        }).encode()
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())
```

### Node.js (Built-in fetch)

```javascript
const KIRANA_URL = 'http://localhost:8000/v1/chat/completions';
const API_KEY = 'kirana-default-api-key-change-me';

// Simple chat
async function chatSimple(message) {
  const response = await fetch(KIRANA_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'default',
      messages: [{ role: 'user', content: message }],
    }),
  });
  const data = await response.json();
  return data.choices[0].message.content;
}

// Streaming response
async function* chatStream(message) {
  const response = await fetch(KIRANA_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'default',
      messages: [{ role: 'user', content: message }],
      stream: true,
    }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data === '[DONE]') return;
        try {
          const parsed = JSON.parse(data);
          const content = parsed.choices?.[0]?.delta?.content;
          if (content) yield content;
        } catch {}
      }
    }
  }
}

// Usage
const response = await chatSimple('Hello!');
console.log(response);

// Or stream
for await (const chunk of chatStream('Tell me a story')) {
  process.stdout.write(chunk);
}
```

### PHP

```php
<?php
$KIRANA_URL = 'http://localhost:8000/v1/chat/completions';
$API_KEY = 'kirana-default-api-key-change-me';

function chatSimple($message) {
    global $KIRANA_URL, $API_KEY;

    $ch = curl_init($KIRANA_URL);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Authorization: Bearer $API_KEY",
        "Content-Type: application/json"
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode([
        'model' => 'default',
        'messages' => [['role' => 'user', 'content' => $message]]
    ]));

    $response = curl_exec($ch);
    curl_close($ch);

    $data = json_decode($response, true);
    return $data['choices'][0]['message']['content'];
}

echo chatSimple('Hello!');
?>
```

## Advanced Features

### Embed Widget

Kirana provides an embeddable chat widget that you can add to any website. The widget connects to your Kirana instance and provides real-time chat functionality.

#### Basic Embed

Add this to your HTML:

```html
<iframe
  src="http://localhost:8000/embed?channel_id=YOUR_CHANNEL_ID"
  width="400"
  height="600"
  style="border: none; border-radius: 12px;"
></iframe>
```

#### Embed Authentication Options

| Method | Parameter | Description |
|--------|-----------|-------------|
| **Public** | `?channel_id=<uuid>` | No auth required if channel has `public: true` |
| **Token** | `?embed_token=<token>` | Use embed token from channel config |
| **API Key** | `?token=<api_key>` | Full API access (admin use) |

#### Embed URL Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `channel_id` | UUID | Channel to use (required) |
| `embed_token` | string | Embed token for private channels |
| `token` | string | API key for full access |
| `theme` | string | Theme: `dark` or `light` (default: channel config) |
| `bg_color` | string | Background color (hex, overrides theme) |
| `text_color` | string | Text color (hex, overrides theme) |
| `primary_color` | string | Primary/accent color (hex) |
| `bubble_style` | string | Bubble style: `rounded`, `square`, `minimal` |
| `header_title` | string | Custom header title |
| `css_url` | string | URL to custom CSS file |

#### Example with Customization

```html
<iframe
  src="http://localhost:8000/embed?channel_id=abc-123&theme=light&primary_color=%234f46e5&header_title=Support%20Chat&bubble_style=rounded"
  width="400"
  height="600"
  style="border: none;"
></iframe>
```

#### Configuring Embed in Admin Panel

1. Go to **Channels** in admin panel
2. Click **Edit** on a channel
3. Scroll to **Embed Configuration**
4. Enable embed and configure:
   - **Save History**: Store chat history (localStorage + server session)
   - **Public Access**: Allow access without embed token

#### How Embed Sessions Work

Each visitor gets a unique session for conversation continuity:

1. **First visit**: Widget generates unique `visitor_id`, stores in localStorage
2. **Backend creates session**: Session named `Embed - {visitor_id}` (e.g., `Embed - a7f3b2c1`)
3. **Subsequent chats**: Widget sends `visitor_id` + `session_id` for continuity
4. **Session appears in admin**: View all embed conversations in **Sessions** page

```
User A (Browser 1) → Session: "Embed - a7f3b2c1"
User B (Browser 2) → Session: "Embed - x9y8z7w6"
```

Each visitor's conversation is isolated - no cross-user history sharing.

#### WebSocket Support

Embed uses WebSocket for real-time streaming. Connection URL:

```
ws://localhost:8000/v1/chat/ws?channel_id=<uuid>
```

For private channels:
```
ws://localhost:8000/v1/chat/ws?embed_token=<token>
```

### Tool Calling (Server-Side Configured)

Tools are configured **server-side** in Kirana. Clients don't need to define tools - just use the channel that has the tools enabled.

**Available tools in Kirana:**
- `query_knowledge` - Search knowledge base automatically when relevant
- `get_current_datetime` - Get current time in specified timezone

**How it works:**
1. Admin configures tools in a Channel via admin panel
2. Client just sends normal requests to that channel's sessions
3. Kirana automatically invokes tools when needed

```bash
# Just send a normal message - Kirana handles tool calling
# If the channel has knowledge_query enabled, Kirana will:
# 1. Detect the query needs knowledge
# 2. Call query_knowledge tool
# 3. Include results in the response

curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "What do you know about our product?"}]
  }'
# Kirana auto-calls query_knowledge if channel is configured
```

### Context Guard

Context Guard restricts AI responses to a specific domain/context. When enabled, the AI will only answer questions related to the configured context and politely decline off-topic queries.

#### Configuration (via Admin Panel)

1. Go to **Channels** → Edit Channel
2. Under **Context Guard**:
   - **Context Name**: The domain/entity (e.g., "Sekolah ABC", "Produk XYZ")
   - **Context Description**: Additional details (optional)

#### Example Behavior

**Context:** "Sekolah ABC" with description "SMA di Jakarta"

| User Question | AI Response |
|---------------|-------------|
| "Jam berapa sekolah buka?" | Answers with school info |
| "Berapa biaya SPP?" | Answers from knowledge base |
| "Bagaimana cuaca hari ini?" | Politely declines - off-topic |
| "Ceritakan lelucon" | Politely declines - off-topic |

**Without Context Guard:** AI answers any question freely.

### Web Scraping & Crawling

Kirana can scrape websites and add content to the knowledge base automatically.

#### Scrape Single URL

```bash
curl -X POST http://localhost:8000/v1/knowledge/scrape-web \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article"}'
```

#### Crawl Entire Website

```bash
curl -X POST http://localhost:8000/v1/knowledge/crawl-web \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/docs",
    "max_pages": 50,
    "max_depth": 3,
    "path_prefix": "/docs/"
  }'
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `url` | required | Starting URL |
| `max_pages` | 50 | Maximum pages to crawl |
| `max_depth` | 3 | Maximum link depth |
| `path_prefix` | null | Only crawl URLs starting with this path |

**Note:** Uses Jina AI Reader for content extraction.

## Web Panel Usage

The built-in admin panel provides a visual interface for managing Kirana.

Access at: `http://localhost:8000/panel`

### Dashboard
- View API key for client integration
- Usage statistics (total requests, tokens)
- Quick access to all sections

### Providers (Settings)
- Add/edit LLM API providers
- Configure API keys and base URLs
- Set active provider
- Set default models

### Channels
- Create channels with custom personalities
- Set system prompts and parameters
- Assign providers to channels
- **Context Guard**: Restrict AI to specific domain
- **Embed Configuration**: Enable/disable embed access

### Sessions
- View all chat sessions (including embed sessions)
- Create new sessions with channel selection
- Browse conversation history
- Delete sessions

### Knowledge
- Add text/markdown knowledge
- Upload files (PDF, Word, Excel, PPT, images)
- Scrape/crawl websites
- Search and manage knowledge items

### Chat
- Test chat completions
- Switch between sessions
- Real-time streaming display
- View conversation history

## Development

### Local Development (without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000

# In another terminal, start the web dev server
cd web
npm install
npm run dev
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_chat.py

# Run with coverage
pytest --cov=app
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Project Structure

```
kirana/
├── app/                    # FastAPI backend
│   ├── api/               # API routes
│   │   └── v1/            # Version 1 endpoints
│   ├── core/              # Core utilities (auth, rate limit, etc.)
│   ├── db/                # Database configuration
│   ├── models/            # SQLAlchemy models
│   ├── schemas/           # Pydantic schemas
│   └── services/          # Business logic
├── web/                   # SvelteKit frontend
│   ├── src/
│   │   ├── routes/        # Page routes
│   │   └── lib/           # Components and utilities
│   └── static/
├── alembic/               # Database migrations
├── scripts/               # Utility scripts
├── docker-compose.yml     # Docker services
└── Dockerfile             # Multi-stage build
```

## API Compatibility

Kirana implements the OpenAI Chat Completions API format:

| OpenAI Feature | Status | Notes |
|----------------|--------|-------|
| Chat Completions | ✅ Full | `/v1/chat/completions` |
| Streaming (SSE) | ✅ Full | Server-Sent Events |
| Tool Calling | ✅ Full | Function calling support |
| Multi-turn | ✅ Full | Via `session_id` |
| Models | ⚠️ Partial | Use `/v1/config/` instead |

### Supported Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model identifier or "default" |
| `messages` | array | Array of message objects |
| `stream` | boolean | Enable SSE streaming |
| `temperature` | float | Sampling temperature (0-2) |
| `max_tokens` | integer | Maximum tokens to generate |
| `tools` | array | Available function tools |
| `tool_choice` | string | Tool selection strategy |
| `session_id` | uuid | **Kirana:** Persist conversation |
| `channel_id` | uuid | **Kirana:** Use specific channel |
| `visitor_id` | string | **Kirana:** Unique visitor ID for embed sessions |
| `stream_id` | string | **Kirana:** For stream resume |

## Troubleshooting

### Chat history not persisting
- Ensure `session_id` is provided in chat requests
- Check database connection and `conversation_logs` table
- Verify session exists and is not expired

### Streaming not working
- Use `-N` flag with curl to disable buffering
- Ensure client supports SSE (Server-Sent Events)
- Check network timeouts for long responses

### Rate limiting errors
- Check Redis connection
- Adjust `RATE_LIMIT_REQUESTS_PER_MINUTE` in .env
- Disable with `RATE_LIMIT_ENABLED=false` for development

## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

**Built with:** FastAPI · SvelteKit · PostgreSQL · Redis · LiteLLM
