import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import Depends, Request
from fastapi.concurrency import iterate_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.providers import LLMError, llm_client
from backend.routes.helpers import (
    AGENT_MODE_MAPPING,
    DEFAULT_AGENT_MODE,
    extract_llm_options,
    resolve_session,
)
from backend.context_manager import calculate_messages_tokens, truncate_messages
from backend.session_manager import session_manager

logger = logging.getLogger(__name__)


def register_chat_routes(app, get_current_user, agent):
    """注册聊天和 Agent 路由。"""

    # ------------------------------------------------------------------
    # /api/chat — 普通聊天
    # ------------------------------------------------------------------

    @app.post("/api/chat")
    async def chat(request: Request,
                   user: Dict = Depends(get_current_user),
                   db: Session = Depends(get_db)):
        data = await request.json()
        llm_opts = extract_llm_options(data, user["id"] if user else None, db)

        messages = data.get("messages", [])
        max_tokens = data.get("max_tokens", 2048)
        truncated_messages = truncate_messages(messages, max_tokens)

        try:
            result = await llm_client.async_chat_completion(
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
    async def chat_stream(request: Request,
                          user: Dict = Depends(get_current_user),
                          db: Session = Depends(get_db)):
        data = await request.json()
        llm_opts = extract_llm_options(data, user["id"] if user else None, db)

        messages = data.get("messages", [])
        max_tokens = data.get("max_tokens", 2048)
        truncated_messages = truncate_messages(messages, max_tokens)

        async def event_generator():
            async for event in llm_client.async_chat_completion_stream(
                messages=truncated_messages,
                provider_id=llm_opts["provider"],
                model=llm_opts["model"],
                max_tokens=max_tokens,
                api_key=llm_opts["api_key"],
                base_url=llm_opts["base_url"],
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] == "error":
                    break

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # ------------------------------------------------------------------
    # /api/agent — LangGraph Agent
    # ------------------------------------------------------------------

    @app.post("/api/agent")
    async def agent_chat(request: Request,
                         user: Dict = Depends(get_current_user),
                         db: Session = Depends(get_db)):
        data = await request.json()
        llm_opts = extract_llm_options(data, user["id"] if user else None, db)

        max_tokens = data.get("max_tokens", 2048)
        agent_mode = data.get("agent_mode", DEFAULT_AGENT_MODE)
        current_agent_mode = AGENT_MODE_MAPPING.get(agent_mode, DEFAULT_AGENT_MODE)
        session_id, session, messages = resolve_session(data)

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
                assistant_msg = {"role": "assistant", "content": result["content"]}
                if result.get("plan"):
                    assistant_msg["plan"] = result["plan"]
                if result.get("tool_info"):
                    assistant_msg["tool_info"] = result["tool_info"]
                session.messages = messages + [assistant_msg]
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
    async def agent_chat_stream(request: Request,
                                user: Dict = Depends(get_current_user),
                                db: Session = Depends(get_db)):
        data = await request.json()
        llm_opts = extract_llm_options(data, user["id"] if user else None, db)

        max_tokens = data.get("max_tokens", 2048)
        agent_mode = data.get("agent_mode", DEFAULT_AGENT_MODE)
        current_agent_mode = AGENT_MODE_MAPPING.get(agent_mode, DEFAULT_AGENT_MODE)
        session_id, session, messages = resolve_session(data)
        run_fn = agent.run_stream

        async def event_generator():
            full_content = ""
            collected_plan = None
            collected_tool_info = []
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
                    event_type = event["type"]
                    if event_type == "token":
                        full_content += event.get("content", "")
                    elif event_type == "plan":
                        collected_plan = event.get("steps") or event.get("plan") or []
                    elif event_type == "tool_call":
                        collected_tool_info.append({
                            "tool_name": event["tool_name"],
                            "parameters": event["parameters"],
                            "status": "running",
                            "result": None,
                        })
                    elif event_type == "tool_result":
                        if collected_tool_info:
                            collected_tool_info[-1]["result"] = event.get("result", "")
                            collected_tool_info[-1]["status"] = "completed"
                    elif event_type == "error":
                        break
            except Exception as exc:
                logger.error(f"Stream error: {exc}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(exc)}, ensure_ascii=False)}\n\n"
                return

            # 更新会话消息（含 plan 和工具调用记录）
            if session and full_content:
                assistant_msg = {"role": "assistant", "content": full_content}
                if collected_plan:
                    assistant_msg["plan"] = collected_plan
                if collected_tool_info:
                    assistant_msg["tool_info"] = collected_tool_info
                session.messages = messages + [assistant_msg]
                session_manager.update_session_messages(session_id, session.messages)

        return StreamingResponse(event_generator(), media_type="text/event-stream")
