import logging
import os
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.crypto_utils import decrypt_api_key
from backend.database import ModelConfig
from backend.session_manager import session_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "llama_cpp")
DEFAULT_AGENT_MODE = os.environ.get("DEFAULT_AGENT_MODE", "plan_execute")

AGENT_MODE_MAPPING = {
    "graph": DEFAULT_AGENT_MODE,
    "chat": "chat",
    "react": "react",
    "plan_execute": "plan_execute",
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def extract_llm_options(data: Dict[str, Any],
                        user_id: Optional[int] = None,
                        db: Optional[Session] = None) -> Dict[str, Any]:
    """从请求数据中提取 LLM 配置，必要时回退到数据库配置。"""
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


def resolve_session(data: Dict) -> tuple:
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


def sync_mcp_tools() -> int:
    """将 MCP 工具注册到 tool_registry。返回注册的工具数量。"""
    from backend.mcp import mcp_manager
    from backend.tools.base import tool_registry

    mcp_tools = mcp_manager.get_all_tools()
    if not mcp_tools:
        return 0
    count = tool_registry.register_mcp_tools(mcp_tools)
    if count > 0:
        logger.info(f"已将 {count} 个 MCP 工具注册到 Agent 工具列表")
    return count
