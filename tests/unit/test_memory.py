"""Tests for memory components (pure logic, no DB dependency)."""

import pytest
from backend.memory.short_term import ShortTermMemory
from backend.memory.long_term import LongTermMemory


class TestShortTermMemoryLogic:

    def test_extract_key_points_empty(self):
        memory = ShortTermMemory(user_id=1)
        points = memory._extract_key_points("")
        assert points == []

    def test_extract_key_points_single_line(self):
        memory = ShortTermMemory(user_id=1)
        points = memory._extract_key_points("用户询问了天气情况")
        assert len(points) >= 1
        assert "用户询问了天气情况" in points[0]

    def test_extract_key_points_skips_dash_lines(self):
        memory = ShortTermMemory(user_id=1)
        text = "概要信息\n- 这是一个副信息\n另一个重要点"
        points = memory._extract_key_points(text)
        assert "概要信息" in points
        assert "另一个重要点" in points
        # Lines starting with '-' should not be in key_points
        assert not any(p.startswith("-") for p in points)

    def test_extract_key_points_truncates_long_lines(self):
        memory = ShortTermMemory(user_id=1)
        long_text = "a" * 100
        points = memory._extract_key_points(long_text)
        assert len(points[0]) <= 50

    def test_extract_key_points_max_count(self):
        memory = ShortTermMemory(user_id=1)
        lines = "\n".join([f"Point {i}" for i in range(10)])
        points = memory._extract_key_points(lines)
        assert len(points) <= 5


class TestLongTermMemoryLogic:

    def test_calculate_similarity_identical(self):
        sim = LongTermMemory._calculate_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_calculate_similarity_partial(self):
        sim = LongTermMemory._calculate_similarity("hello world foo", "hello world bar")
        assert sim == 0.5  # 2 words overlap out of 4 unique words

    def test_calculate_similarity_no_overlap(self):
        sim = LongTermMemory._calculate_similarity("abc def", "ghi jkl")
        assert sim == 0.0

    def test_calculate_similarity_case_insensitive(self):
        sim = LongTermMemory._calculate_similarity("Hello World", "hello world")
        assert sim == 1.0

    def test_calculate_similarity_both_empty(self):
        sim = LongTermMemory._calculate_similarity("", "")
        assert sim == 1.0

    def test_calculate_similarity_one_empty(self):
        sim = LongTermMemory._calculate_similarity("hello", "")
        assert sim == 0.0

    def test_calculate_similarity_repeated_words(self):
        sim = LongTermMemory._calculate_similarity("hello hello world", "hello world")
        # Union removes duplicates
        assert sim == 1.0

    def test_id_format(self):
        memory = LongTermMemory(user_id=1)
        mid = memory._generate_id("test content")
        assert isinstance(mid, str)
        assert len(mid) == 16  # MD5[:16]
