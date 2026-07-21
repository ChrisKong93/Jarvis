# Jarvis AI Agent

> [中文版](README.md)

An AI Agent intelligent assistant system based on FastAPI + Vue3, supporting **local llama.cpp** and **cloud-based LLMs** (DeepSeek, OpenAI, Kimi, GLM, Qwen, etc.), featuring task planning, tool calling, memory mechanisms, streaming output, and session management.

## Features

- 🔐 **User System**: Register, login, logout with password validation (≥8 chars, letter + digit required), per-user independent model configuration and memory
- 🎯 **Task Planning**: Three Agent modes, all powered by LangGraph directed graph orchestration
  - **Plan & Execute** (default): LLM analyzes tasks and creates an execution plan with parallel groups, then executes group by group
  - **ReAct**: Classic Think → Act → Observe loop with tool calling, error reflection and retry
  - **Chat**: Pure conversation mode, suitable for daily chat without tool calling
- 🔄 **Reflection Mechanism**: Automatically retries and adjusts strategies when tool calls fail
- 🛠️ **Tool Calling**: Supports calculator, search, weather, file operations, date/time tools with **parallel execution**
- 🧩 **Plugin System**: Tools managed as plugins with enable/disable, install/uninstall capabilities
- 🧠 **Memory System**: Short-term (conversation summaries) and long-term (important info persistence) memory, backed by SQLite + ChromaDB vector storage, LLM-automated importance scoring (threshold ≥ 6/10), background embedding model download
- 🔐 **API Key Encryption**: Fernet (PBKDF2) encrypted storage for user API Keys
- 🔗 **MCP Protocol Support**: Integrated Model Context Protocol with stdio and SSE transport, connect external MCP servers to extend tool capabilities
- ⚡ **Streaming Output**: SSE (Server-Sent Events) streaming, token-by-token rendering, real-time tool call visualization
- 💬 **Multi-turn Conversation**: Complete context management with intelligent truncation strategy
- 📁 **Session Management**: Create, switch, delete sessions with auto title preview, auto-save history
- ☁️ **Multi-model Support**: Local llama.cpp + cloud OpenAI-compatible APIs, freely switchable in frontend
- 🔄 **Quick Model Switching**: Dropdown in header to quickly switch between configured Providers
- 🗄️ **Database Storage**: Model configs, memories, sessions persisted in SQLite, survives browser changes
- 🌓 **Theme Switching**: Supports light mode (white background) and dark mode (dark background)
- 📊 **Performance Monitoring**: Real-time display of response time, Tokens/s, input/output Tokens
- 🚦 **Rate Limiting**: Login/register endpoints throttled via slowapi

## Supported Model Providers

| Provider | Description |
|----------|-------------|
| `llama_cpp` | Local llama.cpp service (no API Key required) |
| `deepseek` | DeepSeek Cloud |
| `openai` | OpenAI GPT Series |
| `moonshot` | Moonshot (Kimi) |
| `zhipu` | Zhipu GLM |
| `dashscope` | Aliyun Qwen |
| `siliconflow` | SiliconFlow model aggregation |
| `custom` | Custom OpenAI-compatible API |

## Tech Stack

- **Backend**: Python 3.9+, FastAPI, SQLAlchemy, SQLite, ChromaDB (vector storage)
- **LLMs**: llama.cpp (local) / OpenAI-compatible APIs (cloud)
- **Agent Framework**: LangGraph (finite-state machine graph orchestration)
- **Frontend**: Vue 3 + Vite + Fetch API (SSE streaming)
- **Auth**: JWT Token, bcrypt password hashing
- **Security**: Fernet (PBKDF2) API Key encryption
- **Deployment**: Uvicorn

## Project Structure

