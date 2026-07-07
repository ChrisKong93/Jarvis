from typing import Dict, List, Optional
import json
import time
import hashlib

class MemoryEntry:
    def __init__(self, content: str, category: str = "general", metadata: Optional[Dict] = None):
        self.id = hashlib.md5(f"{content}{time.time()}".encode()).hexdigest()[:16]
        self.content = content
        self.category = category
        self.metadata = metadata or {}
        self.created_at = time.time()
        self.last_accessed_at = time.time()
        self.access_count = 1

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count
        }

class LongTermMemory:
    def __init__(self, storage_path: Optional[str] = None):
        self.memories: List[MemoryEntry] = []
        self.storage_path = storage_path or "memories.json"
        self._load_memories()

    def add_memory(self, content: str, category: str = "general", metadata: Optional[Dict] = None) -> str:
        entry = MemoryEntry(content, category, metadata)
        self.memories.append(entry)
        self._save_memories()
        return entry.id

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
        results = []
        
        for memory in self.memories:
            similarity = self._calculate_similarity(query, memory.content)
            if similarity >= min_similarity:
                memory.last_accessed_at = time.time()
                memory.access_count += 1
                results.append({
                    "similarity": round(similarity, 3),
                    **memory.to_dict()
                })
        
        results.sort(key=lambda x: x["similarity"], reverse=True)
        self._save_memories()
        return results[:top_k]

    def get_memories_by_category(self, category: str) -> List[Dict]:
        return [m.to_dict() for m in self.memories if m.category == category]

    def delete_memory(self, memory_id: str) -> bool:
        original_length = len(self.memories)
        self.memories = [m for m in self.memories if m.id != memory_id]
        self._save_memories()
        return len(self.memories) < original_length

    def clear(self) -> None:
        self.memories = []
        self._save_memories()

    def get_all_memories(self) -> List[Dict]:
        return [m.to_dict() for m in self.memories]

    def _save_memories(self) -> None:
        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump([m.to_dict() for m in self.memories], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_memories(self) -> None:
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    entry = MemoryEntry(item["content"], item["category"], item.get("metadata"))
                    entry.id = item["id"]
                    entry.created_at = item["created_at"]
                    entry.last_accessed_at = item.get("last_accessed_at", item["created_at"])
                    entry.access_count = item.get("access_count", 1)
                    self.memories.append(entry)
        except Exception:
            pass