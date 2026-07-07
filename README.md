# Jarvis AI Agent

一个基于 FastAPI 和 llama.cpp 的 AI Agent 智能助手系统，具备任务规划、工具调用、记忆机制等核心能力。

## 功能特性

- 🎯 **任务规划**：基于 ReAct 模式，将复杂任务分解为子任务，制定执行计划
- 🔄 **反思机制**：工具调用失败时自动重试与策略调整
- 🛠️ **工具调用**：支持计算器、搜索、天气、文件操作、日期时间等工具
- 🧠 **记忆系统**：短期记忆（对话总结）与长期记忆（重要信息持久化）
- 💬 **多轮对话**：完整的上下文管理与智能截断策略

## 技术栈

- **后端**：Python 3.9+, FastAPI
- **大模型**：llama.cpp (GGUF 格式)
- **前端**：HTML/CSS/JavaScript
- **部署**：Uvicorn

## 项目结构

```
Jarvis/
├── backend/
│   ├── agent.py          # Agent 核心逻辑
│   ├── memory/           # 记忆系统
│   │   ├── __init__.py
│   │   ├── short_term.py
│   │   └── long_term.py
│   └── tools/            # 工具集
│       ├── base.py
│       ├── calculator.py
│       ├── datetime_tool.py
│       ├── file_tool.py
│       ├── search.py
│       └── weather.py
├── templates/
│   └── index.html        # 前端界面
├── main.py               # FastAPI 主应用
├── session_manager.py    # 会话管理
├── context_manager.py    # 上下文管理
└── requirements.txt      # 依赖列表
```

## 快速开始

### 1. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置 llama.cpp 服务

确保 llama.cpp 服务器已启动：

```bash
# 示例：启动 llama.cpp 服务器
cd /path/to/llama.cpp
./server -m models/your-model.gguf -c 4096 --host 192.168.0.201 --port 8081
```

### 3. 启动服务

```bash
python3 main.py
```

服务将运行在 `http://localhost:8000`

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端界面 |
| `/api/chat` | POST | 基础聊天 |
| `/api/agent` | POST | Agent 聊天（支持工具调用） |
| `/api/tools` | GET | 获取工具列表 |
| `/api/session` | POST | 创建会话 |
| `/api/session/{id}` | GET/DELETE | 获取/删除会话 |
| `/api/memory` | GET/POST/DELETE | 记忆管理 |

## 工具列表

| 工具 | 功能 |
|------|------|
| `calculator` | 数学表达式计算 |
| `search` | 互联网信息检索 |
| `weather` | 城市天气查询 |
| `file` | 文件读写操作 |
| `datetime` | 日期时间与定时器 |

## 配置说明

在 `main.py` 中修改配置：

```python
LLAMA_CPP_URL = "http://192.168.0.201:8081"  # llama.cpp 服务器地址
MAX_CONTEXT_TOKENS = 8192                     # 最大上下文 Token 数
```

## 许可证

MIT License