```
Jarvis/
├── backend/
│   ├── graph_agent.py        # Core Agent logic (LangGraph-based, supports chat / ReAct / Plan&Execute, with streaming run_stream)
│   ├── crypto_utils.py       # API Key encryption/decryption (Fernet + PBKDF2)
│   ├── auth.py               # User authentication (JWT, password hashing)
│   ├── database.py           # Database models (User, ModelConfig, ShortTermMemory, LongTermMemory, Plugin, ChatSession)
│   ├── plugin_manager.py     # Plugin manager (install/uninstall/enable/disable)
│   ├── routes/               # API route modules
│   │   ├── auth.py           #   Auth endpoints
│   │   ├── chat.py           #   Chat & Agent endpoints
│   │   ├── config.py         #   Model config endpoints
│   │   ├── memory.py         #   Memory endpoints
│   │   ├── mcp.py            #   MCP management endpoints
│   │   ├── plugins.py        #   Plugin management endpoints
│   │   ├── session.py        #   Session management endpoints
│   │   ├── tools.py          #   Tool list endpoint
│   │   └── helpers.py        #   Shared helper functions
│   ├── providers/            # Multi-model Provider abstraction
│   │   ├── registry.py       # Provider registry
│   │   ├── client.py         # Unified LLM client (sync/async, with connection pool)
│   │   └── __init__.py
│   ├── memory/               # Memory system
│   │   ├── __init__.py       # MemoryManager
│   │   ├── short_term.py     # Short-term memory (SQLite)
│   │   ├── long_term.py      # Long-term memory (SQLite + ChromaDB vector search)
│   │   ├── embeddings.py     # Embedding generation (sentence-transformers, with fallback pseudo-vector)
│   │   └── vector_store.py   # ChromaDB vector store wrapper
│   ├── tools/                # Tool set (default plugins)
│   │   ├── base.py           # Tool registry (with MCP tool registration)
│   │   ├── calculator.py
│   │   ├── datetime_tool.py
│   │   ├── file_tool.py
│   │   ├── search.py
│   │   └── weather.py
│   ├── session_manager.py    # Session management (SQLite persistence)
│   ├── context_manager.py    # Context management & token truncation
│   └── mcp/                  # MCP (Model Context Protocol) integration
│       ├── __init__.py
│       ├── manager.py        # MCP server manager (JSON-RPC 2.0, supports stdio/SSE)
│       ├── adapter.py        # MCP tool adapter
│       └── servers.json      # MCP server config file (optional)
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatPanel.vue      # Chat panel (with SSE streaming reader)
│   │   │   ├── SidebarLeft.vue    # Left sidebar (session list + navigation, MCP nav)
│   │   │   ├── SidebarRight.vue   # Right sidebar (memory + performance)
│   │   │   ├── LoginPage.vue      # Login/Registration page
│   │   │   ├── PluginPage.vue     # Plugin management page
│   │   │   ├── MCPServerPage.vue  # MCP server management page
│   │   │   └── SettingsPage.vue   # Settings page
│   │   ├── App.vue                # Main app component
│   │   ├── main.js                # Entry file
│   │   └── style.css              # Global styles (with theme variables)
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── jsconfig.json
├── data/                     # Runtime data
│   ├── jarvis.db             # SQLite database
│   └── vectors/              # ChromaDB vector store
├── requirements.txt
├── Dockerfile               # Multi-stage build (frontend + backend), with HEALTHCHECK + non-root user
├── docker-compose.yml       # Docker Compose config (healthcheck, persistent volumes)
├── .dockerignore
├── .env.example             # Environment variable example
├── pytest.ini               # Test configuration
├── .coveragerc              # Coverage configuration
├── tests/                   # Test directory
│   ├── unit/                #   Unit tests
│   └── integration/         #   Integration tests
├── README.md
└── README_EN.md
```

## Quick Start

### 1. Clone Project

```bash
git clone <repo-url>
cd Jarvis
```

### 2. Install Backend Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Install Frontend Dependencies & Build

```bash
cd frontend
npm install
npm run build
```

### 4. Start Service

```bash
# Use venv Python
venv/bin/python backend/main.py
```

### 5. Usage

Visit `http://localhost:8000`:

1. **Register Account** → First time register (password ≥ 8 chars, must contain letter + digit)
2. **Login System** → Use registered credentials
3. **Configure Model** → Left sidebar ⚙️ settings to configure Provider, API Key (encrypted storage)
4. **Start Chatting** → Input messages in chat panel, streaming output supported

## Docker Deployment

