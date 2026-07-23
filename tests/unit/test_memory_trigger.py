"""测试短期记忆和长期记忆的触发逻辑。

测试范围：
1. 短期记忆摘要触发阈值（条数和 token 量）
2. 短期记忆的存储（add_turn / add_summary）和查询
3. 滑窗清理逻辑
4. 长期记忆的去重和降级检索
5. 边界情况

使用方法：
    cd Jarvis && python3 -m pytest tests/unit/test_memory_trigger.py -v
"""

import os
import json
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# Helper: 设置临时 SQLite 数据库
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tmp_db():
    """创建临时 SQLite 数据库，自动创建表。"""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from backend.database import Base
    Base.metadata.create_all(bind=engine)

    yield engine, TestingSessionLocal

    engine.dispose()
    if os.path.exists(db_path):
        os.unlink(db_path)


def _create_test_user(tmp_db, username="test_user", email="test@test.com"):
    """辅助：在临时数据库中创建并返回 user_id。"""
    engine, TestingSessionLocal = tmp_db
    db = TestingSessionLocal()
    from backend.database import User
    user = User(username=username, email=email, hashed_password="x")
    db.add(user)
    db.commit()
    uid = user.id
    db.close()
    return uid


@pytest.fixture(autouse=True)
def patch_db(tmp_db):
    """将 backend.database.get_db_session 替换为临时数据库。"""
    engine, TestingSessionLocal = tmp_db
    with patch("backend.database.get_db_session", side_effect=TestingSessionLocal):
        yield


# ===================================================================
# 1. 摘要触发逻辑
# ===================================================================

