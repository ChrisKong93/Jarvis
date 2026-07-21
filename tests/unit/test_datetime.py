"""Tests for DateTimeTool."""

import pytest
from backend.tools.datetime_tool import DateTimeTool


class TestDateTimeTool:

    def setup_method(self):
        self.tool = DateTimeTool()

    def test_action_now(self):
        result = self.tool.execute(action="now")
        assert "当前时间" in result or "日期" in result or "时间" in result

    def test_action_now_lowercase(self):
        result = self.tool.execute(action="now")
        assert result is not None

    def test_timer_invalid_seconds_zero(self):
        result = self.tool.execute(action="timer", seconds=0, message="test")
        assert "错误" in result

    def test_timer_invalid_seconds_negative(self):
        result = self.tool.execute(action="timer", seconds=-5, message="test")
        assert "错误" in result

    def test_timer_exceeds_limit(self):
        result = self.tool.execute(action="timer", seconds=301, message="test")
        assert "错误" in result
        assert "最长" in result

    def test_empty_action(self):
        result = self.tool.execute(action="")
        assert "错误" in result

    def test_unknown_action(self):
        result = self.tool.execute(action="invalid_action")
        assert "错误" in result
        assert "未知" in result

    def test_get_current_time_format(self):
        time_str = self.tool._get_current_time()
        assert "年" in time_str
        assert "月" in time_str
        assert "日" in time_str
        assert "星期" in time_str or "周" in time_str
        assert ":" in time_str  # HH:MM:SS

    def test_tool_metadata(self):
        assert self.tool.name == "datetime"
        assert self.tool.description
        assert "action" in self.tool.parameters