```bash
# 1. Configure environment variables (change SECRET_KEY and other settings)
cp .env.example .env
# Edit .env file with your SECRET_KEY and LLM configuration

# 2. Start services (auto-builds frontend + backend)
docker compose up -d

# 3. View logs
docker compose logs -f

# 4. Stop services
docker compose down
```

Visit `http://localhost:8000` to use.

> **Notes:**
> - To access host services (e.g., local llama.cpp) from Docker, use `host.docker.internal`
> - Data persists in `./data/` directory (SQLite + ChromaDB vector store)
> - Embedding model cache is stored in the Docker volume `embedding_cache`
> - Docker image includes HEALTHCHECK and graceful shutdown via `init: true`
> - Container runs as a non-root user for enhanced security

### China Mainland Mirror

Docker Hub is unstable in China. Configure **Docker daemon registry mirrors**:

**Step 1: Configure mirror accelerator**

Open Docker Desktop → **Settings** → **Docker Engine**, add to `daemon.json`:

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://hub-mirror.c.163.com"
  ]
}
```

Click **Apply & Restart**.

**Step 2: Build and start**

```bash
cp .env.example .env
# For China mainland users: uncomment PIP_INDEX_URL in .env to use Tsinghua mirror
docker compose build
docker compose up -d
```

## User System

Jarvis has built-in user authentication:

| Feature | Description |
|---------|-------------|
| Registration | Fill username, email and password to register (password ≥ 8 chars, letter + digit required) |
| Login | JWT Token authentication, 30-day validity; rate limited |
| Logout | Clear Token, return to login page |
| Model Config | Each user manages their own model configs (API Key encrypted) |
| Memory Isolation | Each user has independent short/long-term memory |

> All user data (password hashes, model configs, memories) stored in server SQLite database, survives browser changes or cache clearing.

## Agent Modes

Jarvis supports three Agent modes, selectable in settings page or request parameters:

| Mode | Description |
|------|-------------|
| `plan_execute` (default) | LangGraph-based. LLM analyzes task and creates a plan with parallel groups, then executes group by group (parallel/serial). Supports parallel tool calls and reflection |
| `react` | LangGraph-based. Classic ReAct (Think → Act → Observe) loop with tool guessing, parallel execution, error reflection and retry |
| `chat` | LangGraph-based. Pure conversation mode, suitable for daily chat without tool calling. Flow: LLM call → memory update |

> Default mode configurable via `DEFAULT_AGENT_MODE` environment variable.

## Plugin System

Jarvis plugin system manages tools as plugins with enable/disable, install/uninstall capabilities.

### Default Plugins

| Icon | Plugin | Description | Type |
|------|--------|-------------|------|
| 🔢 | Calculator | Mathematical expression calculation | Default |
| 🔍 | Search Engine | Internet information retrieval | Default |
| 🌤️ | Weather Forecast | City weather query | Default |
| 📁 | File Operations | File read/write operations | Default |
| ⏰ | Date/Time | Get time/set timers | Default |

### Plugin Management

Plugin management page (left sidebar navigation → 🧩 plugins) supports:

- **View Plugin List**: Show all installed plugins
- **Enable/Disable**: Toggle plugin on/off via switches
- **Install Plugins**: Install new plugins by filling plugin info
- **Uninstall Plugins**: Completely uninstall non-default plugins

### Plugin API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/plugins` | GET | Get all plugins list |
| `/api/plugins/enabled` | GET | Get enabled plugins |
| `/api/plugins/{id}/toggle` | PUT | Toggle plugin enable/disable |
| `/api/plugins` | POST | Install new plugin |
| `/api/plugins/{id}` | DELETE | Uninstall plugin |

## MCP (Model Context Protocol) Integration

Jarvis supports [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), allowing connection to external MCP servers to extend tool capabilities.

### Transport Types

| Type | Description |
|------|-------------|
| `stdio` | Communication via subprocess stdin/stdout (local command) |
| `sse` | Communication via HTTP POST + SSE (remote service) |

### Configuration

Create a `backend/mcp/servers.json` file:

```json
{
  "servers": [
    {
      "name": "my-server",
      "transport": "stdio",
      "command": "node",
      "args": ["path/to/server.js"],
      "env": {"API_KEY": "xxx"}
    },
    {
      "name": "remote-server",
      "transport": "sse",
      "url": "http://localhost:3000/mcp"
    }
  ]
}
```