class TestSummaryTrigger:
    """测试 ShortTermMemory.needs_summary() 的触发逻辑。"""

    def test_no_turns_no_trigger(self, tmp_db):
        """没有任何对话记录时，不应触发。"""
        user_id = _create_test_user(tmp_db, "trigger_none", "none@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)
        assert memory.needs_summary() is False

    def test_below_count_threshold(self, tmp_db):
        """对话条数未达到阈值时，不应触发。"""
        user_id = _create_test_user(tmp_db, "trigger_below", "below@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)
        for i in range(49):
            memory.add_turn("user", f"msg{i}")
        assert memory.needs_summary() is False

    def test_at_count_threshold(self, tmp_db):
        """对话条数达到 50 条时应触发。"""
        user_id = _create_test_user(tmp_db, "trigger_50", "t50@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)
        for i in range(50):
            memory.add_turn("user", f"msg{i}")
        assert memory.needs_summary() is True

    def test_below_token_threshold(self, tmp_db):
        """token 量低于 4096 时，不应触发。"""
        user_id = _create_test_user(tmp_db, "trigger_tok_below", "tok_below@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)
        # "a" 是 1 个英文词 → 0 个 token（word // 2）
        for i in range(10):
            memory.add_turn("user", "a")
        assert memory.needs_summary() is False

    def test_at_token_threshold(self, tmp_db):
        """token 量达到 4096 时应触发。"""
        user_id = _create_test_user(tmp_db, "trigger_tok_4096", "tok4096@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)
        # 4097 个中文字符 → 4097 个 token（中文按字符数计）
        long_text = "一" * 4097
        memory.add_turn("user", long_text)
        assert memory.needs_summary() is True

    def test_needs_summary_after_summarize_resets_count(self, tmp_db):
        """生成摘要后 count_turns 减少，needs_summary 应重新变为 False。"""
        user_id = _create_test_user(tmp_db, "trigger_after", "after@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)
        for i in range(50):
            memory.add_turn("user", f"msg{i}")
        assert memory.needs_summary() is True

        # 清空对话（模拟生产代码中 summarize 后清理或降低数量）
        memory.clear()
        assert memory.needs_summary() is False


# ===================================================================
# 2. 短期记忆存储和滑窗清理
# ===================================================================

class TestShortTermStorage:
    """测试短期记忆的 add_turn / add_summary 和滑窗清理。"""

    def test_add_turn(self, tmp_db):
        """写入一条对话记录，验证能正确查询。"""
        user_id = _create_test_user(tmp_db, "st_turn", "turn@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        memory.add_turn("user", "你好")
        memory.add_turn("assistant", "你好！有什么可以帮助你的吗？")

        all_records = memory.get_all()
        assert len(all_records) == 2
        assert all_records[0]["role"] == "user"
        assert all_records[0]["content"] == "你好"
        assert all_records[1]["role"] == "assistant"
        assert all_records[1]["content"] == "你好！有什么可以帮助你的吗？"

    def test_add_turn_with_metadata(self, tmp_db):
        """写入对话记录时可以附带 metadata。"""
        user_id = _create_test_user(tmp_db, "st_meta", "meta@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        memory.add_turn("user", "你好", metadata={"plan": "打招呼"})
        records = memory.get_all()
        assert records[0]["metadata"]["plan"] == "打招呼"

    def test_add_summary(self, tmp_db):
        """写入摘要，验证 role 为 summary。"""
        user_id = _create_test_user(tmp_db, "st_summary", "sum@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        memory.add_summary("用户打招呼，助手回应")

        all_records = memory.get_all()
        assert len(all_records) == 1
        assert all_records[0]["role"] == "summary"
        assert all_records[0]["content"] == "用户打招呼，助手回应"

    def test_get_turns_only_returns_turns(self, tmp_db):
        """get_turns 只应返回 user/assistant 记录，不含 summary。"""
        user_id = _create_test_user(tmp_db, "st_turns_only", "turns_only@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        memory.add_turn("user", "你好")
        memory.add_turn("assistant", "回复")
        memory.add_summary("对话摘要")

        turns = memory.get_turns(count=10)
        assert len(turns) == 2
        assert all(t["role"] in ("user", "assistant") for t in turns)

    def test_get_summaries_only_returns_summaries(self, tmp_db):
        """get_summaries 只应返回 summary 记录。"""
        user_id = _create_test_user(tmp_db, "st_sums_only", "sums_only@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        memory.add_turn("user", "你好")
        memory.add_summary("摘要A")
        memory.add_summary("摘要B")

        summaries = memory.get_summaries(count=10)
        assert len(summaries) == 2
        assert all(s["role"] == "summary" for s in summaries)

    def test_get_turns_returns_latest(self, tmp_db):
        """get_turns 应返回最近的 N 条记录。"""
        user_id = _create_test_user(tmp_db, "st_latest", "latest@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        for i in range(10):
            memory.add_turn("user", f"msg{i}")

        turns = memory.get_turns(count=3)
        assert len(turns) == 3
        # 最近 3 条：msg7, msg8, msg9（按时间升序返回）
        assert [t["content"] for t in turns] == ["msg7", "msg8", "msg9"]

    def test_sliding_window_basic(self, tmp_db):
        """超过 SLIDING_WINDOW_SIZE(100) 时，最旧的记录应被删除。"""
        user_id = _create_test_user(tmp_db, "st_slide", "slide@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        # 写入 101 条（超过 100 的上限）
        for i in range(101):
            memory.add_turn("user", f"msg{i}")

        all_records = memory.get_all()
        assert len(all_records) == 100

        # 最早保留的是 msg1 而非 msg0
        contents = [r["content"] for r in all_records]
        assert "msg0" not in contents
        assert contents[0] == "msg1"

    def test_sliding_window_preserves_summaries(self, tmp_db):
        """滑窗清理只清理 user/assistant 记录，summary 不应被清理。"""
        user_id = _create_test_user(tmp_db, "st_preserve", "preserve@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        # 写入 100 条对话 + 10 条摘要
        for i in range(100):
            memory.add_turn("user", f"msg{i}")
        for i in range(10):
            memory.add_summary(f"摘要{i}")

        # 再写 1 条触发滑窗清理
        memory.add_turn("user", "overflow")

        all_records = memory.get_all()
        summaries = [r for r in all_records if r["role"] == "summary"]
        assert len(summaries) == 10  # 摘要应全部保留

    def test_clear(self, tmp_db):
        """clear 应清空所有记录。"""
        user_id = _create_test_user(tmp_db, "st_clear", "clear@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        memory.add_turn("user", "你好")
        memory.add_summary("摘要")
        assert len(memory.get_all()) > 0

        memory.clear()
        assert len(memory.get_all()) == 0


# ===================================================================
# 3. 统计数据
# ===================================================================

class TestShortTermStats:
    """测试短期记忆的统计方法。"""

    def test_count_turns(self, tmp_db):
        """count_turns 应只统计 user/assistant 记录。"""
        user_id = _create_test_user(tmp_db, "stats_turns", "st_turns@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        memory.add_turn("user", "你好")
        memory.add_turn("assistant", "回复")
        memory.add_summary("摘要")

        assert memory.count_turns() == 2

    def test_count_all(self, tmp_db):
        """count_all 应返回各类记录的统计。"""
        user_id = _create_test_user(tmp_db, "stats_all", "st_all@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        for i in range(5):
            memory.add_turn("user", f"msg{i}")
        memory.add_summary("摘要A")
        memory.add_summary("摘要B")

        counts = memory.count_all()
        assert counts["total"] == 7
        assert counts["turns"] == 5
        assert counts["summaries"] == 2

    def test_total_turn_tokens_excludes_summaries(self, tmp_db):
        """total_turn_tokens 不应包含 summary 记录。"""
        user_id = _create_test_user(tmp_db, "stats_tokens", "st_tokens@test.com")
        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)

        memory.add_summary("很长很长的摘要内容" * 100)  # 摘要不应计入
        memory.add_turn("user", "a")                    # "a" → 0 token

        tokens = memory.total_turn_tokens()
        assert tokens == 0


# ===================================================================
# 4. 长期记忆去重和检索
# ===================================================================

class TestLongTermStorage:
    """测试长期记忆的 add_memory 和去重逻辑。"""

    def test_add_and_retrieve_by_keyword(self, tmp_db):
        """写入一条长期记忆，验证 keyword fallback 能检索到。

        注意：ChromaDB 未安装时会降级为 keyword 检索。
        keyword 检索使用 split() 分词，所以测试内容用英文词。
        """
        user_id = _create_test_user(tmp_db, "test_long", "long@test.com")

        from backend.memory.long_term import LongTermMemory
        memory = LongTermMemory(user_id=user_id)

        mid = memory.add_memory("user likes Python programming", category="preference")
        assert mid is not None
        assert len(mid) == 16

        results = memory.retrieve_memories("Python", top_k=5)
        assert len(results) >= 1
        assert any("Python" in r["content"] for r in results)

        results_no_match = memory.retrieve_memories("golang", top_k=5)
        assert len(results_no_match) == 0

    def test_dedup_similar_content_keyword(self, tmp_db):
        """验证 keyword fallback 模式下相似内容去重。"""
        user_id = _create_test_user(tmp_db, "test_dedup", "dedup@test.com")

        from backend.memory.long_term import LongTermMemory
        memory = LongTermMemory(user_id=user_id)

        # 6 个词的基础文本
        mid1 = memory.add_memory("user likes eating hot pot food", category="preference")
        # 内容完全不同 → 应插入新记录
        mid_diff = memory.add_memory("user lives in Shanghai", category="knowledge")
        assert mid_diff != mid1

        # 仅多 1 个词 → Jaccard = 6/7 ≈ 0.857 ≥ 0.85 → 应返回相同 id
        mid2 = memory.add_memory("user likes eating hot pot food very", category="preference")
        assert mid1 == mid2

    def test_calculate_similarity(self):
        """测试 Jaccard 相似度计算（降级路径使用）。"""
        from backend.memory.long_term import LongTermMemory
        calc = LongTermMemory._calculate_similarity

        assert calc("hello world", "hello world") == 1.0
        assert calc("", "") == 1.0
        assert calc("abc def", "ghi jkl") == 0.0
        assert calc("Hello World", "hello world") == 1.0
        assert calc("hello world foo", "hello world bar") == 0.5


# ===================================================================
# 5. 模拟完整触发流程
# ===================================================================

class TestFullTriggerFlow:
    """模拟 _update_memories 的完整流程。"""

    def test_short_term_flow(self, tmp_db):
        """测试完整的短期记忆写入 → 摘要触发流程。"""
        user_id = _create_test_user(tmp_db, "test_flow_st", "flow_st@test.com")

        from backend.memory.short_term import ShortTermMemory
        short_mem = ShortTermMemory(user_id=user_id)

        # 添加 50 条对话记录，触发 count 阈值
        for i in range(50):
            short_mem.add_turn("user", f"用户消息{i}")

        assert short_mem.needs_summary() is True

        # 生成摘要并写入
        short_mem.add_summary("用户进行了多轮对话，内容涉及测试。")

        # 验证摘要已写入（clear 不会在真实流程中使用）
        summaries = short_mem.get_summaries(count=10)
        assert any("多轮对话" in s["content"] for s in summaries)

    def test_long_term_flow(self, tmp_db):
        """测试完整的长期记忆写入→检索流程。"""
        user_id = _create_test_user(tmp_db, "test_flow_lt", "flow_lt@test.com")

        from backend.memory.long_term import LongTermMemory
        long_mem = LongTermMemory(user_id=user_id)

        mid = long_mem.add_memory("user is learning FastAPI framework", category="knowledge")
        assert mid is not None

        # 检索（keyword fallback）
        results = long_mem.retrieve_memories("learning FastAPI", top_k=5)
        assert len(results) >= 1
        assert any("learning FastAPI" in r["content"] for r in results)

    def test_long_term_dedup_same_content(self, tmp_db):
        """完全相同的 long-term 内容应去重，返回相同 id。"""
        user_id = _create_test_user(tmp_db, "test_lt_dedup", "lt_dedup@test.com")

        from backend.memory.long_term import LongTermMemory
        long_mem = LongTermMemory(user_id=user_id)

        mid1 = long_mem.add_memory("user likes Python", category="preference")
        mid2 = long_mem.add_memory("user likes Python", category="preference")
        assert mid1 == mid2


# ===================================================================
# 6. 边界情况和一致性
# ===================================================================

class TestEdgeCases:

    def test_empty_content_no_crash(self, tmp_db):
        """空内容不应导致崩溃。"""
        user_id = _create_test_user(tmp_db, "test_edge", "edge@test.com")

        from backend.memory.short_term import ShortTermMemory
        memory = ShortTermMemory(user_id=user_id)
        memory.add_turn("user", "")
        memory.add_summary("")
        all_records = memory.get_all()
        assert len(all_records) == 2

    def test_get_stats_consistency(self, tmp_db):
        """get_stats 和 get_all_memories 的返回值应一致。"""
        user_id = _create_test_user(tmp_db, "test_stats", "stats@test.com")

        from backend.memory import MemoryManager
        mgr = MemoryManager()

        # 写入一些数据
        mgr.add_short_term_turn(user_id, "user", "你好")
        mgr.add_short_term_turn(user_id, "assistant", "回复")
        mgr.add_short_term_summary(user_id, "摘要")

        stats = mgr.get_stats(user_id)
        all_mem = mgr.get_all_memories(user_id)
        assert stats["short_term_count"] == len(all_mem["short_term"])
        assert stats["long_term_count"] == len(all_mem["long_term"])
