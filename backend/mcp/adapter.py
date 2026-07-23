"""
MCP 工具适配器。

将 MCP 工具包装为 Jarvis 原生的 Tool 接口，
使 Agent 可以无缝调用 MCP 工具。
"""
import logging
from typing import Any, Dict, Optional

from backend.tools.base import Tool

logger = logging.getLogger(__name__)


class MCPToolAdapter(Tool):
    """适配 MCP 工具到 Jarvis Tool 接口。"""

    def __init__(self, name: str, description: str, input_schema: Dict[str, Any]):
        self.name = name
        self.description = description
        # 将 JSON Schema 转为 Jarvis parameters 格式
        self.parameters = self._convert_schema(input_schema)
        self._input_schema = input_schema
        self._tool_description_for_llm = ""

    def _convert_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """将 JSON Schema 转为 Jarvis 统一的参数格式。"""
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        params = {}
        for param_name, param_info in properties.items():
            params[param_name] = {
                "type": param_info.get("type", "string"),
                "description": param_info.get("description", ""),
                "required": param_name in required,
            }
        return params

    def execute(self, **kwargs) -> str:
        """执行 MCP 工具（从 Agent 线程调用）。"""
        from .manager import mcp_manager

        try:
            result = mcp_manager.call_tool_sync(self.name, kwargs)
            return result
        except ValueError as e:
            return f"MCP 工具不存在: {e}"
        except RuntimeError as e:
            return f"MCP 工具调用失败: {e}"
        except Exception as e:
            logger.exception(f"MCP 工具执行异常 '{self.name}': {e}")
            return f"MCP 工具执行错误: {str(e)}"

    @classmethod
    def from_mcp_tool_info(cls, tool_info: Dict[str, Any]) -> "MCPToolAdapter":
        """从 MCP 管理器返回的工具信息创建适配器。"""
        return cls(
            name=tool_info["name"],
            description=tool_info.get("description", ""),
            input_schema=tool_info.get("input_schema", {}),
        )
