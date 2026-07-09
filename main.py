import json
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.agent import Agent
from backend.memory import memory_manager
from backend.providers import LLMError, list_providers, llm_client
from context_manager import calculate_messages_tokens, truncate_messages
from session_manager import session_manager

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI()
agent = Agent()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "llama_cpp")


def _extract_llm_options(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "provider": data.get("provider", DEFAULT_PROVIDER),
        "model": data.get("model"),
        "api_key": data.get("api_key"),
        "base_url": data.get("base_url"),
    }


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/session")
async def create_session():
    session_id = session_manager.create_session()
    return {"session_id": session_id}


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
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
async def delete_session(session_id: str):
    success = session_manager.delete_session(session_id)
    return {"success": success}


@app.get("/api/providers")
async def get_providers():
    return {"providers": list_providers(), "default_provider": DEFAULT_PROVIDER}


@app.get("/api/models")
async def models(provider: str = DEFAULT_PROVIDER, api_key: Optional[str] = None, base_url: Optional[str] = None):
    model_list = llm_client.list_models(provider_id=provider, api_key=api_key, base_url=base_url)
    return {"models": model_list, "provider": provider}


@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    llm_opts = _extract_llm_options(data)

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
async def agent_chat(request: Request):
    data = await request.json()
    llm_opts = _extract_llm_options(data)

    messages = data.get("messages", [])
    max_tokens = data.get("max_tokens", 2048)

    try:
        result = agent.run(
            messages,
            max_tokens=max_tokens,
            provider=llm_opts["provider"],
            model=llm_opts["model"],
            api_key=llm_opts["api_key"],
            base_url=llm_opts["base_url"],
        )
        return result
    except LLMError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc), "provider": exc.provider},
        )


@app.get("/api/tools")
async def get_tools():
    from backend.tools.base import tool_registry

    return {"tools": tool_registry.get_tools_list()}


@app.get("/api/health")
async def health(provider: str = DEFAULT_PROVIDER, api_key: Optional[str] = None, base_url: Optional[str] = None):
    result = llm_client.health_check(provider_id=provider, api_key=api_key, base_url=base_url)
    if result["status"] == "ok":
        return {"status": "ok", "provider": provider, "detail": result}
    return {"status": "error", "message": result.get("message", "连接失败"), "provider": provider}


@app.get("/api/memory/stats")
async def get_memory_stats():
    return memory_manager.get_stats()


@app.get("/api/memory")
async def get_all_memories():
    return memory_manager.get_all_memories()


@app.post("/api/memory")
async def add_memory(request: Request):
    data = await request.json()
    content = data.get("content", "")
    category = data.get("category", "general")
    metadata = data.get("metadata", {})

    if not content:
        return {"error": "内容不能为空"}

    memory_id = memory_manager.add_long_term_memory(content, category, metadata)
    return {"memory_id": memory_id}


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    success = memory_manager.long_term.delete_memory(memory_id)
    return {"success": success}


@app.get("/api/memory/search")
async def search_memories(query: str, top_k: int = 5):
    results = memory_manager.retrieve_relevant_memories(query, top_k)
    return {"results": results}


@app.delete("/api/memory")
async def clear_all_memories():
    memory_manager.clear_all()
    return {"success": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=300)
