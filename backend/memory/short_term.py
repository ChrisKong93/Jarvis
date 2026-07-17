import json
from datetime import datetime
from typing import Dict, List, Optional

from backend.database import ShortTermMemory as ShortTermMemoryModel, get_db_session


class ShortTermMemory:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.max_summaries = 10

    def add_summary(self, messages: List[Dict], summary: str) -> None:
        db = get_db_session()
        try:
            entry = ShortTermMemoryModel(
                user_id=self.user_id,
                summary=summary,
                message_count=len(messages),
                key_points=json.dumps(self._extract_key_points(summary), ensure_ascii=False),
            )
            db.add(entry)

            all_entries = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id
            ).order_by(ShortTermMemoryModel.timestamp.desc()).all()

            if len(all_entries) > self.max_summaries:
                # 将最旧的超量条目合并压缩，而非直接丢弃
                old_entries = all_entries[self.max_summaries:]
                old_texts = [e.summary for e in old_entries if e.summary.strip()]
                for old in old_entries:
                    db.delete(old)

                if old_texts:
                    merged_summary = "【历史摘要合并】\n" + "\n---\n".join(old_texts)
                    merged_entry = ShortTermMemoryModel(
                        user_id=self.user_id,
                        summary=merged_summary,
                        message_count=sum(e.message_count for e in old_entries),
                        key_points=json.dumps(
                            [t[:50] for t in old_texts][:5],
                            ensure_ascii=False,
                        ),
                    )
                    db.add(merged_entry)

            db.commit()
        finally:
            db.close()

    def _extract_key_points(self, summary: str) -> List[str]:
        lines = summary.split('\n')
        key_points = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('-'):
                key_points.append(line[:50])
        return key_points[:5]

    def get_recent_summaries(self, count: int = 3) -> List[Dict]:
        db = get_db_session()
        try:
            entries = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id
            ).order_by(ShortTermMemoryModel.timestamp.desc()).limit(count).all()

            return [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.timestamp(),
                    "summary": e.summary,
                    "message_count": e.message_count,
                    "key_points": json.loads(e.key_points) if e.key_points else []
                }
                for e in entries
            ]
        finally:
            db.close()

    def get_all_summaries(self) -> List[Dict]:
        db = get_db_session()
        try:
            entries = db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id
            ).order_by(ShortTermMemoryModel.timestamp.desc()).all()

            return [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.timestamp(),
                    "summary": e.summary,
                    "message_count": e.message_count,
                    "key_points": json.loads(e.key_points) if e.key_points else []
                }
                for e in entries
            ]
        finally:
            db.close()

    def clear(self) -> None:
        db = get_db_session()
        try:
            db.query(ShortTermMemoryModel).filter(
                ShortTermMemoryModel.user_id == self.user_id
            ).delete()
            db.commit()
        finally:
            db.close()

    def get_summary_text(self, count: int = 3) -> str:
        summaries = self.get_recent_summaries(count)
        if not summaries:
            return ""

        result = "近期对话总结：\n"
        for i, summary in enumerate(summaries, 1):
            result += f"{i}. {summary['summary']}\n"
        return result.strip()