MCP config path can be customized via `MCP_CONFIG_PATH` environment variable.

### MCP Management Page

Left sidebar navigation → 🔗 MCP Servers, view connected MCP servers and their tools.

### MCP Management API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/mcp/servers` | GET | Get all MCP server connection status |
| `/api/mcp/tools` | GET | Get all MCP tools list |
| `/api/mcp/servers/reload` | POST | Reload MCP config and reconnect all servers |
| `/api/mcp/servers/{name}/reconnect` | POST | Reconnect specific MCP server |
| `/api/mcp/servers/{name}` | PUT | Update MCP server configuration |
| `/api/mcp/servers/{name}` | DELETE | Delete MCP server configuration |

## Model Management

### Quick Model Switching (Header)

Header shows **quick model switching** dropdown with only configured Providers, click to switch, Provider configs (API Key, model, base_url) automatically apply.

### Model Settings Panel (Left Sidebar ⚙️)

In left sidebar settings page you can:

- **Select Provider**: Choose from available Provider list
- **Configure API Key / Base URL**: Fill server connection info (API Key encrypted)
- **Select Model**: Choose from Provider's supported model list (supports dynamic fetching)
- **Configure Max Tokens**, Agent mode (plan_execute / react / chat)
- Configured Providers show ✓ and "Configured" label

### Configuration Flow

```
First time use
    ↓
Left sidebar ⚙️ settings → Select Provider (e.g., DeepSeek)
    ↓
Fill API Key → Select Model → Click save (Key encrypted)
    ↓
Config persisted to SQLite database
    ↓
Top quick switch dropdown automatically shows that Provider
    ↓
Subsequent use can directly switch in top, no reconfiguration needed
```

## Memory System

| Type | Storage | Retrieval | User Isolation | Features |
|------|---------|-----------|----------------|----------|
| Short-term | SQLite `short_term_memories` table | Direct read | ✅ Per user | Auto-generate summary every N turns, auto-overwrite oldest |
| Long-term | SQLite `long_term_memories` table + ChromaDB vector index | Semantic vector search (top_k=3) | ✅ Per user | LLM importance scoring (threshold ≥ 6/10), vector dedup (similarity ≥ 0.85 skip), time-decay ranking (30-day half-life) |

Memory is automatically managed by Agent:

- Agent generates short-term summaries during conversations
- LLM analyzes and scores each conversation (1-10) after completion
- Info with importance ≥ 6 is extracted as long-term memory, stored in SQLite + ChromaDB
- Embedding model (default all-MiniLM-L6-v2) auto-downloads in background, falls back to pseudo-vector mode when unavailable
- Related memory retrieved via vector similarity search before each conversation
- Right sidebar panel for viewing and managing all memories

## Streaming Output

Jarvis supports full SSE (Server-Sent Events) streaming:

- **Token-by-token rendering**: Each LLM-generated token pushed to frontend in real-time
- **Tool call visualization**: Tool invocation, execution, and reflection displayed in real-time
- **Event types**: `token`, `thinking`, `tool_call`, `tool_result`, `summary_start`, `done`, `error`

## Interface Layout

### Left Sidebar
- **Header**: Jarvis Logo + AI Assistant identifier
- **Navigation**: 💬 Chat / 🧩 Plugins / 🔗 MCP Servers / ⚙️ Settings (vertical)
- **Chat Page**: Session list + action buttons (new/save/clear)
- **Plugins/MCP/Settings Pages**: Content area

### Center Area
- **Chat Page**: ChatPanel interface
- **Plugins Page**: Plugin management interface
- **MCP Page**: MCPServerPage MCP management interface
- **Settings Page**: Model configuration interface

### Right Sidebar (Chat Page Only)
- **Memory System**: View/manage short/long-term memory (clear all, single delete)
- **Performance Metrics**: Response time, Tokens/s, input/output Tokens etc.

## API Interfaces

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | User registration (password ≥ 8 chars, letter+digit; 5/min rate limit) |
| `/api/auth/login` | POST | User login (returns JWT Token; 10/min rate limit) |
| `/api/auth/logout` | POST | User logout |
| `/api/auth/me` | GET | Get current user info |

