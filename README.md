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

### 1. Clone and Configure

```bash
git clone <repository-url>
cd kirana

# Copy environment file
cp .env.example .env

# Edit .env with your API keys
vim .env
```

### 2. Start Services

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

### 3. First API Call

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model": "default", "messages": [{"role": "user", "content": "Hello!"}]}'
```

### 4. Access Admin Panel

Open http://localhost:8000/panel and login with:
- **Password**: `admin` (or your `ADMIN_PASSWORD` from .env)

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KIRANA_API_KEY` | API key for client authentication | `kirana-default-api-key-change-me` |
| `ADMIN_PASSWORD` | Admin panel login password | `admin` |
| `APP_PORT` | Application port | `8000` |
| **LLM Provider** |||
| `OPENAI_API_KEY` | Your LLM API key (OpenAI, Z.AI, etc.) | - |
| `OPENAI_BASE_URL` | Custom provider base URL | `https://api.openai.com/v1` |
| `DEFAULT_MODEL` | Default model identifier | `gpt-4o-mini` |
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

#### Add Knowledge

```bash
curl -X POST http://localhost:8000/v1/knowledge/ \
  -H "Authorization: Bearer kirana-default-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Product FAQ",
    "content": "Our product supports...",
    "metadata": {"category": "documentation"}
  }'
```

#### Search Knowledge

```bash
curl "http://localhost:8000/v1/knowledge/?q=product%20features" \
  -H "Authorization: Bearer kirana-default-api-key-change-me"
```

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

## Web Panel Usage

The built-in admin panel provides a visual interface for:

### 1. Providers
- Add/edit LLM API providers
- Configure API keys and base URLs
- Set default models

### 2. Channels
- Create channels with custom personalities
- Set system prompts and parameters
- Assign providers to channels

### 3. Sessions
- View all chat sessions
- Create new sessions with channel selection
- Browse conversation history

### 4. Chat Playground
- Test chat completions
- Switch between sessions
- Real-time streaming display

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
| `session_id` | uuid | **Kirana-specific:** Persist conversation |
| `stream_id` | string | **Kirana-specific:** For stream resume |

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
