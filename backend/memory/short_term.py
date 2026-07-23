import json
from datetime import datetime
from typing import Dict, List, Optional

from backend.database import ShortTermMemory as ShortTermMemoryModel, get_db_session
from backend.context_manager import estimate_token_count


class ShortTermMemory:
    """短期记忆：存储近期对话记录，支持滑窗清理和摘要触发。"""

    # 滑窗上限 — 超过此数量则删除最旧的消息
    SLIDING_WINDOW_SIZE = 100
    # 触发长期摘要的阈值（条数或 token 量，任一达到即触发）
    SUMMARY_THRESHOLD_COUNT = 50
    SUMMARY_THRESHOLD_TOKENS = 4096

    def __init__(self, user_id: int):
        self.user_id = user_id

    # ---- 写入 ----

    def add_turn(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        """添加一条对话记录（user / assistant），自动触发滑窗清理。"""
        db = get_db_session()
        try:
            entry = ShortTermMemoryModel(
                user_id=self.user_id,
                role=role,
                content=content,
                message_count=1,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
            db.add(entry)
            db.flush()

            # 滑窗清理：超出上限则删除最旧的条目
            self._apply_sliding_window(db)

            db.commit()
        finally:
            db.close()

    def add_summary(self, content: str) -> None:
        """添加一条摘要记录（role='summary'），不被滑窗清理。"""
        db = get_db_session()
        try:
            entry = ShortTermMemoryModel(
                user_id=self.user_id,
                role="summary",
                content=content,
            )
            db.add(entry)
            db.commit()
        finally:
            db.close()

    # ---- 查询 ----

    def get_all(self) -> List[Dict]:
        """获取所有记录（按时间升序）。"""
        db = get_db_session()
        try:
            entries = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id
            ).order_by(ShortTermMemoryModel.timestamp.asc()).all()

            return [self._row_to_dict(e) for e in entries]
        finally:
            db.close()

    def get_turns(self, count: int = 10) -> List[Dict]:
        """获取最近 N 条对话记录（只含 user/assistant，不含 summary）。"""
        db = get_db_session()
        try:
            entries = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id,
                ShortTermMemoryModel.role.in_(["user", "assistant"]),
            ).order_by(ShortTermMemoryModel.timestamp.desc()).limit(count).all()

            return [self._row_to_dict(e) for e in reversed(entries)]
        finally:
            db.close()

    def get_summaries(self, count: int = 10) -> List[Dict]:
        """获取最近 N 条摘要记录（role='summary'）。"""
        db = get_db_session()
        try:
            entries = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id,
                ShortTermMemoryModel.role == "summary",
            ).order_by(ShortTermMemoryModel.timestamp.desc()).limit(count).all()

            return [self._row_to_dict(e) for e in entries]
        finally:
            db.close()

    # ---- 统计 ----

    def count_turns(self) -> int:
        """当前对话记录（user/assistant）的总条数。"""
        db = get_db_session()
        try:
            return db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id,
                ShortTermMemoryModel.role.in_(["user", "assistant"]),
            ).count()
        finally:
            db.close()

    def count_all(self) -> Dict[str, int]:
        """各类记录的统计。"""
        db = get_db_session()
        try:
            total = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id
            ).count()
            turns = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id,
                ShortTermMemoryModel.role.in_(["user", "assistant"]),
            ).count()
            summaries = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id,
                ShortTermMemoryModel.role == "summary",
            ).count()
            return {"total": total, "turns": turns, "summaries": summaries}
        finally:
            db.close()

    def total_turn_tokens(self) -> int:
        """所有对话记录的 token 总量。"""
        db = get_db_session()
        try:
            entries = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id,
                ShortTermMemoryModel.role.in_(["user", "assistant"]),
            ).all()
            return sum(estimate_token_count(e.content) for e in entries)
        finally:
            db.close()

    def needs_summary(self) -> bool:
        """判断是否需要对短期对话记录进行总结并存入长期记忆。"""
        return (
            self.count_turns() >= self.SUMMARY_THRESHOLD_COUNT
            or self.total_turn_tokens() >= self.SUMMARY_THRESHOLD_TOKENS
        )

    # ---- 滑窗清理 ----

    def _apply_sliding_window(self, db=None) -> None:
        """保留最新的 SLIDING_WINDOW_SIZE 条对话记录，删除更旧的。

        可由外部调用（传入 db session）或内部自动创建 session 后调用。
        """
        own_session = False
        if db is None:
            db = get_db_session()
            own_session = True

        try:
            # 查所有 user/assistant 记录（最旧在前）
            all_entries = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id,
                ShortTermMemoryModel.role.in_(["user", "assistant"]),
            ).order_by(ShortTermMemoryModel.timestamp.asc()).all()

            if len(all_entries) > self.SLIDING_WINDOW_SIZE:
                # 删除超出上限的最旧条目
                to_delete = all_entries[:len(all_entries) - self.SLIDING_WINDOW_SIZE]
                for entry in to_delete:
                    db.delete(entry)

            if own_session:
                db.commit()
        finally:
            if own_session:
                db.close()

    # ---- 清除 ----

    def clear(self) -> None:
        db = get_db_session()
        try:
            db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id
            ).delete()
            db.commit()
        finally:
            db.close()

    # ---- 工具方法 ----

    @staticmethod
    def _row_to_dict(entry) -> Dict:
        return {
            "id": entry.id,
            "role": entry.role,
            "content": entry.content,
            "message_count": entry.message_count,
            "metadata": json.loads(entry.metadata_json) if entry.metadata_json else {},
            "timestamp": entry.timestamp.timestamp(),
        }
