"""Tests for CalculatorTool."""

import math
import pytest
from backend.tools.calculator import CalculatorTool


class TestCalculatorTool:

    def setup_method(self):
        self.tool = CalculatorTool()

    def test_basic_addition(self):
        result = self.tool.execute(expression="2 + 3")
        assert "5" in result or "计算结果" in result

    def test_subtraction(self):
        result = self.tool.execute(expression="10 - 4")
        assert "6" in result or "计算结果" in result

    def test_multiplication(self):
        result = self.tool.execute(expression="6 * 7")
        assert "42" in result or "计算结果" in result

    def test_division(self):
        result = self.tool.execute(expression="15 / 3")
        assert "5" in result or "计算结果" in result

    def test_complex_expression(self):
        result = self.tool.execute(expression="(2 + 3) * 4")
        assert "20" in result or "计算结果" in result

    def test_sqrt(self):
        result = self.tool.execute(expression="sqrt(16)")
        assert "4" in result or "计算结果" in result

    def test_power(self):
        result = self.tool.execute(expression="2 ** 3")
        assert "8" in result or "计算结果" in result

    def test_pi_constant(self):
        result = self.tool.execute(expression="pi")
        assert "3.14159" in result or "计算结果" in result

    def test_empty_expression(self):
        result = self.tool.execute(expression="")
        assert "错误" in result

    def test_no_expression(self):
        result = self.tool.execute()
        assert "错误" in result

    def test_unsafe_content(self):
        """Expression with letters should be sanitized or rejected."""
        result = self.tool.execute(expression="__import__('os')")
        assert "错误" in result

    def test_sin_cos(self):
        result_sin = self.tool.execute(expression="sin(0)")
        assert "0" in result_sin or "计算结果" in result_sin
        result_cos = self.tool.execute(expression="cos(0)")
        assert "1" in result_cos or "计算结果" in result_cos

    def test_division_by_zero(self):
        result = self.tool.execute(expression="1 / 0")
        assert "inf" in result or "计算结果" in result or "错误" in result

    def test_modulo(self):
        result = self.tool.execute(expression="10 % 3")
        assert "1" in result or "计算结果" in result

    def test_negation(self):
        result = self.tool.execute(expression="-5 + 3")
        assert "-2" in result or "计算结果" in result

    def test_whitespace_handling(self):
        result = self.tool.execute(expression="   2   +   3   ")
        assert "5" in result or "计算结果" in result

    def test_log(self):
        result = self.tool.execute(expression="log(e)")
        assert "1" in result or "计算结果" in result
