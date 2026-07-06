import math
import re
from typing import Dict, Any
from .base import Tool, tool_registry


class CalculatorTool(Tool):
    name = "calculator"
    description = "用于计算数学表达式，支持基本算术运算和常见数学函数"
    parameters = {
        "expression": {
            "type": "string",
            "description": "要计算的数学表达式，例如：2 + 3 * 4 或 sqrt(16)"
        }
    }

    def execute(self, **kwargs) -> str:
        expression = kwargs.get("expression", "")
        if not expression:
            return "错误：请提供要计算的表达式"

        safe_expr = self._sanitize_expression(expression)
        if not safe_expr:
            return "错误：表达式包含不安全的内容"

        try:
            result = eval(safe_expr, {"__builtins__": None}, {
                "abs": abs,
                "sqrt": math.sqrt,
                "pow": pow,
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "log": math.log,
                "log10": math.log10,
                "exp": math.exp,
                "pi": math.pi,
                "e": math.e,
                "+": lambda x, y: x + y,
                "-": lambda x, y: x - y,
                "*": lambda x, y: x * y,
                "/": lambda x, y: x / y if y != 0 else float('inf'),
                "%": lambda x, y: x % y if y != 0 else 0,
                "**": lambda x, y: x ** y,
            })
            return f"计算结果：{result}"
        except Exception as e:
            return f"计算错误：{str(e)}"

    def _sanitize_expression(self, expression: str) -> str:
        allowed_pattern = re.compile(r'^[0-9+\-*/().%^ \t\nsqrtpow sincostanloglog10exp pie]+$')
        if allowed_pattern.match(expression):
            return expression.replace('^', '**')
        return ""


tool_registry.register(CalculatorTool())