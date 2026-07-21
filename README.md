# Jarvis AI Agent

> [English Version](README_EN.md)

一个基于 FastAPI + Vue3 的 AI Agent 智能助手系统，支持**本地 llama.cpp** 与**云端主流大模型**（DeepSeek、OpenAI、Kimi、智谱、通义千问等），具备任务规划、工具调用、记忆机制、会话管理等核心能力。

## 功能特性

- 🔐 **用户系统**：支持注册、登录、退出，密码校验（≥8 位，含字母+数字），每个用户独立的模型配置和记忆
- 🎯 **任务规划**：支持三种 Agent 模式，全部基于 LangGraph 有向图编排
  - **Plan & Execute**（默认）：先由 LLM 制定执行计划，再按并行分组逐步执行
  - **ReAct**：经典的思考→行动→观察循环，支持工具调用、错误反思与重试
  - **Chat**：纯对话模式，适用于不需要工具调用的日常聊天
- 🔄 **反思机制**：工具调用失败时自动重试与策略调整
- 🛠️ **工具调用**：支持计算器、搜索、天气、文件操作、日期时间等工具，支持**并行执行**多个工具
- 🧩 **插件系统**：工具作为插件存在，支持启用/禁用、安装/卸载管理
- 🧠 **记忆系统**：短期记忆（对话总结）与长期记忆（重要信息持久化），基于 SQLite + ChromaDB 向量存储，LLM 自动评估重要性（阈值 ≥ 6/10），embedding 模型自动后台下载
- 🔐 **API Key 加密**：使用 Fernet (PBKDF2) 对用户 API Key 进行加密存储
- 🔗 **MCP 协议支持**：集成 Model Context Protocol，支持 stdio 和 SSE 传输，可连接外部 MCP 服务器扩展工具能力
- ⚡ **流式输出**：支持 SSE (Server-Sent Events) 流式输出，逐 token 渲染，工具调用过程实时可见
- 💬 **多轮对话**：完整的上下文管理与智能截断策略
- 📁 **会话管理**：支持创建、切换、删除多个会话，自动标题预览，历史消息自动保存
- ☁️ **多模型支持**：本地 llama.cpp + 云端 OpenAI 兼容 API，前端可自由切换
- 🔄 **模型快捷切换**：顶部下拉框快速切换已配置的模型 Provider
- 🗄️ **数据库存储**：模型配置、记忆、会话通过 SQLite 持久化到服务端，换浏览器不丢失
- 🌓 **主题切换**：支持日间模式（白色背景）和夜间模式（深色背景）
- 📊 **性能监控**：实时显示响应时间、Tokens/s、输入/输出 Tokens 等指标
- 🚦 **频率限制**：登录/注册接口基于 slowapi 速率限制

## 支持的模型 Provider

| Provider | 说明 |
|----------|------|
| `llama_cpp` | 本地 llama.cpp 服务（无需 API Key）|
| `deepseek` | DeepSeek 云端 |
| `openai` | OpenAI GPT 系列 |
| `moonshot` | 月之暗面 Kimi |
| `zhipu` | 智谱 GLM |
| `dashscope` | 阿里云通义千问 |
| `siliconflow` | 硅基流动模型聚合 |
| `custom` | 自定义 OpenAI 兼容 API |

## 技术栈

- **后端**：Python 3.9+, FastAPI, SQLAlchemy, SQLite, ChromaDB（向量存储）
- **大模型**：llama.cpp（本地）/ OpenAI 兼容 API（云端）
- **Agent 框架**：LangGraph（有穷状态机图编排）
- **前端**：Vue 3 + Vite + Fetch API（SSE 流式读取）
- **认证**：JWT Token, bcrypt 密码加密
- **安全**：Fernet (PBKDF2) API Key 加密
- **部署**：Uvicorn

## 项目结构

