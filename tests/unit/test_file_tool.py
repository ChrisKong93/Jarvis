"""Tests for FileTool."""

import os
import tempfile

import pytest
from backend.tools.file_tool import FileTool


class TestFileTool:

    def setup_method(self):
        self.tool = FileTool()

    def test_write_and_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")
            write_result = self.tool.execute(
                action="write", file_path=file_path, content="Hello, World!"
            )
            assert "成功" in write_result or "写入" in write_result

            read_result = self.tool.execute(action="read", file_path=file_path)
            assert "Hello, World!" in read_result

    def test_append_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "append.txt")
            self.tool.execute(action="write", file_path=file_path, content="Line 1\n")
            self.tool.execute(action="write", file_path=file_path, content="Line 2\n", append=True)

            read_result = self.tool.execute(action="read", file_path=file_path)
            assert "Line 1" in read_result
            assert "Line 2" in read_result

    def test_read_non_existent_file(self):
        result = self.tool.execute(action="read", file_path="/tmp/non_existent_file_xyz.txt")
        assert "错误" in result

    def test_empty_action(self):
        result = self.tool.execute(action="", file_path="/tmp/test.txt")
        assert "错误" in result

    def test_empty_file_path(self):
        result = self.tool.execute(action="read", file_path="")
        assert "错误" in result

    def test_unknown_action(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "f.txt")
            result = self.tool.execute(action="unknown", file_path=path)
            assert "错误" in result
            assert "未知" in result

    def test_empty_content_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "empty.txt")
            result = self.tool.execute(action="write", file_path=file_path, content="")
            assert "成功" in result or "写入" in result

            read_result = self.tool.execute(action="read", file_path=file_path)
            assert "成功" in read_result or "文件内容" in read_result

    def test_write_to_nested_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = os.path.join(tmpdir, "subdir", "test.txt")
            result = self.tool.execute(
                action="write", file_path=nested_path, content="test"
            )
            # Should fail because directory doesn't exist
            assert "错误" in result

    def test_tool_metadata(self):
        assert self.tool.name == "file"
        assert self.tool.description
        assert "action" in self.tool.parameters
        assert "file_path" in self.tool.parameters
