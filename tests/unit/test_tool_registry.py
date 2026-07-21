"""Tests for ToolRegistry."""

import pytest
from backend.tools.base import Tool, ToolRegistry


class _DummyTool(Tool):
    name = "dummy"
    description = "A dummy tool"
    parameters = {"param1": {"type": "string", "description": "Test param"}}

    def execute(self, **kwargs) -> str:
        return f"dummy executed with {kwargs}"


class _AnotherTool(Tool):
    name = "another"
    description = "Another tool"
    parameters = {"foo": {"type": "integer", "description": "Foo"}}

    def execute(self, **kwargs) -> str:
        return f"another executed with {kwargs}"


class TestToolRegistry:

    def setup_method(self):
        self.registry = ToolRegistry()

    def test_register_and_get(self):
        tool = _DummyTool()
        self.registry.register(tool)
        assert self.registry.is_registered("dummy")
        assert self.registry.get_tool("dummy") is tool

    def test_register_overwrite(self):
        tool1 = _DummyTool()
        tool2 = _AnotherTool()
        self.registry.register(tool1)
        self.registry.register(tool2)  # different name, both kept
        assert self.registry.is_registered("dummy")
        assert self.registry.is_registered("another")

    def test_unregister_existing(self):
        self.registry.register(_DummyTool())
        assert self.registry.unregister("dummy") is True
        assert not self.registry.is_registered("dummy")

    def test_unregister_non_existing(self):
        assert self.registry.unregister("nonexistent") is False

    def test_get_tools_list(self):
        self.registry.register(_DummyTool())
        self.registry.register(_AnotherTool())
        tools_list = self.registry.get_tools_list()
        assert len(tools_list) == 2
        names = {t["name"] for t in tools_list}
        assert names == {"dummy", "another"}

    def test_get_tool_descriptions(self):
        self.registry.register(_DummyTool())
        desc = self.registry.get_tool_descriptions()
        assert "dummy" in desc
        assert "Dummy" in desc or "dummy" in desc

    def test_empty_registry(self):
        assert self.registry.get_tools_list() == []
        assert self.registry.get_tool("anything") is None
        assert not self.registry.is_registered("anything")

    def test_register_mcp_tools_with_empty_list(self):
        count = self.registry.register_mcp_tools([])
        assert count == 0

    def test_get_tool_returns_none_for_missing(self):
        assert self.registry.get_tool("missing") is None
