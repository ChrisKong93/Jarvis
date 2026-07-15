# Jarvis AI Agent

一个基于 FastAPI + Vue3 的 AI Agent 智能助手系统，支持**本地 llama.cpp** 与**云端主流大模型**（DeepSeek、OpenAI、Kimi、智谱、通义千问等），具备任务规划、工具调用、记忆机制、会话管理等核心能力。

## 功能特性

- 🔐 **用户系统**：支持注册、登录、退出，每个用户独立的模型配置
- 🎯 **任务规划**：基于 ReAct 模式，将复杂任务分解为子任务，制定执行计划
- 🔄 **反思机制**：工具调用失败时自动重试与策略调整
- 🛠️ **工具调用**：支持计算器、搜索、天气、文件操作、日期时间等工具
- 🧠 **记忆系统**：短期记忆（对话总结）与长期记忆（重要信息持久化）
- 💬 **多轮对话**：完整的上下文管理与智能截断策略
- 📁 **会话管理**：支持创建、切换、删除多个会话，历史消息自动保存
- ☁️ **多模型支持**：本地 llama.cpp + 云端 OpenAI 兼容 API，前端可自由切换
- 🔄 **模型快捷切换**：顶部下拉框快速切换已配置的模型 Provider
- 🗄️ **数据库存储**：模型配置通过 SQLite 持久化到服务端，换浏览器不丢失
- 🌓 **主题切换**：支持日间模式（白色背景）和夜间模式（深色背景）

## 支持的模型 Provider

| Provider | 说明 |
|----------|------|
| `llama_cpp` | 本地 llama.cpp 服务 |
| `deepseek` | DeepSeek 云端 |
| `openai` | OpenAI GPT 系列 |
| `moonshot` | 月之暗面 Kimi |
| `zhipu` | 智谱 GLM |
| `dashscope` | 阿里云通义千问 |
| `siliconflow` | 硅基流动模型聚合 |
| `custom` | 自定义 OpenAI 兼容 API |

## 技术栈

- **后端**：Python 3.9+, FastAPI, SQLAlchemy, SQLite
- **大模型**：llama.cpp（本地）/ OpenAI 兼容 API（云端）
- **前端**：Vue 3 + Vite + Axios
- **认证**：JWT Token, bcrypt 密码加密
- **部署**：Uvicorn

## 项目结构

```
Jarvis/
├── backend/
│   ├── agent.py              # Agent 核心逻辑
│   ├── graph_agent.py        # Graph Agent 逻辑
│   ├── providers/            # 多模型 Provider 抽象
│   │   ├── registry.py       # Provider 注册表
│   │   ├── client.py         # 统一 LLM 客户端
│   │   └── __init__.py
│   ├── memory/               # 记忆系统
│   │   ├── __init__.py
│   │   ├── short_term.py
│   │   └── long_term.py
│   ├── tools/                # 工具集
│   │   ├── base.py
│   │   ├── calculator.py
│   │   ├── datetime_tool.py
│   │   ├── file_tool.py
│   │   ├── search.py
│   │   └── weather.py
│   ├── config/
│   │   └── providers.yaml     # Provider 配置模板
│   ├── database.py            # 数据库模型（用户表、模型配置表）
│   ├── auth.py                # 用户认证（JWT、密码哈希）
│   └── __init__.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatPanel.vue      # 聊天面板
│   │   │   ├── SidebarLeft.vue    # 左侧会话列表
│   │   │   ├── SidebarRight.vue   # 右侧设置面板（模型管理）
│   │   │   └── LoginPage.vue      # 登录/注册页面
│   │   ├── App.vue                # 主应用组件
│   │   ├── main.js                # 入口文件
│   │   └── style.css              # 全局样式（含主题变量）
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── jsconfig.json
├── main.py                 # FastAPI 主应用
├── session_manager.py      # 会话管理
├── context_manager.py      # 上下文管理
├── requirements.txt
└── README.md
```

## 快速开始

### 1. 安装后端依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 安装前端依赖

```bash
cd frontend
npm install
```

### 3. 构建前端

```bash
cd frontend
npm run build
```

### 4. 启动服务

```bash
python3 main.py
```

### 5. 使用

访问 `http://localhost:8000`：

1. **注册账号** → 首次使用先注册
2. **登录系统** → 使用注册的账号登录
3. **配置模型** → 右上角 ⚙️ 设置中配置 Provider、API Key
4. **开始对话** → 在聊天面板输入消息

## 用户系统

Jarvis 内置了简单的用户认证系统：

| 功能 | 说明 |
|------|------|
| 注册 | 填写用户名和密码即可注册 |
| 登录 | JWT Token 认证，有效期 30 天 |
| 退出 | 清除 Token，返回登录页面 |
| 模型配置 | 每个用户独立管理自己的模型配置 |

> 模型配置（API Key、Base URL 等）存储在服务端 SQLite 数据库中，换浏览器或清除缓存不会丢失。

## 模型管理

### 模型快捷切换（顶部）

顶部 Header 右侧显示**模型快捷切换**下拉框，仅列出已配置的 Provider，点击即可切换。

### 模型设置面板（右侧 ⚙️）

在右侧设置面板中可以：

- **选择 Provider**：从可用 Provider 列表中选择
- **配置 API Key / Base URL**：填写服务端连接信息
- **选择模型**：从 Provider 支持的模型列表中选择
- **配置最大 Token 数**、Agent 模式等

## 模型 Provider 配置流程

```
首次使用
    ↓
右上角 ⚙️ 设置 → 选择 Provider（如 DeepSeek）
    ↓
填写 API Key → 选择模型 → 点击保存
    ↓
配置持久化到 SQLite 数据库
    ↓
顶部快捷切换下拉框自动出现该 Provider
    ↓
后续使用可直接在顶部切换，无需再次配置
```

## API 接口

### 认证接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/login` | POST | 用户登录（返回 JWT Token） |
| `/api/auth/logout` | POST | 用户退出 |
| `/api/auth/me` | GET | 获取当前用户信息 |

### 模型配置接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/providers` | GET | 获取可用 Provider 列表 |
| `/api/user/config` | GET | 获取当前用户的模型配置列表 |
| `/api/user/config` | POST | 保存当前用户的模型配置 |
| `/api/user/config/{id}` | DELETE | 删除指定模型配置 |
| `/api/models` | GET | 获取指定 Provider 的模型列表 |

### 对话接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | POST | 基础聊天 |
| `/api/agent` | POST | Agent 聊天（支持工具调用） |
| `/api/health` | GET | 健康检查（支持 `?provider=deepseek`） |

### 会话接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/session` | POST | 创建会话 |
| `/api/sessions` | GET | 获取会话列表 |
| `/api/session/{id}` | GET | 获取会话详情 |
| `/api/session/{id}` | DELETE | 删除会话 |
| `/api/session/{id}/save` | POST | 保存会话记录 |

### 工具 / 记忆接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/tools` | GET | 获取工具列表 |
| `/api/memory` | GET | 获取记忆内容 |
| `/api/memory` | POST | 存储记忆 |
| `/api/memory` | DELETE | 清除记忆 |
| `/api/memory/stats` | GET | 获取记忆统计 |

### 请求参数（chat / agent）

```json
{
  "messages": [{"role": "user", "content": "你好"}],
  "session_id": "your-session-id",
  "max_tokens": 2048,
  "provider": "deepseek",
  "model": "deepseek-chat"
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

主题状态自动保存到 localStorage。

## 许可证

MIT License
