from typing import Dict

from fastapi import Depends

from backend.tools.base import tool_registry


def register_tools_routes(app, get_current_user):
    """注册工具相关路由。"""

    @app.get("/api/tools")
    async def get_tools(user: Dict = Depends(get_current_user)):
        return {"tools": tool_registry.get_tools_list()}
