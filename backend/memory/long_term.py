import hashlib
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

from backend.database import LongTermMemory as LongTermMemoryModel, get_db_session


class LongTermMemory:
    def __init__(self, user_id: int):
        self.user_id = user_id

    def _generate_id(self, content: str) -> str:
        return hashlib.md5(f"{content}{time.time()}".encode()).hexdigest()[:16]

    def add_memory(self, content: str, category: str = "general", metadata: Optional[Dict] = None) -> str:
        db = get_db_session()
        try:
            memory_id = self._generate_id(content)
            entry = LongTermMemoryModel(
                user_id=self.user_id,
                memory_id=memory_id,
                content=content,
                category=category,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
            db.add(entry)
            db.commit()
            return memory_id
        finally:
            db.close()

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union

    def retrieve_memories(self, query: str, top_k: int = 5, min_similarity: float = 0.1) -> List[Dict]:
        db = get_db_session()
        try:
            entries = db.query(LongTermMemoryModel).filter(
                LongTermMemoryModel.user_id == self.user_id
            ).all()

            results = []
            now = datetime.utcnow()

            for e in entries:
                similarity = self._calculate_similarity(query, e.content)
                if similarity >= min_similarity:
                    e.last_accessed_at = now
                    e.access_count += 1
                    results.append({
                        "similarity": round(similarity, 3),
                        "id": e.memory_id,
                        "content": e.content,
                        "category": e.category,
                        "metadata": json.loads(e.metadata_json) if e.metadata_json else {},
                        "created_at": e.created_at.timestamp(),
                        "last_accessed_at": e.last_accessed_at.timestamp(),
                        "access_count": e.access_count,
                    })

            db.commit()
            results.sort(key=lambda x: x["similarity"], reverse=True)
            return results[:top_k]
        finally:
            db.close()

    def get_memories_by_category(self, category: str) -> List[Dict]:
        db = get_db_session()
        try:
            entries = db.query(LongTermMemoryModel).filter(
                LongTermMemoryModel.user_id == self.user_id,
                LongTermMemoryModel.category == category,
            ).all()

            return [
                {
                    "id": e.memory_id,
                    "content": e.content,
                    "category": e.category,
                    "metadata": json.loads(e.metadata_json) if e.metadata_json else {},
                    "created_at": e.created_at.timestamp(),
                    "last_accessed_at": e.last_accessed_at.timestamp(),
                    "access_count": e.access_count,
                }
                for e in entries
            ]
        finally:
            db.close()

    def delete_memory(self, memory_id: str) -> bool:
        db = get_db_session()
        try:
            entry = db.query(LongTermMemoryModel).filter(
                LongTermMemoryModel.user_id == self.user_id,
                LongTermMemoryModel.memory_id == memory_id,
            ).first()

            if not entry:
                return False

            db.delete(entry)
            db.commit()
            return True
        finally:
            db.close()

    def clear(self) -> None:
        db = get_db_session()
        try:
            db.query(LongTermMemoryModel).filter(
                LongTermMemoryModel.user_id == self.user_id
            ).delete()
            db.commit()
        finally:
            db.close()

    def get_all_memories(self) -> List[Dict]:
        db = get_db_session()
        try:
            entries = db.query(LongTermMemoryModel).filter(
                LongTermMemoryModel.user_id == self.user_id
            ).all()

            return [
                {
                    "id": e.memory_id,
                    "content": e.content,
                    "category": e.category,
                    "metadata": json.loads(e.metadata_json) if e.metadata_json else {},
                    "created_at": e.created_at.timestamp(),
                    "last_accessed_at": e.last_accessed_at.timestamp(),
                    "access_count": e.access_count,
                }
                for e in entries
            ]
        finally:
            db.close()
