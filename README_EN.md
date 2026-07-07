# Jarvis AI Agent

An AI Agent intelligent assistant system based on FastAPI and llama.cpp, featuring task planning, tool calling, and memory mechanisms.

## Features

- 🎯 **Task Planning**: Based on ReAct mode, decomposes complex tasks into subtasks and formulates execution plans
- 🔄 **Reflection Mechanism**: Automatically retries and adjusts strategies when tool calls fail
- 🛠️ **Tool Calling**: Supports calculator, search, weather, file operations, date/time tools
- 🧠 **Memory System**: Short-term memory (conversation summarization) and long-term memory (important information persistence)
- 💬 **Multi-turn Conversation**: Complete context management with intelligent truncation strategy

## Tech Stack

- **Backend**: Python 3.9+, FastAPI
- **LLM**: llama.cpp (GGUF format)
- **Frontend**: HTML/CSS/JavaScript
- **Deployment**: Uvicorn

## Project Structure

```
Jarvis/
├── backend/
│   ├── agent.py          # Agent core logic
│   ├── memory/           # Memory system
│   │   ├── __init__.py
│   │   ├── short_term.py
│   │   └── long_term.py
│   └── tools/            # Toolset
│       ├── base.py
│       ├── calculator.py
│       ├── datetime_tool.py
│       ├── file_tool.py
│       ├── search.py
│       └── weather.py
├── templates/
│   └── index.html        # Frontend interface
├── main.py               # FastAPI main application
├── session_manager.py    # Session management
├── context_manager.py    # Context management
└── requirements.txt      # Dependency list
```

## Quick Start

### 1. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure llama.cpp Service

Ensure llama.cpp server is running:

```bash
# Example: Start llama.cpp server
cd /path/to/llama.cpp
./server -m models/your-model.gguf -c 4096 --host 192.168.0.201 --port 8081
```

### 3. Start the Service

```bash
python3 main.py
```

The service will run at `http://localhost:8000`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Frontend interface |
| `/api/chat` | POST | Basic chat |
| `/api/agent` | POST | Agent chat (with tool calling) |
| `/api/tools` | GET | Get tool list |
| `/api/session` | POST | Create session |
| `/api/session/{id}` | GET/DELETE | Get/delete session |
| `/api/memory` | GET/POST/DELETE | Memory management |

## Tool List

| Tool | Function |
|------|----------|
| `calculator` | Mathematical expression calculation |
| `search` | Internet information retrieval |
| `weather` | City weather query |
| `file` | File read/write operations |
| `datetime` | Date/time and timer |

## Configuration

Modify settings in `main.py`:

```python
LLAMA_CPP_URL = "http://192.168.0.201:8081"  # llama.cpp server address
MAX_CONTEXT_TOKENS = 8192                     # Maximum context tokens
```

## License

MIT License