```
Jarvis/
├── backend/
│   ├── graph_agent.py        # Agent 核心逻辑（基于 LangGraph，支持 chat / ReAct / Plan&Execute，含流式 run_stream）
│   ├── crypto_utils.py       # API Key 加密解密（Fernet + PBKDF2）
│   ├── auth.py               # 用户认证（JWT、密码哈希）
│   ├── database.py           # 数据库模型（User、ModelConfig、ShortTermMemory、LongTermMemory、Plugin、ChatSession）
│   ├── plugin_manager.py     # 插件管理器（安装/卸载/启停）
│   ├── routes/               # API 路由模块
│   │   ├── auth.py           #   认证接口
│   │   ├── chat.py           #   聊天 & Agent 接口
│   │   ├── config.py         #   模型配置接口
│   │   ├── memory.py         #   记忆接口
│   │   ├── mcp.py            #   MCP 管理接口
│   │   ├── plugins.py        #   插件管理接口
│   │   ├── session.py        #   会话管理接口
│   │   ├── tools.py          #   工具列表接口
│   │   └── helpers.py        #   公共辅助函数
│   ├── providers/            # 多模型 Provider 抽象
│   │   ├── registry.py       # Provider 注册表
│   │   ├── client.py         # 统一 LLM 客户端（同步/异步，含连接池）
│   │   └── __init__.py
│   ├── memory/               # 记忆系统
│   │   ├── __init__.py       # MemoryManager
│   │   ├── short_term.py     # 短期记忆（SQLite）
│   │   ├── long_term.py      # 长期记忆（SQLite + ChromaDB 向量检索）
│   │   ├── embeddings.py     # Embedding 生成（sentence-transformers，带 fallback 伪向量）
│   │   └── vector_store.py   # ChromaDB 向量存储封装
│   ├── tools/                # 工具集（默认插件）
│   │   ├── base.py           # 工具注册表（含 MCP 工具注册）
│   │   ├── calculator.py
│   │   ├── datetime_tool.py
│   │   ├── file_tool.py
│   │   ├── search.py
│   │   └── weather.py
│   └── mcp/                  # MCP (Model Context Protocol) 集成
│       ├── __init__.py
│       ├── manager.py        # MCP 服务器管理器（JSON-RPC 2.0，支持 stdio/SSE）
│       └── adapter.py        # MCP 工具适配器
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatPanel.vue      # 聊天面板（含 SSE 流式读取）
│   │   │   ├── SidebarLeft.vue    # 左侧导航栏（会话列表+导航，含 MCP 导航）
│   │   │   ├── SidebarRight.vue   # 右侧记忆+性能面板
│   │   │   ├── LoginPage.vue      # 登录/注册页面
│   │   │   ├── PluginPage.vue     # 插件管理页面
│   │   │   ├── MCPServerPage.vue  # MCP 服务器管理页面
│   │   │   └── SettingsPage.vue   # 设置页面
│   │   ├── App.vue                # 主应用组件
│   │   ├── main.js                # 入口文件
│   │   └── style.css              # 全局样式（含主题变量）
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── jsconfig.json
├── data/                     # 运行时数据
│   ├── jarvis.db             # SQLite 数据库
│   └── vectors/              # ChromaDB 向量存储
├── requirements.txt
├── Dockerfile               # 多阶段构建（前端 + 后端），含 HEALTHCHECK + 非 root 用户
├── docker-compose.yml       # Docker Compose 配置（含健康检查、持久化卷）
├── .dockerignore
├── .env.example             # 环境变量示例
├── pytest.ini               # 测试配置
├── .coveragerc              # 覆盖率配置
├── tests/                   # 测试目录
│   ├── unit/                #   单元测试
│   └── integration/         #   集成测试
├── README.md
└── README_EN.md
```

## 快速开始

### 1. 克隆项目

```bash
git clone <repo-url>
cd Jarvis
```

### 2. 安装后端依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 安装前端依赖并构建

```bash
cd frontend
npm install
npm run build
```

### 4. 启动服务

```bash
# 使用虚拟环境的 Python 启动
# 方式一（推荐）
uvicorn backend.main:app --reload

# 方式二
venv/bin/python backend/main.py
```

### 5. 使用

访问 `http://localhost:8000`：

1. **注册账号** → 首次使用先注册（密码 ≥ 8 位，需包含字母和数字）
2. **登录系统** → 使用注册的账号登录
3. **配置模型** → 左侧栏 ⚙️ 设置中配置 Provider、API Key（Key 加密存储）
4. **开始对话** → 在聊天面板输入消息，支持流式输出

## Docker 部署

```bash
# 1. 配置环境变量（修改 SECRET_KEY 和其他配置）
cp .env.example .env
# 编辑 .env 文件，填入你的 SECRET_KEY 和 LLM 配置

# 2. 启动服务（自动构建前端 + 后端）
docker compose up -d

# 3. 查看日志
docker compose logs -f

# 4. 停止服务
docker compose down
```

访问 `http://localhost:8000` 使用。

