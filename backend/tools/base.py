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


tool_registry = ToolRegistry()