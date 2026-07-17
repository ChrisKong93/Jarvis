import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VECTORS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "vectors"
)
os.makedirs(VECTORS_DIR, exist_ok=True)


class VectorStore:
    def __init__(self, persist_dir: str = VECTORS_DIR):
        self.persist_dir = persist_dir
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
        except ImportError:
            self._client = None
            logger.warning("chromadb 未安装，向量检索引擎不可用")
        return self._client

    def _collection_name(self, user_id: int) -> str:
        return f"user_{user_id}_memories"

    def _get_or_create_collection(self, user_id: int):
        client = self._get_client()
        if client is None:
            return None
        name = self._collection_name(user_id)
        try:
            return client.get_collection(name)
        except Exception:
            return client.create_collection(
                name,
                metadata={"hnsw:space": "cosine"},  # 余弦距离，适合语义检索
            )

    def is_available(self) -> bool:
        return self._get_client() is not None

    def add_memory(
        self,
        user_id: int,
        memory_id: str,
        content: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        collection = self._get_or_create_collection(user_id)
        if collection is None:
            return
        collection.add(
            ids=[memory_id],
            embeddings=[embedding],
            metadatas=[metadata or {}],
            documents=[content],
        )

    def search(
        self,
        user_id: int,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        collection = self._get_or_create_collection(user_id)
        if collection is None:
            return []

        actual_k = min(top_k, 20)
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=actual_k,
                include=["documents", "distances", "metadatas"],
            )
        except Exception as exc:
            logger.warning(f"ChromaDB 查询失败: {exc}")
            return []

        formatted = []
        if results and results.get("ids"):
            for i in range(len(results["ids"][0])):
                memory_id = results["ids"][0][i]
                content = results["documents"][0][i] if results.get("documents") else ""
                distance = results["distances"][0][i] if results.get("distances") else 0.0
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}

                # 余弦距离 [0, 2] → 相似度 [1, 0]
                similarity = round(1.0 - distance / 2.0, 3)
                if similarity < 0.05:
                    continue

                formatted.append({
                    "id": memory_id,
                    "content": content,
                    "similarity": similarity,
                    "category": meta.get("category", "general"),
                    "metadata": meta,
                })
        return formatted

    def delete_memory(self, user_id: int, memory_id: str):
        collection = self._get_or_create_collection(user_id)
        if collection is None:
            return
        try:
            collection.delete(ids=[memory_id])
        except Exception:
            pass

    def clear_all(self, user_id: int):
        client = self._get_client()
        if client is None:
            return
        name = self._collection_name(user_id)
        try:
            client.delete_collection(name)
        except Exception:
            pass


vector_store = VectorStore()