> **注意事项：**
> - 本地 llama.cpp 服务在 Docker 中访问请使用 `host.docker.internal`
> - 数据持久化在 `./data/` 目录（SQLite + ChromaDB 向量库）
> - Embedding 模型缓存保存在 Docker 卷 `embedding_cache` 中
> - Docker 镜像内置 HEALTHCHECK 健康检查和 `init: true` 优雅关闭机制
> - 容器以非 root 用户运行，增强安全性

### 中国大陆加速

Docker Hub 在国内访问不稳定，需要配置 **Docker daemon registry mirror**：

**第一步：配置镜像加速器**

打开 Docker Desktop → **Settings** → **Docker Engine**，在 `daemon.json` 中加入：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://hub-mirror.c.163.com"
  ]
}
```

点击 **Apply & Restart**。

> 如果上述镜像都不可用，参考 [Docker 官方文档](https://docs.docker.com/engine/daemon/#configure-mirrors) 配置其他镜像源。

**第二步：构建并启动**

```bash
cp .env.example .env
# 中国大陆用户可取消 .env 中 PIP_INDEX_URL 注释使用清华源
docker compose build
docker compose up -d
```

## 用户系统

Jarvis 内置了用户认证系统：

| 功能 | 说明 |
|------|------|
| 注册 | 填写用户名、邮箱和密码注册（密码 ≥ 8 位，含字母+数字） |
| 登录 | JWT Token 认证，有效期 30 天；接口有速率限制 |
| 退出 | 清除 Token，返回登录页面 |
| 模型配置 | 每个用户独立管理自己的模型配置（API Key 加密存储） |
| 记忆隔离 | 每个用户拥有独立的短期/长期记忆 |

> 所有用户数据（密码哈希、模型配置、记忆）存储在服务端 SQLite 数据库中，换浏览器或清除缓存不会丢失。

## Agent 模式

Jarvis 支持三种 Agent 模式，可在设置页面或请求参数中选择：

| 模式 | 说明 |
|------|------|
| `plan_execute`（默认） | 基于 LangGraph，LLM 分析任务并制定包含并行分组的执行计划，再按组并行/串行执行。支持工具并行调用与反思 |
| `react` | 基于 LangGraph，经典的 ReAct（思考→行动→观察）循环模式，支持工具猜测、并行执行、错误反思与重试 |
| `chat` | 基于 LangGraph，纯对话模式，适用于不需要工具调用的日常聊天。流程：LLM 调用 → 记忆更新 |

> 默认模式可通过环境变量 `DEFAULT_AGENT_MODE` 配置。

## 插件系统

Jarvis 的插件系统将工具以插件形式管理，支持启用/禁用、安装和卸载。

### 默认插件

| 图标 | 插件 | 说明 | 类型 |
|------|------|------|------|
| 🔢 | 计算器 | 数学表达式计算 | 默认 |
| 🔍 | 搜索引擎 | 互联网信息检索 | 默认 |
| 🌤️ | 天气预报 | 城市天气查询 | 默认 |
| 📁 | 文件操作 | 文件读写操作 | 默认 |
| ⏰ | 日期时间 | 获取时间/设置定时器 | 默认 |

### 插件管理

插件管理页面（左侧栏导航 → 🧩 插件）支持：

- **查看插件列表**：展示已安装的所有插件
- **启用/禁用**：通过开关切换插件启停
- **安装插件**：填写插件信息即可安装新插件
- **卸载插件**：非默认插件可完全卸载

### 插件 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/plugins` | GET | 获取所有插件列表 |
| `/api/plugins/enabled` | GET | 获取已启用的插件 |
| `/api/plugins/{id}/toggle` | PUT | 切换插件启停状态 |
| `/api/plugins` | POST | 安装新插件 |
| `/api/plugins/{id}` | DELETE | 卸载插件 |

## MCP（Model Context Protocol）集成

Jarvis 支持 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)，可连接外部 MCP 服务器扩展工具能力。

### 传输类型

| 类型 | 说明 |
|------|------|
| `stdio` | 通过子进程 stdin/stdout 通信（本地命令启动） |
| `sse` | 通过 HTTP POST + SSE 通信（远程服务） |

### 配置方式

创建 `backend/mcp/servers.json` 文件：

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

MCP 配置路径可通过环境变量 `MCP_CONFIG_PATH` 自定义。

### MCP 管理页面

左侧栏导航 → 🔗 MCP 服务器，可查看已连接的 MCP 服务器列表及其工具。

