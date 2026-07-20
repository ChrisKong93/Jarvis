# ============================================================
# Stage 1: Build Frontend (Vue.js)
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# ============================================================
# Stage 2: Backend (Python)
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# 系统依赖（sentence-transformers / chromadb 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（中国大陆可通过 .env 配置 PIP_INDEX_URL 加速）
ARG PIP_INDEX_URL=""
RUN if [ -n "$PIP_INDEX_URL" ]; then \
        pip config set global.index-url "$PIP_INDEX_URL"; \
    fi
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制前端构建产物
COPY --from=frontend-builder /app/dist ./dist

# 复制后端代码
COPY main.py .
COPY backend/ backend/
COPY context_manager.py .
COPY session_manager.py .

# 运行端口
EXPOSE 8000

# 默认环境变量
ENV DEFAULT_PROVIDER=llama_cpp
ENV DEFAULT_AGENT_MODE=plan_execute
ENV SECRET_KEY=jarvis-docker-secret-change-me

# 数据卷挂载点
VOLUME ["/app/data", "/app/backend/memory/embeddings_cache"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
