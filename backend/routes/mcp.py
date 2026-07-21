import json
import logging
import os
from typing import Dict

from fastapi import Depends, Request

from backend.mcp import mcp_manager
from backend.tools.base import tool_registry
from backend.routes.helpers import sync_mcp_tools

logger = logging.getLogger(__name__)


def register_mcp_routes(app, get_current_user):
    """注册 MCP 服务器管理路由。"""

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
    async def reconnect_mcp_server(name: str,
                                   user: Dict = Depends(get_current_user)):
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
    async def update_mcp_server(name: str,
                                request: Request,
                                user: Dict = Depends(get_current_user)):
        """更新 MCP 服务器配置（保存到配置文件并重连）。"""
        if not user:
            return {"error": "未登录"}, 401
        from backend.mcp.manager import MCP_CONFIG_PATH

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
    async def delete_mcp_server(name: str,
                                user: Dict = Depends(get_current_user)):
        """删除 MCP 服务器配置。"""
        if not user:
            return {"error": "未登录"}, 401
        from backend.mcp.manager import MCP_CONFIG_PATH

        try:
            if os.path.exists(MCP_CONFIG_PATH):
                with open(MCP_CONFIG_PATH, "r") as f:
                    existing = json.load(f)
                existing["servers"] = [s for s in existing.get("servers", [])
                                       if s.get("name") != name]
                with open(MCP_CONFIG_PATH, "w") as f:
                    json.dump(existing, f, indent=2, ensure_ascii=False)

            tool_registry.unregister_mcp_tools()
            mcp_manager.reload_config_sync()
            sync_mcp_tools()
            return {"success": True, "message": f"MCP 服务器 '{name}' 已删除"}
        except Exception as exc:
            logger.error(f"删除 MCP 服务器 '{name}' 失败: {exc}")
            return {"error": str(exc)}, 500
