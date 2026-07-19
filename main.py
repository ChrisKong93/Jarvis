import asyncio
import json
import logging
import os
import re
import threading
from datetime import timedelta
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.concurrency import iterate_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from backend.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    decode_access_token,
    get_user,
)
from backend.crypto_utils import encrypt_api_key, decrypt_api_key
from backend.database import ModelConfig, init_db, get_db
from backend.graph_agent import GraphAgent
from backend.mcp import mcp_manager
from backend.memory import memory_manager
from backend.plugin_manager import seed_default_plugins, get_all_plugins, get_enabled_plugins, toggle_plugin, remove_plugin, install_plugin
from backend.providers import LLMError, list_providers, llm_client
from backend.tools.base import tool_registry
from context_manager import calculate_messages_tokens, truncate_messages
from session_manager import session_manager

load_dotenv()

# SECRET_KEY 安全检查（用于 API Key 加密）
DEFAULT_SECRET_KEY = "jarvis-secret-key-change-in-production"
SECRET_KEY = os.environ.get("SECRET_KEY", DEFAULT_SECRET_KEY)
if SECRET_KEY == DEFAULT_SECRET_KEY:
    logger.warning("⚠️ SECURITY: SECRET_KEY 使用默认值！请设置环境变量 SECRET_KEY 以保护 API Key 加密安全。")

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

