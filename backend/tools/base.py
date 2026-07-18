from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class Tool(ABC):
    name: str
    description: str
    parameters: Dict[str, Any]

    @abstractmethod
    def execute(self, **kwargs) -> str:
        pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """注销一个工具，返回是否成功。"""
        if name in self.tools:
            del self.tools[name]
            return True
        return False

    def is_registered(self, name: str) -> bool:
        """检查工具是否已注册。"""
        return name in self.tools

    def get_tool(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)

    def get_tools_list(self) -> list:
        return [tool.to_dict() for tool in self.tools.values()]

    def get_tool_descriptions(self) -> str:
        descriptions = []
        for tool in self.tools.values():
            params_desc = []
            for param_name, param_info in tool.parameters.items():
                param_type = param_info.get('type', 'string')
                param_desc = param_info.get('description', '')
                params_desc.append(f"  {param_name}: {param_type} - {param_desc}")
            params_str = "\n".join(params_desc)
            descriptions.append(f"- {tool.name}: {tool.description}\n参数:\n{params_str}")
        return "\n\n".join(descriptions)

    def register_mcp_tools(self, mcp_tools_info: list) -> int:
        """批量注册 MCP 工具，返回注册数量。"""
        from backend.mcp.adapter import MCPToolAdapter

        count = 0
        for tool_info in mcp_tools_info:
            name = tool_info["name"]
            adapter = MCPToolAdapter.from_mcp_tool_info(tool_info)
            self.register(adapter)
            count += 1
        return count

    def unregister_mcp_tools(self) -> int:
        """注销所有 MCP 适配器工具，返回注销数量。"""
        count = 0
        to_remove = [
            name for name, tool in self.tools.items()
            if type(tool).__module__.startswith("backend.mcp.")
            or type(tool).__name__ == "MCPToolAdapter"
        ]
        for name in to_remove:
            del self.tools[name]
            count += 1
        return count


tool_registry = ToolRegistry()