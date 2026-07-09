# Jarvis AI Agent

一个基于 FastAPI 的 AI Agent 智能助手系统，支持**本地 llama.cpp** 与**云端主流大模型**（DeepSeek、OpenAI、Kimi、智谱、通义千问等），具备任务规划、工具调用、记忆机制等核心能力。

## 功能特性

- 🎯 **任务规划**：基于 ReAct 模式，将复杂任务分解为子任务，制定执行计划
- 🔄 **反思机制**：工具调用失败时自动重试与策略调整
- 🛠️ **工具调用**：支持计算器、搜索、天气、文件操作、日期时间等工具
- 🧠 **记忆系统**：短期记忆（对话总结）与长期记忆（重要信息持久化）
- 💬 **多轮对话**：完整的上下文管理与智能截断策略
- ☁️ **多模型支持**：本地 llama.cpp + 云端 OpenAI 兼容 API，前端可自由切换

## 支持的模型 Provider

| Provider | 说明 | 环境变量 |
|----------|------|----------|
| `llama_cpp` | 本地 llama.cpp 服务 | `LLAMA_CPP_URL` |
| `deepseek` | DeepSeek 云端 | `DEEPSEEK_API_KEY` |
| `openai` | OpenAI GPT 系列 | `OPENAI_API_KEY` |
| `moonshot` | 月之暗面 Kimi | `MOONSHOT_API_KEY` |
| `zhipu` | 智谱 GLM | `ZHIPU_API_KEY` |
| `dashscope` | 阿里云通义千问 | `DASHSCOPE_API_KEY` |
| `siliconflow` | 硅基流动模型聚合 | `SILICONFLOW_API_KEY` |
| `custom` | 自定义 OpenAI 兼容 API | `CUSTOM_LLM_BASE_URL` + `CUSTOM_LLM_API_KEY` |

## 技术栈

- **后端**：Python 3.9+, FastAPI
- **大模型**：llama.cpp（本地）/ OpenAI 兼容 API（云端）
- **前端**：HTML/CSS/JavaScript
- **部署**：Uvicorn

## 项目结构

```
Jarvis/
├── backend/
│   ├── agent.py          # Agent 核心逻辑
│   ├── providers/        # 多模型 Provider 抽象
│   │   ├── registry.py   # Provider 注册表
│   │   └── client.py     # 统一 LLM 客户端
│   ├── memory/           # 记忆系统
│   └── tools/            # 工具集
├── templates/
│   └── index.html        # 前端界面
├── main.py               # FastAPI 主应用
├── .env.example          # 环境变量模板
└── requirements.txt
```

## 快速开始

### 1. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置模型

复制环境变量模板并填入 API Key：

```bash
cp .env.example .env
# 编辑 .env，至少配置一个 Provider
```

**使用本地 llama.cpp：**

```bash
cd /path/to/llama.cpp
./server -m models/your-model.gguf -c 4096 --host 0.0.0.0 --port 8081
```

在 `.env` 中设置：

```
DEFAULT_PROVIDER=llama_cpp
LLAMA_CPP_URL=http://127.0.0.1:8081
```

**使用 DeepSeek 云端：**

```
DEFAULT_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-key-here
```

### 3. 启动服务

```bash
python3 main.py
```

访问 `http://localhost:8000`，在右上角**设置**中切换 Provider 和模型。

> API Key 也可在 Web 界面设置中填写（保存在浏览器本地），无需写入 `.env`。

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端界面 |
| `/api/providers` | GET | 获取可用 Provider 列表 |
| `/api/models` | GET | 获取指定 Provider 的模型列表 |
| `/api/chat` | POST | 基础聊天 |
| `/api/agent` | POST | Agent 聊天（支持工具调用） |
| `/api/tools` | GET | 获取工具列表 |
| `/api/health` | GET | 健康检查（支持 `?provider=deepseek`） |
| `/api/memory` | GET/POST/DELETE | 记忆管理 |

### 请求参数（chat / agent）

```json
{
  "messages": [{"role": "user", "content": "你好"}],
  "max_tokens": 2048,
  "provider": "deepseek",
  "model": "deepseek-chat",
  "api_key": "sk-optional-override"
}
```

## 工具列表

| 工具 | 功能 |
|------|------|
| `calculator` | 数学表达式计算 |
| `search` | 互联网信息检索 |
| `weather` | 城市天气查询 |
| `file` | 文件读写操作 |
| `datetime` | 日期时间与定时器 |

## 许可证

MIT License
