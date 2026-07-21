from typing import Dict

from fastapi import Depends

from session_manager import session_manager


def register_session_routes(app, get_current_user):
    """注册会话管理路由。"""

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
