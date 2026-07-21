# ============================================================
# Stage 1: Build Frontend (Vue.js)
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 利用 Docker 缓存：先安装依赖，再复制源码
COPY frontend/package.json ./
# 兼容 package-lock.json 不存在的情况
COPY frontend/package-lock.json ./ || true
RUN npm ci || npm install

COPY frontend/ .
RUN npm run build

# ============================================================
# Stage 2: Backend (Python)
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# ── 系统依赖 ──
# sentence-transformers / chromadb 需要编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# ── Python 依赖 ──
# 中国大陆可通过 .env 设置 PIP_INDEX_URL 加速
ARG PIP_INDEX_URL=""
RUN if [ -n "$PIP_INDEX_URL" ]; then \
        pip config set global.index-url "$PIP_INDEX_URL"; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 复制前端构建产物 ──
COPY --from=frontend-builder /app/dist ./dist

# ── 复制后端代码 ──
COPY main.py .
COPY backend/ backend/
COPY context_manager.py .
COPY session_manager.py .

# ── 创建非 root 用户 ──
RUN addgroup --system --gid 1001 jarvis && \
    adduser --system --uid 1001 --ingroup jarvis --home /app --no-create-home jarvis && \
    chown -R jarvis:jarvis /app
USER jarvis

# ── 健康检查 ──
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# ── 元数据 ──
LABEL org.opencontainers.image.title="Jarvis AI Agent"
LABEL org.opencontainers.image.description="AI Agent based on FastAPI + Vue3, supporting local & cloud LLMs"
LABEL org.opencontainers.image.version="1.0.0"

# ── 运行配置 ──
EXPOSE 8000

ENV DEFAULT_PROVIDER=llama_cpp
ENV DEFAULT_AGENT_MODE=plan_execute
ENV SECRET_KEY=jarvis-docker-secret-change-me

# 数据卷挂载点
VOLUME ["/app/data", "/app/backend/memory/embeddings_cache"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