dist_dir = os.path.join(os.path.dirname(__file__), "dist")
if os.path.exists(dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")

MIN_PASSWORD_LENGTH = 8


def _validate_password(password: str) -> Optional[str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位"
    if not re.search(r"[A-Za-z]", password):
        return "密码必须包含至少一个字母"
    if not re.search(r"\d", password):
        return "密码必须包含至少一个数字"
    return None


DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "llama_cpp")
DEFAULT_AGENT_MODE = os.environ.get("DEFAULT_AGENT_MODE", "plan_execute")

# 前端 agent_mode → GraphAgent mode 映射
AGENT_MODE_MAPPING = {
    "graph": DEFAULT_AGENT_MODE,
    "chat": "chat",
    "react": "react",
    "plan_execute": "plan_execute",
}

agent = GraphAgent()

init_db()
seed_default_plugins()
session_manager.cleanup_expired_sessions()

# 后台自动下载 Embedding 模型（不阻塞服务启动）
from backend.memory.embeddings import embedding_generator
embedding_generator.try_download_model_background()

# ---------------------------------------------------------------------------
# MCP 初始化
# ---------------------------------------------------------------------------

def sync_mcp_tools():
    """将 MCP 工具注册到 tool_registry。"""
    mcp_tools = mcp_manager.get_all_tools()
    if not mcp_tools:
        return
    count = tool_registry.register_mcp_tools(mcp_tools)
    if count > 0:
        logger.info(f"已将 {count} 个 MCP 工具注册到 Agent 工具列表")


# 启动 MCP 连接（后台线程，不阻塞服务启动）
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


def _extract_llm_options(data: Dict[str, Any], user_id: Optional[int] = None, db: Optional[Session] = None) -> Dict[str, Any]:
    options = {
        "provider": data.get("provider", DEFAULT_PROVIDER),
        "model": data.get("model"),
        "api_key": data.get("api_key"),
        "base_url": data.get("base_url"),
    }

    if user_id and db:
        config = db.query(ModelConfig).filter(
            ModelConfig.user_id == user_id,
            ModelConfig.provider_id == options["provider"],
            ModelConfig.is_active == True
        ).first()
        if config:
            if not options["api_key"] and config.api_key:
                options["api_key"] = decrypt_api_key(config.api_key)
            if not options["base_url"] and config.base_url:
                options["base_url"] = config.base_url
            if not options["model"] and config.default_model:
                options["model"] = config.default_model

    return options


def _resolve_session(data: Dict) -> tuple:
    """获取或创建会话，合并已有消息。返回 (session_id, session, merged_messages)。"""
    session_id = data.get("session_id")
    if not session_id:
        session_id = session_manager.create_session()
    else:
        if session_manager.get_session(session_id) is None:
            session_manager.create_session(session_id)

    session = session_manager.get_session(session_id)
    messages = data.get("messages", [])
    if session:
        existing = session.messages.copy()
        if existing:
            messages = existing + messages
        session_manager.update_session_messages(session_id, messages)
    return session_id, session, messages


@app.get("/")
async def index(request: Request):
    dist_index = os.path.join(dist_dir, "index.html")
    if os.path.exists(dist_index):
        with open(dist_index, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content, media_type="text/html")
    frontend_index = os.path.join(os.path.dirname(__file__), "frontend", "index.html")
    if os.path.exists(frontend_index):
        with open(frontend_index, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content, media_type="text/html")
    return HTMLResponse(content="<h1>Jarvis AI Assistant</h1><p>前端文件未找到，请先构建前端项目。</p>", media_type="text/html")


@app.post("/api/auth/register")
@limiter.limit("5/minute")
async def register(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not email or not password:
        return {"error": "用户名、邮箱和密码不能为空"}, 400

    username = username.strip()
    email = email.strip()

    if len(username) < 2:
        return {"error": "用户名至少 2 个字符"}, 400

    if not re.match(r"^[a-zA-Z0-9_\u4e00-\u9fff]+$", username):
        return {"error": "用户名只能包含字母、数字、下划线和中文"}, 400

    if "@" not in email or "." not in email:
        return {"error": "邮箱格式不正确"}, 400

    password_error = _validate_password(password)
    if password_error:
        return {"error": password_error}, 400

    if get_user(db, username):
        return {"error": "用户名已存在"}, 400

    if get_user(db, email):
        return {"error": "邮箱已被注册"}, 400

    user = create_user(db, username, email, password)
    return {"success": True, "message": "注册成功", "username": user.username}


@app.post("/api/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")

    user = authenticate_user(db, username, password)
    if not user:
        return {"error": "用户名或密码错误"}, 401

    access_token_expires = timedelta(minutes=30 * 24 * 60)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    response = JSONResponse({
        "success": True,
        "message": "登录成功",
        "access_token": access_token,
        "username": user.username,
    })
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response


@app.post("/api/auth/logout")
async def logout():
    response = JSONResponse({"success": True, "message": "退出成功"})
    response.set_cookie(key="access_token", value="", expires=0)
    return response


@app.get("/api/auth/me")
async def get_current_user_info(user: Dict = Depends(get_current_user)):
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": user}


@app.post("/api/session")
async def create_session(user: Dict = Depends(get_current_user)):
    session_id = session_manager.create_session()
    return {"session_id": session_id}


@app.get("/api/session/{session_id}")
async def get_session(session_id: str, user: Dict = Depends(get_current_user)):
    session = session_manager.get_session(session_id)
    if session:
        return {
            "session_id": session.session_id,
            "messages": session.messages,
            "created_at": session.created_at.isoformat(),
            "last_active": session.last_active.isoformat(),
        }
    return {"error": "会话不存在"}


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str, user: Dict = Depends(get_current_user)):
    success = session_manager.delete_session(session_id)
    return {"success": success}


@app.get("/api/sessions")
async def list_sessions(user: Dict = Depends(get_current_user)):
    sessions = session_manager.list_sessions()
    return {"sessions": sessions}


@app.get("/api/providers")
async def get_providers(user: Dict = Depends(get_current_user)):
    return {"providers": list_providers(), "default_provider": DEFAULT_PROVIDER}


@app.get("/api/user/config")
async def get_user_config(user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return {"config": None}

    configs = db.query(ModelConfig).filter(
        ModelConfig.user_id == user["id"],
        ModelConfig.is_active == True
    ).all()

    result = []
    for config in configs:
        result.append({
            "id": config.id,
            "provider_id": config.provider_id,
            "provider_name": config.provider_name,
            "api_key": "",
            "base_url": config.base_url,
            "default_model": config.default_model,
            "max_tokens": config.max_tokens,
            "agent_mode": config.agent_mode,
        })

    return {"configs": result}


@app.post("/api/user/config")
async def save_user_config(request: Request, user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return {"error": "未登录"}, 401

    data = await request.json()
    provider_id = data.get("provider_id")
    provider_name = data.get("provider_name")
    api_key = data.get("api_key")
    base_url = data.get("base_url")
    default_model = data.get("default_model")
    max_tokens = data.get("max_tokens", 2048)
    agent_mode = data.get("agent_mode", "graph")

    if not provider_id or not provider_name:
        return {"error": "Provider ID 和名称不能为空"}, 400

    existing_config = db.query(ModelConfig).filter(
        ModelConfig.user_id == user["id"],
        ModelConfig.provider_id == provider_id,
        ModelConfig.is_active == True
    ).first()

    encrypted_api_key = encrypt_api_key(api_key) if api_key else ""

    if existing_config:
        existing_config.provider_name = provider_name
        if api_key:
            existing_config.api_key = encrypted_api_key
        existing_config.base_url = base_url
        existing_config.default_model = default_model
        existing_config.max_tokens = max_tokens
        existing_config.agent_mode = agent_mode
    else:
        new_config = ModelConfig(
            user_id=user["id"],
            provider_id=provider_id,
            provider_name=provider_name,
            api_key=encrypted_api_key,
            base_url=base_url,
            default_model=default_model,
            max_tokens=max_tokens,
            agent_mode=agent_mode,
        )
        db.add(new_config)

    db.commit()
    return {"success": True, "message": "配置已保存"}


@app.delete("/api/user/config/{config_id}")
async def delete_user_config(config_id: int, user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return {"error": "未登录"}, 401

    config = db.query(ModelConfig).filter(
        ModelConfig.id == config_id,
        ModelConfig.user_id == user["id"]
    ).first()

    if not config:
        return {"error": "配置不存在"}, 404

    config.is_active = False
    db.commit()
    return {"success": True, "message": "配置已删除"}


@app.get("/api/models")
async def models(provider: str = DEFAULT_PROVIDER, api_key: Optional[str] = None, base_url: Optional[str] = None, user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if user and db and not api_key:
        config = db.query(ModelConfig).filter(
            ModelConfig.user_id == user["id"],
            ModelConfig.provider_id == provider,
            ModelConfig.is_active == True
        ).first()
        if config and config.api_key:
            api_key = decrypt_api_key(config.api_key)
        if config and config.base_url:
            base_url = config.base_url

    model_list = llm_client.list_models(provider_id=provider, api_key=api_key, base_url=base_url)
    return {"models": model_list, "provider": provider}


@app.post("/api/chat")
async def chat(request: Request, user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    llm_opts = _extract_llm_options(data, user["id"] if user else None, db)

    messages = data.get("messages", [])
    max_tokens = data.get("max_tokens", 2048)
    truncated_messages = truncate_messages(messages, max_tokens)

    try:
        result = llm_client.chat_completion(
            messages=truncated_messages,
            provider_id=llm_opts["provider"],
            model=llm_opts["model"],
            max_tokens=max_tokens,
            api_key=llm_opts["api_key"],
            base_url=llm_opts["base_url"],
        )
        return {
            "content": result["content"],
            "choices": [{"message": {"role": "assistant", "content": result["content"]}}],
            "usage": {
                "completion_tokens": result["completion_tokens"],
                "prompt_tokens": result["prompt_tokens"],
                "total_tokens": result["total_tokens"],
            },
            "tokens_per_second": result["tokens_per_second"],
            "response_time": result["response_time"],
            "context_tokens": calculate_messages_tokens(truncated_messages),
            "original_messages_count": len(messages),
            "truncated_messages_count": len(truncated_messages),
            "provider": result["provider"],
            "model": result["model"],
        }
    except LLMError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc), "provider": exc.provider},
        )


@app.post("/api/chat/stream")
async def chat_stream(request: Request, user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    llm_opts = _extract_llm_options(data, user["id"] if user else None, db)

    messages = data.get("messages", [])
    max_tokens = data.get("max_tokens", 2048)
    truncated_messages = truncate_messages(messages, max_tokens)

    async def event_generator():
        async for event in iterate_in_threadpool(
            llm_client.chat_completion_stream(
                messages=truncated_messages,
                provider_id=llm_opts["provider"],
                model=llm_opts["model"],
                max_tokens=max_tokens,
                api_key=llm_opts["api_key"],
                base_url=llm_opts["base_url"],
            )
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event["type"] == "error":
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/agent")
async def agent_chat(request: Request, user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    llm_opts = _extract_llm_options(data, user["id"] if user else None, db)

    max_tokens = data.get("max_tokens", 2048)
    agent_mode = data.get("agent_mode", DEFAULT_AGENT_MODE)
    current_agent_mode = AGENT_MODE_MAPPING.get(agent_mode, DEFAULT_AGENT_MODE)
    session_id, session, messages = _resolve_session(data)

    try:
        result = await asyncio.to_thread(
            agent.run,
            messages,
            max_tokens=max_tokens,
            provider=llm_opts["provider"],
            model=llm_opts["model"],
            api_key=llm_opts["api_key"],
            base_url=llm_opts["base_url"],
            user_id=user["id"] if user else None,
            mode=current_agent_mode,
        )
        result["agent_mode"] = agent_mode
        result["session_id"] = session_id

        if session:
            session.messages = messages + [{"role": "assistant", "content": result["content"]}]
            session_manager.update_session_messages(session_id, session.messages)

        return result
    except LLMError as exc:
        logger.error(f"LLMError: {exc} (provider: {exc.provider}, status: {exc.status_code})")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc), "provider": exc.provider},
        )
    except Exception as exc:
        import traceback
        logger.error(f"Unexpected error in agent_chat:\n{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/agent/stream")
async def agent_chat_stream(request: Request, user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    llm_opts = _extract_llm_options(data, user["id"] if user else None, db)

    max_tokens = data.get("max_tokens", 2048)
    agent_mode = data.get("agent_mode", DEFAULT_AGENT_MODE)
    current_agent_mode = AGENT_MODE_MAPPING.get(agent_mode, DEFAULT_AGENT_MODE)
    session_id, session, messages = _resolve_session(data)
    run_fn = agent.run_stream

    async def event_generator():
        full_content = ""
        try:
            async for event in iterate_in_threadpool(
                run_fn(
                    messages,
                    max_tokens=max_tokens,
                    provider=llm_opts["provider"],
                    model=llm_opts["model"],
                    api_key=llm_opts["api_key"],
                    base_url=llm_opts["base_url"],
                    user_id=user["id"] if user else None,
                    mode=current_agent_mode,
                )
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] == "token":
                    full_content += event.get("content", "")
                elif event["type"] == "error":
                    break
        except Exception as exc:
            logger.error(f"Stream error: {exc}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)}, ensure_ascii=False)}\n\n"
            return

        # 更新会话消息
        if session and full_content:
            session.messages = messages + [{"role": "assistant", "content": full_content}]
            session_manager.update_session_messages(session_id, session.messages)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/tools")
async def get_tools(user: Dict = Depends(get_current_user)):
    from backend.tools.base import tool_registry

    return {"tools": tool_registry.get_tools_list()}


@app.get("/api/plugins")
async def list_plugins(user: Dict = Depends(get_current_user)):
    return {"plugins": get_all_plugins()}


@app.get("/api/plugins/enabled")
async def list_enabled_plugins(user: Dict = Depends(get_current_user)):
    return {"plugins": get_enabled_plugins()}


@app.put("/api/plugins/{plugin_id}/toggle")
async def toggle_plugin_endpoint(plugin_id: int, request: Request, user: Dict = Depends(get_current_user)):
    data = await request.json()
    enabled = data.get("is_enabled", True)
    success = toggle_plugin(plugin_id, enabled)
    if success:
        return {"success": True}
    return {"error": "插件不存在"}, 404


@app.post("/api/plugins")
async def install_plugin_endpoint(request: Request, user: Dict = Depends(get_current_user)):
    if not user:
        return {"error": "未登录"}, 401
    data = await request.json()
    plugin_id = install_plugin(
        name=data.get("name"),
        display_name=data.get("display_name"),
        description=data.get("description", ""),
        version=data.get("version", "1.0.0"),
        author=data.get("author", ""),
        icon=data.get("icon", "🧩"),
        config=data.get("config"),
    )
    if plugin_id:
        return {"success": True, "id": plugin_id}
    return {"error": "安装失败，插件名可能已存在"}, 400


@app.delete("/api/plugins/{plugin_id}")
async def uninstall_plugin_endpoint(plugin_id: int, user: Dict = Depends(get_current_user)):
    if not user:
        return {"error": "未登录"}, 401
    success = remove_plugin(plugin_id)
    if success:
        return {"success": True}
    return {"error": "删除失败（默认插件不可删除）"}, 400


@app.get("/api/health")
async def health(provider: str = DEFAULT_PROVIDER, api_key: Optional[str] = None, base_url: Optional[str] = None, user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if user and db and not api_key:
        config = db.query(ModelConfig).filter(
            ModelConfig.user_id == user["id"],
            ModelConfig.provider_id == provider,
            ModelConfig.is_active == True
        ).first()
        if config and config.api_key:
            api_key = decrypt_api_key(config.api_key)
        if config and config.base_url:
            base_url = config.base_url

    result = llm_client.health_check(provider_id=provider, api_key=api_key, base_url=base_url)
    if result["status"] == "ok":
        return {"status": "ok", "provider": provider, "detail": result}
    return {"status": "error", "message": result.get("message", "连接失败"), "provider": provider}


@app.get("/api/memory/stats")
async def get_memory_stats(user: Dict = Depends(get_current_user)):
    if not user:
        return {"short_term_summaries": 0, "long_term_memories": 0}
    return memory_manager.get_stats(user["id"])


@app.get("/api/memory")
async def get_all_memories(user: Dict = Depends(get_current_user)):
    if not user:
        return {"short_term": [], "long_term": []}
    return memory_manager.get_all_memories(user["id"])


@app.post("/api/memory")
async def add_memory(request: Request, user: Dict = Depends(get_current_user)):
    if not user:
        return {"error": "未登录"}, 401
    data = await request.json()
    content = data.get("content", "")
    category = data.get("category", "general")
    metadata = data.get("metadata", {})

    if not content:
        return {"error": "内容不能为空"}

    memory_id = memory_manager.add_long_term_memory(user["id"], content, category, metadata)
    return {"memory_id": memory_id}


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str, user: Dict = Depends(get_current_user)):
    if not user:
        return {"error": "未登录"}, 401
    from backend.memory.long_term import LongTermMemory
    long = LongTermMemory(user["id"])
    success = long.delete_memory(memory_id)
    return {"success": success}


@app.get("/api/memory/search")
async def search_memories(query: str, top_k: int = 5, user: Dict = Depends(get_current_user)):
    if not user:
        return {"results": []}
    results = memory_manager.retrieve_relevant_memories(user["id"], query, top_k)
    return {"results": results}


@app.delete("/api/memory")
async def clear_all_memories(user: Dict = Depends(get_current_user)):
    if not user:
        return {"error": "未登录"}, 401
    memory_manager.clear_all(user["id"])
    return {"success": True}


# ---------------------------------------------------------------------------
# MCP 管理 API
# ---------------------------------------------------------------------------

@app.get("/api/mcp/servers")
async def get_mcp_servers(user: Dict = Depends(get_current_user)):
    """获取所有 MCP 服务器连接状态。"""
    return {"servers": mcp_manager.get_config_snapshot()}


@app.get("/api/mcp/tools")
async def get_mcp_tools(user: Dict = Depends(get_current_user)):
    """获取所有 MCP 工具列表。"""
    return {"tools": mcp_manager.get_all_tools()}


@app.post("/api/mcp/servers/reload")
async def reload_mcp_servers(user: Dict = Depends(get_current_user)):
    """重新加载 MCP 配置并重连所有服务器。"""
    if not user:
        return {"error": "未登录"}, 401
    try:
        # 注销旧的 MCP 工具
        count = tool_registry.unregister_mcp_tools()
        if count > 0:
            logger.info(f"已注销 {count} 个旧的 MCP 工具")

        mcp_manager.reload_config_sync()
        sync_mcp_tools()
        return {"success": True, "message": "MCP 服务器已重新加载"}
    except Exception as exc:
        logger.error(f"重新加载 MCP 失败: {exc}")
        return {"error": str(exc)}, 500


@app.post("/api/mcp/servers/{name}/reconnect")
async def reconnect_mcp_server(name: str, user: Dict = Depends(get_current_user)):
    """重连指定的 MCP 服务器。"""
    if not user:
        return {"error": "未登录"}, 401
    from backend.mcp.manager import MCPServerConnection

    conn = mcp_manager.connections.get(name)
    if not conn:
        return {"error": f"MCP 服务器 '{name}' 不存在"}, 404
    try:
        conn.disconnect()
        configs = mcp_manager._load_config()
        config = next((c for c in configs if c.get("name") == name), None)
        if config:
            new_conn = MCPServerConnection(config)
            new_conn.connect()
            mcp_manager.connections[name] = new_conn
            mcp_manager._rebuild_tool_index()
            sync_mcp_tools()
            return {"success": True, "message": f"MCP 服务器 '{name}' 已重连"}
        return {"error": f"未找到 '{name}' 的配置"}, 404
    except Exception as exc:
        logger.error(f"重连 MCP 服务器 '{name}' 失败: {exc}")
        return {"error": str(exc)}, 500


@app.put("/api/mcp/servers/{name}")
async def update_mcp_server(name: str, request: Request, user: Dict = Depends(get_current_user)):
    """更新 MCP 服务器配置（保存到配置文件并重连）。"""
    if not user:
        return {"error": "未登录"}, 401
    from backend.mcp.manager import MCP_CONFIG_PATH
    import json, os

    try:
        data = await request.json()

        existing = {"servers": []}
        if os.path.exists(MCP_CONFIG_PATH):
            with open(MCP_CONFIG_PATH, "r") as f:
                existing = json.load(f)

        servers = existing.get("servers", [])
        idx = next((i for i, s in enumerate(servers) if s.get("name") == name), None)
        new_config = {
            "name": name,
            "transport": data.get("transport", "stdio"),
            "command": data.get("command", ""),
            "args": data.get("args", []),
            "env": data.get("env", {}),
            "url": data.get("url", ""),
        }
        if idx is not None:
            servers[idx] = new_config
        else:
            servers.append(new_config)

        existing["servers"] = servers
        with open(MCP_CONFIG_PATH, "w") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        tool_registry.unregister_mcp_tools()
        mcp_manager.reload_config_sync()
        sync_mcp_tools()
        return {"success": True, "message": f"MCP 服务器 '{name}' 已更新"}
    except Exception as exc:
        logger.error(f"更新 MCP 服务器 '{name}' 失败: {exc}")
        return {"error": str(exc)}, 500


@app.delete("/api/mcp/servers/{name}")
async def delete_mcp_server(name: str, user: Dict = Depends(get_current_user)):
    """删除 MCP 服务器配置。"""
    if not user:
        return {"error": "未登录"}, 401
    from backend.mcp.manager import MCP_CONFIG_PATH
    import json, os

    try:
        if os.path.exists(MCP_CONFIG_PATH):
            with open(MCP_CONFIG_PATH, "r") as f:
                existing = json.load(f)
            existing["servers"] = [s for s in existing.get("servers", []) if s.get("name") != name]
            with open(MCP_CONFIG_PATH, "w") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

        tool_registry.unregister_mcp_tools()
        mcp_manager.reload_config_sync()
        sync_mcp_tools()
        return {"success": True, "message": f"MCP 服务器 '{name}' 已删除"}
    except Exception as exc:
        logger.error(f"删除 MCP 服务器 '{name}' 失败: {exc}")
        return {"error": str(exc)}, 500


if __name__ == "__main__":
    import uvicorn

    import os
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), timeout_keep_alive=300)
