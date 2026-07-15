import asyncio
import json
import os
from datetime import timedelta
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.agent import Agent
from backend.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    decode_access_token,
    get_user,
)
from backend.database import ModelConfig, init_db, get_db
from backend.graph_agent import GraphAgent
from backend.memory import memory_manager
from backend.providers import LLMError, list_providers, llm_client
from context_manager import calculate_messages_tokens, truncate_messages
from session_manager import session_manager

app = FastAPI()

dist_dir = os.path.join(os.path.dirname(__file__), "dist")
if os.path.exists(dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")

DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "llama_cpp")
DEFAULT_AGENT_MODE = os.environ.get("DEFAULT_AGENT_MODE", "graph")

agent = Agent()
graph_agent = GraphAgent()

init_db()


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
                options["api_key"] = config.api_key
            if not options["base_url"] and config.base_url:
                options["base_url"] = config.base_url
            if not options["model"] and config.default_model:
                options["model"] = config.default_model

    return options


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
async def register(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not email or not password:
        return {"error": "用户名、邮箱和密码不能为空"}, 400

    if get_user(db, username):
        return {"error": "用户名已存在"}, 400

    if get_user(db, email):
        return {"error": "邮箱已被注册"}, 400

    user = create_user(db, username, email, password)
    return {"success": True, "message": "注册成功", "username": user.username}


@app.post("/api/auth/login")
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

    if existing_config:
        existing_config.provider_name = provider_name
        existing_config.api_key = api_key
        existing_config.base_url = base_url
        existing_config.default_model = default_model
        existing_config.max_tokens = max_tokens
        existing_config.agent_mode = agent_mode
    else:
        new_config = ModelConfig(
            user_id=user["id"],
            provider_id=provider_id,
            provider_name=provider_name,
            api_key=api_key,
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
            api_key = config.api_key
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


@app.post("/api/agent")
async def agent_chat(request: Request, user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    llm_opts = _extract_llm_options(data, user["id"] if user else None, db)

    messages = data.get("messages", [])
    max_tokens = data.get("max_tokens", 2048)
    agent_mode = data.get("agent_mode", DEFAULT_AGENT_MODE)
    session_id = data.get("session_id")

    if not session_id:
        session_id = session_manager.create_session()
    else:
        if session_manager.get_session(session_id) is None:
            session_manager.create_session(session_id)

    session = session_manager.get_session(session_id)
    if session:
        existing_messages = session.messages.copy()

        if existing_messages:
            messages = existing_messages + messages

        session_manager.update_session_messages(session_id, messages)

    current_agent = graph_agent if agent_mode == "graph" else agent

    try:
        result = await asyncio.to_thread(
            current_agent.run,
            messages,
            max_tokens=max_tokens,
            provider=llm_opts["provider"],
            model=llm_opts["model"],
            api_key=llm_opts["api_key"],
            base_url=llm_opts["base_url"],
        )
        result["agent_mode"] = agent_mode
        result["session_id"] = session_id

        if session:
            session.messages = messages + [{"role": "assistant", "content": result["content"]}]
            session_manager.update_session_messages(session_id, session.messages)

        return result
    except LLMError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc), "provider": exc.provider},
        )


@app.get("/api/tools")
async def get_tools(user: Dict = Depends(get_current_user)):
    from backend.tools.base import tool_registry

    return {"tools": tool_registry.get_tools_list()}


@app.get("/api/health")
async def health(provider: str = DEFAULT_PROVIDER, api_key: Optional[str] = None, base_url: Optional[str] = None, user: Dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if user and db and not api_key:
        config = db.query(ModelConfig).filter(
            ModelConfig.user_id == user["id"],
            ModelConfig.provider_id == provider,
            ModelConfig.is_active == True
        ).first()
        if config and config.api_key:
            api_key = config.api_key
        if config and config.base_url:
            base_url = config.base_url

    result = llm_client.health_check(provider_id=provider, api_key=api_key, base_url=base_url)
    if result["status"] == "ok":
        return {"status": "ok", "provider": provider, "detail": result}
    return {"status": "error", "message": result.get("message", "连接失败"), "provider": provider}


@app.get("/api/memory/stats")
async def get_memory_stats(user: Dict = Depends(get_current_user)):
    return memory_manager.get_stats()


@app.get("/api/memory")
async def get_all_memories(user: Dict = Depends(get_current_user)):
    return memory_manager.get_all_memories()


@app.post("/api/memory")
async def add_memory(request: Request, user: Dict = Depends(get_current_user)):
    data = await request.json()
    content = data.get("content", "")
    category = data.get("category", "general")
    metadata = data.get("metadata", {})

    if not content:
        return {"error": "内容不能为空"}

    memory_id = memory_manager.add_long_term_memory(content, category, metadata)
    return {"memory_id": memory_id}


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str, user: Dict = Depends(get_current_user)):
    success = memory_manager.long_term.delete_memory(memory_id)
    return {"success": success}


@app.get("/api/memory/search")
async def search_memories(query: str, top_k: int = 5, user: Dict = Depends(get_current_user)):
    results = memory_manager.retrieve_relevant_memories(query, top_k)
    return {"results": results}


@app.delete("/api/memory")
async def clear_all_memories(user: Dict = Depends(get_current_user)):
    memory_manager.clear_all()
    return {"success": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=300)
