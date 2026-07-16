# Jarvis AI Agent

> [中文版](README.md)

An AI Agent intelligent assistant system based on FastAPI + Vue3, supporting **local llama.cpp** and **cloud-based LLMs** (DeepSeek, OpenAI, Kimi, GLM, Qwen, etc.), featuring task planning, tool calling, memory mechanisms, session management, and user authentication.

## Features

- 🔐 **User System**: Register, login, logout with per-user independent model configuration and memory
- 🎯 **Task Planning**: Based on ReAct mode, decomposes complex tasks into subtasks and formulates execution plans
- 🔄 **Reflection Mechanism**: Automatically retries and adjusts strategies when tool calls fail
- 🛠️ **Tool Calling**: Supports calculator, search, weather, file operations, date/time tools
- 🧩 **Plugin System**: Tools managed as plugins with enable/disable, install/uninstall capabilities
- 🧠 **Memory System**: Short-term (conversation summaries) and long-term (important info persistence) memory, SQLite backed, per-user isolation
- 💬 **Multi-turn Conversation**: Complete context management with intelligent truncation strategy
- 📁 **Session Management**: Create, switch, delete sessions with auto-save; session list refreshes in real-time
- ☁️ **Multi-model Support**: Local llama.cpp + cloud OpenAI-compatible APIs, freely switchable in frontend
- 🔄 **Quick Model Switching**: Dropdown in header to quickly switch between configured Providers
- 🗄️ **Database Storage**: Model configs, memories, sessions persisted in SQLite, survives browser changes
- 🌓 **Theme Switching**: Supports light mode (white background) and dark mode (dark background)
- 📊 **Performance Monitoring**: Real-time display of response time, Tokens/s, input/output Tokens

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

- **Backend**: Python 3.9+, FastAPI, SQLAlchemy, SQLite
- **LLMs**: llama.cpp (local) / OpenAI-compatible APIs (cloud)
- **Frontend**: Vue 3 + Vite + Axios
- **Auth**: JWT Token, bcrypt password hashing
- **Deployment**: Uvicorn

## Project Structure

```
Jarvis/
├── backend/
│   ├── agent.py              # Core Agent logic
│   ├── graph_agent.py        # Graph Agent logic
│   ├── providers/            # Multi-model Provider abstraction
│   │   ├── registry.py       # Provider registry (hardcoded default configs)
│   │   ├── client.py         # Unified LLM client
│   │   └── __init__.py
│   ├── memory/               # Memory system (SQLite persistence, user isolation)
│   │   ├── __init__.py       # MemoryManager
│   │   ├── short_term.py     # Short-term memory
│   │   └── long_term.py      # Long-term memory (keyword matching search)
│   ├── tools/                # Tool set (default plugins)
│   │   ├── base.py
│   │   ├── calculator.py
│   │   ├── datetime_tool.py
│   │   ├── file_tool.py
│   │   ├── search.py
│   │   └── weather.py
│   ├── database.py            # Database models (User, ModelConfig, ShortTermMemory, LongTermMemory, Plugin)
│   ├── auth.py                # User authentication (JWT, password hashing)
│   ├── plugin_manager.py      # Plugin manager (install/uninstall/enable/disable)
│   └── __init__.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatPanel.vue      # Chat panel
│   │   │   ├── SidebarLeft.vue    # Left sidebar (session list + navigation)
│   │   │   ├── SidebarRight.vue   # Right sidebar (memory + performance)
│   │   │   ├── LoginPage.vue      # Login/Registration page
│   │   │   ├── PluginPage.vue     # Plugin management page
│   │   │   └── SettingsPage.vue   # Settings page
│   │   ├── App.vue                # Main app component
│   │   ├── main.js                # Entry file
│   │   └── style.css              # Global styles (with theme variables)
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── jsconfig.json
├── main.py                 # FastAPI main app (API routes)
├── session_manager.py      # Session management
├── context_manager.py      # Context management
├── requirements.txt
├── README.md
└── README_EN.md
```

## Quick Start

### 1. Install Backend Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Frontend Dependencies

```bash
cd frontend
npm install
```

### 3. Build Frontend

```bash
cd frontend
npm run build
```

### 4. Start Service

```bash
python3 main.py
```

### 5. Usage

