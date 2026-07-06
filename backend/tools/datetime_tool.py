from backend.tools.base import Tool, tool_registry
import datetime
import time

class DateTimeTool(Tool):
    name = "datetime"
    description = "日期时间工具，支持获取当前时间和设置定时器"
    parameters = {
        "action": {"type": "string", "description": "操作类型：now（获取当前时间）或 timer（设置定时器）", "required": True},
        "seconds": {"type": "integer", "description": "定时秒数（仅 timer 操作需要，最长300秒）"},
        "message": {"type": "string", "description": "提醒消息（仅 timer 操作需要）", "default": "时间到！"}
    }

    def execute(self, **kwargs) -> str:
        action = kwargs.get("action", "").lower()
        
        if not action:
            return "错误：请提供 action 参数"

        if action == "now":
            return self._get_current_time()
        elif action == "timer":
            seconds = kwargs.get("seconds", 0)
            message = kwargs.get("message", "时间到！")
            return self._set_timer(seconds, message)
        else:
            return f"错误：未知操作类型: {action}"

    def _get_current_time(self) -> str:
        now = datetime.datetime.now()
        return f"""当前时间信息：
- 日期：{now.strftime('%Y年%m月%d日')}
- 时间：{now.strftime('%H:%M:%S')}
- 星期：{['周一', '周二', '周三', '周四', '周五', '周六', '周日'][now.weekday()]}
- 时间戳：{int(time.time())}
- ISO格式：{now.isoformat()}"""

    def _set_timer(self, seconds: int, message: str) -> str:
        if seconds <= 0:
            return "错误：秒数必须大于0"
        if seconds > 300:
            return "错误：定时器最长支持5分钟"
        
        time.sleep(seconds)
        return f"⏰ {message}"

tool_registry.register(DateTimeTool())