### Model Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/providers` | GET | Get available Providers list |
| `/api/user/config` | GET | Get current user's model configs |
| `/api/user/config` | POST | Save current user's model config (includes agent_mode) |
| `/api/user/config/{id}` | DELETE | Delete specific model config |
| `/api/models` | GET | Get models for specific Provider |

### Chat (Streaming)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/stream` | POST | Basic chat (SSE streaming) |
| `/api/agent/stream` | POST | Agent chat with tool calling (SSE streaming) |
| `/api/chat` | POST | Basic chat (non-streaming, legacy) |
| `/api/agent` | POST | Agent chat (non-streaming, legacy) |
| `/api/health` | GET | Health check (supports `?provider=deepseek`) |

### Sessions

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/session` | POST | Create session |
| `/api/sessions` | GET | Get session list (with title/preview) |
| `/api/session/{id}` | GET | Get session details |
| `/api/session/{id}` | DELETE | Delete session |

### Tools / Memory

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tools` | GET | Get tool list |
| `/api/memory` | GET | Get current user's long-term memory |
| `/api/memory` | POST | Manually add long-term memory |
| `/api/memory/stats` | GET | Get memory statistics (short/long counts, total tokens) |
| `/api/memory` | DELETE | Clear all memories for current user (short + long + vectors) |
| `/api/memory/{memory_id}` | DELETE | Delete specific long-term memory |
| `/api/memory/search` | GET | Semantic search long-term memory |

### MCP Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/mcp/servers` | GET | Get all MCP server connection status |
| `/api/mcp/tools` | GET | Get all MCP tools list |
| `/api/mcp/servers/reload` | POST | Reload MCP config and reconnect |
| `/api/mcp/servers/{name}/reconnect` | POST | Reconnect specific MCP server |
| `/api/mcp/servers/{name}` | PUT | Update MCP server configuration |
| `/api/mcp/servers/{name}` | DELETE | Delete MCP server |

### Request Parameters (stream endpoints)

```json
{
  "messages": [{"role": "user", "content": "Hello"}],
  "session_id": "your-session-id",
  "max_tokens": 2048,
  "provider": "deepseek",
  "model": "deepseek-chat",
  "agent_mode": "graph"
}
```

> api_key and base_url automatically used from current user's database config, no need to pass from frontend.

## Tool List

| Tool | Function |
|------|----------|
| `calculator` | Mathematical expression calculation |
| `search` | Internet information retrieval |
| `weather` | City weather query |
| `file` | File read/write operations |
| `datetime` | Date/time and timers |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_PROVIDER` | `llama_cpp` | Default model Provider |
| `DEFAULT_AGENT_MODE` | `plan_execute` | Default Agent mode (plan_execute / react / chat) |
| `PORT` | `8000` | Service port |
| `SECRET_KEY` | `jarvis-secret-key-change-in-production` | API Key encryption key (change in production) |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model name |
| `MCP_CONFIG_PATH` | `backend/mcp/servers.json` | MCP server config file path |
| `MCP_CONNECT_TIMEOUT` | `60` | MCP server connection timeout (seconds) |

## Testing

```bash
# Install test dependencies
pip install -r tests/requirements-test.txt

# Run all unit tests
pytest tests/unit -v

# Run all tests (unit + integration)
pytest tests/unit tests/integration -v

# Run tests with coverage report
pytest tests/unit tests/integration --cov=backend

# Expected output:
# 63 passed, 2 xfailed (auth tests affected by rate limiting)
# Tool module coverage ≈ 90%
```

> Some auth integration tests may be skipped due to rate limiting (5 req/min).

## Development Mode

Frontend supports hot-reload development mode:

```bash
# Start frontend dev server
cd frontend
npm run dev
```

Visit `http://localhost:5173` to view frontend, backend still runs on `http://localhost:8000`.

## Theme Switching

Top-right corner provides 🌞/🌙 theme switching button:
- **Light Mode**: White background
- **Dark Mode**: Dark background

Theme state auto-saved to browser localStorage.

## License

MIT License
