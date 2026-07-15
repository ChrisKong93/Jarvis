# Jarvis AI Agent

An AI Agent intelligent assistant system based on FastAPI + Vue3, supporting **local llama.cpp** and **cloud-based LLMs** (DeepSeek, OpenAI, Kimi, GLM, Qwen, etc.), featuring task planning, tool calling, memory mechanisms, session management, and user authentication.

## Features

- 🔐 **User System**: Register, login, logout with per-user independent model configuration
- 🎯 **Task Planning**: Based on ReAct mode, decomposes complex tasks into subtasks and formulates execution plans
- 🔄 **Reflection Mechanism**: Automatically retries and adjusts strategies when tool calls fail
- 🛠️ **Tool Calling**: Supports calculator, search, weather, file operations, date/time tools
- 🧠 **Memory System**: Short-term memory (conversation summarization) and long-term memory (important information persistence)
- 💬 **Multi-turn Conversation**: Complete context management with intelligent truncation strategy
- 📁 **Session Management**: Create, switch, and delete multiple sessions, with automatic history message saving
- ☁️ **Multi-model Support**: Local llama.cpp + cloud OpenAI-compatible APIs, freely switchable in frontend
- 🔄 **Quick Model Switching**: Dropdown in header to quickly switch between configured Providers
- 🗄️ **Database Storage**: Model configs persisted in SQLite on server side, survives browser changes
- 🌓 **Theme Switching**: Supports light mode (white background) and dark mode (dark background)

## Supported Model Providers

| Provider | Description |
|----------|-------------|
| `llama_cpp` | Local llama.cpp service |
| `deepseek` | DeepSeek Cloud |
| `openai` | OpenAI GPT Series |
| `moonshot` | Moonshot (Kimi) |
| `zhipu` | Zhipu GLM |
| `dashscope` | Aliyun Qwen |
| `siliconflow` | SiliconFlow |
| `custom` | Custom OpenAI-compatible API |

## Tech Stack

- **Backend**: Python 3.9+, FastAPI, SQLAlchemy, SQLite
- **LLM**: llama.cpp (local) / OpenAI-compatible API (cloud)
- **Frontend**: Vue 3 + Vite + Axios
- **Authentication**: JWT Token, bcrypt password hashing
- **Deployment**: Uvicorn

## Project Structure

```
Jarvis/
├── backend/
│   ├── agent.py              # Agent core logic
│   ├── graph_agent.py        # Graph Agent logic
│   ├── providers/            # Multi-model Provider abstraction
│   │   ├── registry.py       # Provider registry
│   │   ├── client.py         # Unified LLM client
│   │   └── __init__.py
│   ├── memory/               # Memory system
│   │   ├── __init__.py
│   │   ├── short_term.py
│   │   └── long_term.py
│   ├── tools/                # Toolset
│   │   ├── base.py
│   │   ├── calculator.py
│   │   ├── datetime_tool.py
│   │   ├── file_tool.py
│   │   ├── search.py
│   │   └── weather.py
│   ├── config/
│   │   └── providers.yaml     # Provider template config
│   ├── database.py            # Database models (User, ModelConfig)
│   ├── auth.py                # User authentication (JWT, password hash)
│   └── __init__.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatPanel.vue      # Chat panel
│   │   │   ├── SidebarLeft.vue    # Left sidebar (session list)
│   │   │   ├── SidebarRight.vue   # Right sidebar (model management)
│   │   │   └── LoginPage.vue      # Login/Register page
│   │   ├── App.vue                # Main application component
│   │   ├── main.js                # Entry file
│   │   └── style.css              # Global styles (with theme variables)
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── jsconfig.json
├── main.py                 # FastAPI main application
├── session_manager.py      # Session management
├── context_manager.py      # Context management
├── requirements.txt
└── README.md
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

### 4. Start the Service

```bash
python3 main.py
```

### 5. Usage

Visit `http://localhost:8000`:

1. **Register** → First time users need to register
2. **Login** → Login with your credentials
3. **Configure Model** → Click ⚙️ Settings in top right to configure Provider, API Key
4. **Start Chatting** → Enter messages in the chat panel

## User System

Jarvis has a built-in user authentication system:

| Feature | Description |
|---------|-------------|
| Register | Create account with username and password |
| Login | JWT Token authentication, valid for 30 days |
| Logout | Clear Token, return to login page |
| Model Config | Each user manages their own model configurations independently |

> Model configuration (API Key, Base URL, etc.) is stored in the server-side SQLite database. It persists across browser changes and cache clears.

## Model Management

### Quick Model Switching (Header)

The **Quick Model Switch** dropdown in the header shows only configured Providers. Click to switch instantly.

### Model Settings Panel (⚙️ Right Sidebar)

In the settings panel you can:

- **Select Provider**: Choose from available Providers
- **Configure API Key / Base URL**: Fill in server connection information
- **Select Model**: Choose from the Provider's supported model list
- **Configure Max Tokens**, Agent Mode, etc.

## Model Provider Configuration Flow

```
First Use
    ↓
⚙️ Settings → Select Provider (e.g., DeepSeek)
    ↓
Fill API Key → Select Model → Click Save
    ↓
Configuration persisted to SQLite database
    ↓
Provider appears in quick switch dropdown
    ↓
Subsequent use: switch directly from header, no re-configuration needed
```

## API Endpoints

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
| `/api/providers` | GET | Get available Provider list |
| `/api/user/config` | GET | Get current user's model configs |
| `/api/user/config` | POST | Save current user's model config |
| `/api/user/config/{id}` | DELETE | Delete specified model config |
| `/api/models` | GET | Get model list for specified Provider |

### Chat

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Basic chat |
| `/api/agent` | POST | Agent chat (with tool calling) |
| `/api/health` | GET | Health check (supports `?provider=deepseek`) |

### Session

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/session` | POST | Create session |
| `/api/sessions` | GET | Get session list |
| `/api/session/{id}` | GET | Get session details |
| `/api/session/{id}` | DELETE | Delete session |
| `/api/session/{id}/save` | POST | Save session record |

### Tools / Memory

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tools` | GET | Get tool list |
| `/api/memory` | GET | Get memory content |
| `/api/memory` | POST | Store memory |
| `/api/memory` | DELETE | Clear memory |
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

> api_key and base_url are automatically used from the current user's database configuration, no need to pass from frontend.

## Tool List

| Tool | Function |
|------|----------|
| `calculator` | Mathematical expression calculation |
| `search` | Internet information retrieval |
| `weather` | City weather query |
| `file` | File read/write operations |
| `datetime` | Date/time and timer |

## Development Mode

Frontend supports hot-reload development mode:

```bash
# Start frontend development server
cd frontend
npm run dev
```

Access `http://localhost:5173` for the frontend, backend still needs to run on `http://localhost:8000`.

## Theme Switching

🌞/🌙 toggle button in the top right corner:
- **Light Mode**: White background
- **Dark Mode**: Dark background

Theme preference is automatically saved to localStorage.

## License

MIT License