### MCP 管理 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/mcp/servers` | GET | 获取所有 MCP 服务器连接状态 |
| `/api/mcp/tools` | GET | 获取所有 MCP 工具列表 |
| `/api/mcp/servers/reload` | POST | 重新加载 MCP 配置并重连所有服务器 |
| `/api/mcp/servers/{name}/reconnect` | POST | 重连指定的 MCP 服务器 |
| `/api/mcp/servers/{name}` | PUT | 更新 MCP 服务器配置 |
| `/api/mcp/servers/{name}` | DELETE | 删除 MCP 服务器配置 |

## 模型管理

### 模型快捷切换（顶部）

顶部 Header 右侧显示**模型快捷切换**下拉框，仅列出已配置的 Provider，点击即可切换，切换后该 Provider 的配置（API Key、模型、base_url 等）自动生效。

### 模型设置面板（左侧栏 ⚙️）

在左侧栏设置页面中可以：

- **选择 Provider**：从可用 Provider 列表中选择
- **配置 API Key / Base URL**：填写服务端连接信息（API Key 加密存储）
- **选择模型**：从 Provider 支持的模型列表中选择（支持动态获取官网模型列表）
- **配置最大 Token 数**、Agent 模式（plan_execute / react / chat）
- 已配置的 Provider 显示 ✓ 和「已配置」标签

### 配置流程

```
首次使用
    ↓
左侧栏 ⚙️ 设置 → 选择 Provider（如 DeepSeek）
    ↓
填写 API Key → 选择模型 → 点击保存（Key 加密存储）
    ↓
配置持久化到 SQLite 数据库
    ↓
顶部快捷切换下拉框自动出现该 Provider
    ↓
后续使用可直接在顶部切换，无需再次配置
```

## 记忆系统

| 类型 | 存储方式 | 检索方式 | 用户隔离 | 特性 |
|------|----------|----------|----------|------|
| 短期记忆 | SQLite `short_term_memories` 表 | 直接读取 | ✅ 每个用户独立 | 每 N 轮对话自动生成总结，自动覆盖最旧的 |
| 长期记忆 | SQLite `long_term_memories` 表 + ChromaDB 向量索引 | 语义向量检索（top_k=3） | ✅ 每个用户独立 | LLM 自动评估重要性（阈值 ≥ 6/10），向量去重（相似度 ≥ 0.85 跳过），时间衰减排序（30 天半衰期） |

记忆由 Agent 自动管理：

- 对话过程中 Agent 自动生成短期总结
- 每次对话完成后，LLM 分析对话内容并评分（1-10 分）
- 重要性 ≥ 6 的信息自动提取为长期记忆，存入 SQLite + ChromaDB
- embedding 模型（默认 all-MiniLM-L6-v2）后台自动下载，不可用时自动降级为伪向量模式
- 每次对话前自动检索相关记忆（向量相似度检索）作为上下文
- 右侧面板可查看和管理所有记忆

## 流式输出

Jarvis 支持完整的 SSE (Server-Sent Events) 流式输出：

- **逐 token 渲染**：LLM 生成的每个 token 实时推送到前端
- **工具调用可视化**：工具调用、执行、反思过程实时展示
- **事件类型**：`token`（文本）、`thinking`（思考）、`tool_call`（工具调用）、`tool_result`（工具结果）、`summary_start`（开始总结）、`done`（完成）、`error`（错误）

## 界面布局

### 左侧栏
- **头部**：Jarvis Logo + AI Assistant 标识
- **导航**：💬 对话 / 🧩 插件 / 🔗 MCP 服务器 / ⚙️ 设置（垂直排列）
- **聊天页面**：会话列表 + 操作按钮（新建/保存/清空）
- **插件/MCP/设置页面**：空白区域

### 中间区域
- **对话页面**：ChatPanel 聊天界面
- **插件页面**：PluginPage 插件管理界面
- **MCP 页面**：MCPServerPage MCP 管理界面
- **设置页面**：SettingsPage 模型配置界面

### 右侧栏（仅聊天页面）
- **记忆系统**：短期/长期记忆查看与管理（清空、单条删除）
- **性能指标**：响应时间、Tokens/s、输入/输出 Tokens 等

## API 接口

### 认证接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/auth/register` | POST | 用户注册（密码 ≥ 8 位，含字母+数字；5 次/分钟限流） |
| `/api/auth/login` | POST | 用户登录（返回 JWT Token；10 次/分钟限流） |
| `/api/auth/logout` | POST | 用户退出 |
| `/api/auth/me` | GET | 获取当前用户信息 |

