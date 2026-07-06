from backend.tools.base import Tool, tool_registry

class FileTool(Tool):
    name = "file"
    description = "文件操作工具，支持读取和写入文件"
    parameters = {
        "action": {"type": "string", "description": "操作类型：read（读取）或 write（写入）", "required": True},
        "file_path": {"type": "string", "description": "文件路径", "required": True},
        "content": {"type": "string", "description": "要写入的内容（仅 write 操作需要）"},
        "append": {"type": "boolean", "description": "是否追加模式（仅 write 操作）", "default": False}
    }

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "").lower()
        file_path = kwargs.get("file_path", "")
        
        if not action or not file_path:
            return "错误：请提供 action 和 file_path 参数"

        if action == "read":
            return self._read_file(file_path)
        elif action == "write":
            content = kwargs.get("content", "")
            append = kwargs.get("append", False)
            return self._write_file(file_path, content, append)
        else:
            return f"错误：未知操作类型: {action}"

    def _read_file(self, file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return f"文件内容读取成功（前5000字符）：\n{content[:5000]}"
        except FileNotFoundError:
            return f"错误：文件不存在: {file_path}"
        except Exception as e:
            return f"错误：{str(e)}"

    def _write_file(self, file_path: str, content: str, append: bool) -> str:
        try:
            mode = 'a' if append else 'w'
            with open(file_path, mode, encoding='utf-8') as f:
                f.write(content)
            return f"内容{'追加' if append else '写入'}成功: {file_path}"
        except Exception as e:
            return f"错误：{str(e)}"

tool_registry.register(FileTool())