Visit `http://localhost:8000`:

1. **Register Account** → Register first time
2. **Login System** → Use registered credentials
3. **Configure Model** → Left sidebar ⚙️ settings to configure Provider, API Key
4. **Start Chatting** → Input messages in chat panel

## User System

Jarvis has built-in user authentication:

| Feature | Description |
|---------|-------------|
| Registration | Fill username and password to register |
| Login | JWT Token authentication, 30-day validity |
| Logout | Clear Token, return to login page |
| Model Config | Each user manages their own model configs |
| Memory Isolation | Each user has independent short/long-term memory |

> All user data (password hashes, model configs, memories) stored in server SQLite database, survives browser changes or cache clearing.

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

## Model Management

### Quick Model Switching (Header)

Header shows **quick model switching** dropdown with only configured Providers, click to switch, Provider configs (API Key, model, base_url) automatically apply.

### Model Settings Panel (Left Sidebar ⚙️)

In left sidebar settings page you can:

- **Select Provider**: Choose from available Provider list
- **Configure API Key / Base URL**: Fill server connection info
- **Select Model**: Choose from Provider's supported model list (supports dynamic fetching)
- **Configure Max Tokens**, Agent mode etc.
- Configured Providers show ✓ and "Configured" label

### Configuration Flow

```
First time use
    ↓
Left sidebar ⚙️ settings → Select Provider (e.g., DeepSeek)
    ↓
Fill API Key → Select Model → Click save
    ↓
Config persisted to SQLite database
    ↓
Top quick switch dropdown automatically shows that Provider
    ↓
Subsequent use can directly switch in top, no reconfiguration needed
```

## Memory System

| Type | Storage | User Isolation | Features |
|------|---------|----------------|----------|
| Short-term | SQLite `short_term_memories` table | ✅ Per user | Recent 10 conversation summaries, auto-overwrite oldest |
| Long-term | SQLite `long_term_memories` table | ✅ Per user | Keyword matching search, access frequency tracking |

Memory is automatically managed by Agent:
- Agent generates short-term summaries during conversations
- Important info extracted as long-term memory
- Related memory retrieved as context before each conversation

## Interface Layout

### Left Sidebar
- **Header**: Jarvis Logo + AI Assistant identifier
- **Navigation**: 💬 Chat / 🧩 Plugins / ⚙️ Settings (vertical)
- **Chat Page**: Session list + action buttons (new/save/clear)
- **Plugins/Settings Pages**: Empty area

### Center Area
- **Chat Page**: ChatPanel interface
- **Plugins Page**: Plugin management interface
- **Settings Page**: Model configuration interface

### Right Sidebar (Chat Page Only)
- **Memory System**: View/manage short/long-term memory
- **Performance Metrics**: Response time, Tokens/s, input/output Tokens etc.

## API Interfaces

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | User registration |
| `/api/auth/login` | POST | User login (returns JWT Token) |
| `/api/auth/logout` | POST | User logout |
| `/api/auth/me` | GET | Get current user info |

### Model Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/providers` | GET | Get available Providers list |
| `/api/user/config` | GET | Get current user's model configs |
| `/api/user/config` | POST | Save current user's model config |
| `/api/user/config/{id}` | DELETE | Delete specific model config |
| `/api/models` | GET | Get models for specific Provider |

### Chat

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Basic chat |
| `/api/agent` | POST | Agent chat (with tool calling) |
| `/api/health` | GET | Health check (supports `?provider=deepseek`) |

### Sessions

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/session` | POST | Create session |
| `/api/sessions` | GET | Get session list |
| `/api/session/{id}` | GET | Get session details |
| `/api/session/{id}` | DELETE | Delete session |

### Tools / Memory

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tools` | GET | Get tool list |
| `/api/memory` | GET | Get current user's memory |
| `/api/memory` | POST | Store memory |
| `/api/memory/{memory_id}` | DELETE | Delete specific memory |
| `/api/memory/search` | GET | Search memory |
| `/api/memory/stats` | GET | Get memory statistics |

### Request Parameters (chat / agent)

```json
{
  "messages": [{"role": "user", "content": "Hello"}],
  "session_id": "your-session-id",
  "max_tokens": 2048,
  "provider": "deepseek",
  "model": "deepseek-chat"
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