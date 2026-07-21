from typing import Dict

from fastapi import Depends, Request

from backend.plugin_manager import (
    get_all_plugins,
    get_enabled_plugins,
    install_plugin,
    remove_plugin,
    toggle_plugin,
)


def register_plugin_routes(app, get_current_user):
    """注册插件管理路由。"""

    @app.get("/api/plugins")
    async def list_plugins(user: Dict = Depends(get_current_user)):
        return {"plugins": get_all_plugins()}

    @app.get("/api/plugins/enabled")
    async def list_enabled_plugins(user: Dict = Depends(get_current_user)):
        return {"plugins": get_enabled_plugins()}

    @app.put("/api/plugins/{plugin_id}/toggle")
    async def toggle_plugin_endpoint(plugin_id: int,
                                     request: Request,
                                     user: Dict = Depends(get_current_user)):
        data = await request.json()
        enabled = data.get("is_enabled", True)
        success = toggle_plugin(plugin_id, enabled)
        if success:
            return {"success": True}
        return {"error": "插件不存在"}, 404

    @app.post("/api/plugins")
    async def install_plugin_endpoint(request: Request,
                                      user: Dict = Depends(get_current_user)):
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
    async def uninstall_plugin_endpoint(plugin_id: int,
                                        user: Dict = Depends(get_current_user)):
        if not user:
            return {"error": "未登录"}, 401
        success = remove_plugin(plugin_id)
        if success:
            return {"success": True}
        return {"error": "删除失败（默认插件不可删除）"}, 400