### 模型配置接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/providers` | GET | 获取可用 Provider 列表 |
| `/api/user/config` | GET | 获取当前用户的模型配置列表 |
| `/api/user/config` | POST | 保存当前用户的模型配置（含 agent_mode） |
| `/api/user/config/{id}` | DELETE | 删除指定模型配置 |
| `/api/models` | GET | 获取指定 Provider 的模型列表 |

### 对话接口（流式）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/chat/stream` | POST | 基础聊天（SSE 流式） |
| `/api/agent/stream` | POST | Agent 聊天，支持工具调用（SSE 流式） |
| `/api/chat` | POST | 基础聊天（非流式，兼容旧版） |
| `/api/agent` | POST | Agent 聊天（非流式，兼容旧版） |
| `/api/health` | GET | 健康检查（支持 `?provider=deepseek`） |

### 会话接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/session` | POST | 创建会话 |
| `/api/sessions` | GET | 获取会话列表（含标题/预览） |
| `/api/session/{id}` | GET | 获取会话详情 |
| `/api/session/{id}` | DELETE | 删除会话 |

### 工具 / 记忆接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/tools` | GET | 获取工具列表 |
| `/api/memory` | GET | 获取当前用户的长期记忆 |
| `/api/memory` | POST | 手动添加长期记忆 |
| `/api/memory/stats` | GET | 获取记忆统计（短期/长期数量、总 tokens） |
| `/api/memory` | DELETE | 清空当前用户的所有记忆（含短期+长期+向量） |
| `/api/memory/{memory_id}` | DELETE | 删除指定长期记忆 |
| `/api/memory/search` | GET | 语义搜索长期记忆 |

### MCP 管理接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/mcp/servers` | GET | 获取所有 MCP 服务器连接状态 |
| `/api/mcp/tools` | GET | 获取所有 MCP 工具列表 |
| `/api/mcp/servers/reload` | POST | 重新加载 MCP 配置并重连 |
| `/api/mcp/servers/{name}/reconnect` | POST | 重连指定 MCP 服务器 |
| `/api/mcp/servers/{name}` | PUT | 更新 MCP 服务器配置 |
| `/api/mcp/servers/{name}` | DELETE | 删除 MCP 服务器 |

### 请求参数（stream 端点）

```json
{
  "messages": [{"role": "user", "content": "你好"}],
  "session_id": "your-session-id",
  "max_tokens": 2048,
  "provider": "deepseek",
  "model": "deepseek-chat",
  "agent_mode": "graph"
}
```

> api_key 和 base_url 由后端自动使用当前用户的数据库配置，无需前端传入。

## 工具列表

| 工具 | 功能 |
|------|------|
| `calculator` | 数学表达式计算 |
| `search` | 互联网信息检索 |
| `weather` | 城市天气查询 |
| `file` | 文件读写操作 |
| `datetime` | 日期时间与定时器 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEFAULT_PROVIDER` | `llama_cpp` | 默认模型 Provider |
| `DEFAULT_AGENT_MODE` | `plan_execute` | 默认 Agent 模式（plan_execute / react / chat） |
| `PORT` | `8000` | 服务端口 |
| `SECRET_KEY` | `jarvis-secret-key-change-in-production` | API Key 加密密钥（生产环境请修改） |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding 模型名称 |
| `MCP_CONFIG_PATH` | `backend/mcp/servers.json` | MCP 服务器配置文件路径 |
| `MCP_CONNECT_TIMEOUT` | `60` | MCP 服务器连接超时（秒） |

## 测试

```bash
# 安装测试依赖
pip install -r tests/requirements-test.txt

# 运行全部单元测试
pytest tests/unit -v

# 运行所有测试（含集成测试）
pytest tests/unit tests/integration -v

# 运行测试并生成覆盖率报告
pytest tests/unit tests/integration --cov=backend

# 输出示例：
# 63 passed, 2 xfailed (部分 auth 测试受限流影响)
# 工具模块覆盖率 ≈ 90%
```

> 集成测试中的部分 auth 用例受速率限制影响（5 次/分钟），在 CI 环境中自动跳过。

## 开发模式

前端支持热更新开发模式：

```bash
# 启动前端开发服务器
cd frontend
npm run dev
```

访问 `http://localhost:5173` 查看前端，后端仍需运行在 `http://localhost:8000`。

## 主题切换

页面右上角提供 🌞/🌙 主题切换按钮：
- **日间模式**：白色背景
- **夜间模式**：深色背景

主题状态自动保存到浏览器 localStorage。

## 许可证

MIT License
