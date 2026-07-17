import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from backend.database import LongTermMemory as LongTermMemoryModel, get_db_session

from .embeddings import embedding_generator
from .vector_store import vector_store

logger = logging.getLogger(__name__)


class LongTermMemory:
    def __init__(self, user_id: int):
        self.user_id = user_id

    def _generate_id(self, content: str) -> str:
        return hashlib.md5(f"{content}{time.time()}".encode()).hexdigest()[:16]

    def add_memory(
        self,
        content: str,
        category: str = "general",
        metadata: Optional[Dict] = None,
        skip_dedup: bool = False,
    ) -> str:
        """添加长期记忆，支持写入前去重。

        Args:
            skip_dedup: True 则跳过相似度去重检查，强制写入。
        """
        # 去重：检查是否存在相似内容
        if not skip_dedup:
            similar = self.retrieve_memories(content, top_k=1, min_similarity=0.85)
            if similar:
                logger.info(
                    "跳过重复记忆: %s... (相似于已有记忆, similarity=%s)",
                    content[:50], similar[0].get("similarity"),
                )
                return similar[0]["id"]

        memory_id = self._generate_id(content)
        metadata = metadata or {}

        # 1) 生成向量
        embedding = embedding_generator.embed(content)

        # 2) 存入 ChromaDB
        vector_store.add_memory(
            self.user_id,
            memory_id,
            content,
            embedding,
            {"category": category, **metadata},
        )

        # 3) 同步存入 SQLite（作为数据主库，用于列表展示和删除）
        db = get_db_session()
        try:
            entry = LongTermMemoryModel(
                user_id=self.user_id,
                memory_id=memory_id,
                content=content,
                category=category,
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            )
            db.add(entry)
            db.commit()
        except Exception as exc:
            logger.warning(f"SQLite 写入记忆失败: {exc}")
            db.rollback()
        finally:
            db.close()

        return memory_id

    def retrieve_memories(
        self, query: str, top_k: int = 5, min_similarity: float = 0.05
    ) -> List[Dict]:
        if vector_store.is_available():
            return self._vector_retrieve(query, top_k, min_similarity)
        return self._keyword_retrieve(query, top_k, 0.1)

    def _vector_retrieve(
        self, query: str, top_k: int = 5, min_similarity: float = 0.1
    ) -> List[Dict]:
        query_embedding = embedding_generator.embed(query)
        results = vector_store.search(self.user_id, query_embedding, top_k)

        # 回填 SQLite 中的额外字段（时间、访问次数等）
        if results:
            db = get_db_session()
            try:
                memory_ids = [r["id"] for r in results]
                rows = (
                    db.query(LongTermMemoryModel)
                    .filter(
                        LongTermMemoryModel.user_id == self.user_id,
                        LongTermMemoryModel.memory_id.in_(memory_ids),
                    )
                    .all()
                )
                row_map = {r.memory_id: r for r in rows}

                now = datetime.utcnow()
                now_ts = now.timestamp()
                enriched = []
                for r in results:
                    row = row_map.get(r["id"])
                    if row:
                        row.last_accessed_at = now
                        row.access_count += 1
                        r["created_at"] = row.created_at.timestamp()
                        r["last_accessed_at"] = row.last_accessed_at.timestamp()
                        r["access_count"] = row.access_count
                    else:
                        r["created_at"] = None
                        r["last_accessed_at"] = None
                        r["access_count"] = 0
                    if r["similarity"] >= min_similarity:
                        # 时间衰减：30 天半衰期
                        age_days = (now_ts - (r["created_at"] or now_ts)) / 86400
                        decay = 0.5 ** (age_days / 30.0)
                        r["decayed_score"] = round(r["similarity"] * decay, 3)
                        enriched.append(r)
                # 按衰减后分数排序
                enriched.sort(key=lambda x: x["decayed_score"], reverse=True)
                db.commit()
                return enriched
            except Exception:
                db.rollback()
                return results
            finally:
                db.close()

        return []

    def _keyword_retrieve(
        self, query: str, top_k: int = 5, min_similarity: float = 0.1
    ) -> List[Dict]:
        """降级方案：关键词重叠检索 + 时间衰减"""
        db = get_db_session()
        try:
            entries = (
                db.query(LongTermMemoryModel)
                .filter(LongTermMemoryModel.user_id == self.user_id)
                .all()
            )

            results = []
            now = datetime.utcnow()
            now_ts = now.timestamp()

            for e in entries:
                similarity = self._calculate_similarity(query, e.content)
                if similarity >= min_similarity:
                    e.last_accessed_at = now
                    e.access_count += 1
                    created_ts = e.created_at.timestamp()
                    # 时间衰减：30 天半衰期
                    age_days = (now_ts - created_ts) / 86400
                    decay = 0.5 ** (age_days / 30.0)
                    decayed_score = round(similarity * decay, 3)
                    results.append({
                        "similarity": round(similarity, 3),
                        "decayed_score": decayed_score,
                        "id": e.memory_id,
                        "content": e.content,
                        "category": e.category,
                        "metadata": json.loads(e.metadata_json) if e.metadata_json else {},
                        "created_at": created_ts,
                        "last_accessed_at": e.last_accessed_at.timestamp(),
                        "access_count": e.access_count,
                    })

            db.commit()
            results.sort(key=lambda x: x["decayed_score"], reverse=True)
            return results[:top_k]
        finally:
            db.close()

    @staticmethod
    def _calculate_similarity(text1: str, text2: str) -> float:
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union

    def get_memories_by_category(self, category: str) -> List[Dict]:
        db = get_db_session()
        try:
            entries = (
                db.query(LongTermMemoryModel)
                .filter(
                    LongTermMemoryModel.user_id == self.user_id,
                    LongTermMemoryModel.category == category,
                )
                .all()
            )
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
        vector_store.delete_memory(self.user_id, memory_id)
        db = get_db_session()
        try:
            entry = (
                db.query(LongTermMemoryModel)
                .filter(
                    LongTermMemoryModel.user_id == self.user_id,
                    LongTermMemoryModel.memory_id == memory_id,
                )
                .first()
            )
            if not entry:
                return False
            db.delete(entry)
            db.commit()
            return True
        finally:
            db.close()

    def clear(self) -> None:
        vector_store.clear_all(self.user_id)
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
            entries = (
                db.query(LongTermMemoryModel)
                .filter(LongTermMemoryModel.user_id == self.user_id)
                .order_by(LongTermMemoryModel.created_at.desc())
                .all()
            )
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
