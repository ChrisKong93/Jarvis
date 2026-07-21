"""Jarvis AI Assistant — FastAPI application entry point."""

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Dict, Optional

# Ensure project root is on sys.path (for "python backend/main.py" direct invocation)
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from backend.auth import decode_access_token, get_user
from backend.database import init_db, get_db
from backend.graph_agent import GraphAgent
from backend.mcp import mcp_manager
from backend.plugin_manager import seed_default_plugins
from backend.routes.helpers import sync_mcp_tools
from backend.session_manager import session_manager

logger = logging.getLogger(__name__)

load_dotenv()

# Project root is one level above this file's directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECRET_KEY 安全检查（用于 API Key 加密）
DEFAULT_SECRET_KEY = "jarvis-secret-key-change-in-production"
SECRET_KEY = os.environ.get("SECRET_KEY", DEFAULT_SECRET_KEY)
if SECRET_KEY == DEFAULT_SECRET_KEY:
    logger.warning("⚠️ SECURITY: SECRET_KEY 使用默认值！请设置环境变量 SECRET_KEY 以保护 API Key 加密安全。")

# ---------------------------------------------------------------------------
# FastAPI 应用初始化
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

dist_dir = os.path.join(BASE_DIR, "dist")
if os.path.exists(dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")

agent = GraphAgent()

init_db()
seed_default_plugins()
session_manager.cleanup_expired_sessions()

# 后台自动下载 Embedding 模型（不阻塞服务启动）
from backend.memory.embeddings import embedding_generator  # noqa: E402
embedding_generator.try_download_model_background()

# ---------------------------------------------------------------------------
# MCP 初始化
# ---------------------------------------------------------------------------

def _start_mcp_background():
    """在后台线程中连接所有 MCP 服务器，完成后自动注册工具。"""
    try:
        logger.info("MCP 后台连接开始...")
        mcp_manager.reload_config_sync()
        sync_mcp_tools()
        if mcp_manager.connections:
            logger.info(f"MCP 管理器已启动，已连接 {len(mcp_manager.connections)} 个服务器")
        else:
            logger.info("MCP 管理器已启动（无有效服务器配置）")
    except Exception as exc:
        logger.warning(f"MCP 管理器后台启动异常: {exc}")

threading.Thread(target=_start_mcp_background, daemon=True).start()

# ---------------------------------------------------------------------------
# Auth 依赖
# ---------------------------------------------------------------------------

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[Dict]:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.cookies.get("access_token", "")
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user = get_user(db, payload.get("sub"))
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
    }


# ---------------------------------------------------------------------------
# 路由模块注册
# ---------------------------------------------------------------------------

from backend.routes.auth import register_auth_routes  # noqa: E402
from backend.routes.memory import register_memory_routes  # noqa: E402
from backend.routes.chat import register_chat_routes  # noqa: E402
from backend.routes.config import register_config_routes  # noqa: E402
from backend.routes.mcp import register_mcp_routes  # noqa: E402
from backend.routes.plugins import register_plugin_routes  # noqa: E402
from backend.routes.session import register_session_routes  # noqa: E402
from backend.routes.tools import register_tools_routes  # noqa: E402

register_auth_routes(app, limiter, get_current_user)
register_memory_routes(app, get_current_user)
register_chat_routes(app, get_current_user, agent)
register_config_routes(app, get_current_user)
register_mcp_routes(app, get_current_user)
register_plugin_routes(app, get_current_user)
register_session_routes(app, get_current_user)
register_tools_routes(app, get_current_user)

# ---------------------------------------------------------------------------
# 根路由
# ---------------------------------------------------------------------------

@app.get("/")
async def index(request: Request):
    dist_index = os.path.join(dist_dir, "index.html")
    if os.path.exists(dist_index):
        with open(dist_index, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content, media_type="text/html")
    frontend_index = os.path.join(BASE_DIR, "frontend", "index.html")
    if os.path.exists(frontend_index):
        with open(frontend_index, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content, media_type="text/html")
    return HTMLResponse(content="<h1>Jarvis AI Assistant</h1><p>前端文件未找到，请先构建前端项目。</p>",
                        media_type="text/html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), timeout_keep_alive=300)
