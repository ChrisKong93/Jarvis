from typing import Dict, List, Optional

from .short_term import ShortTermMemory
from .long_term import LongTermMemory


def get_short_term(user_id: int) -> ShortTermMemory:
    return ShortTermMemory(user_id)


def get_long_term(user_id: int) -> LongTermMemory:
    return LongTermMemory(user_id)


class MemoryManager:
    def add_short_term_turn(self, user_id: int, role: str, content: str,
                            metadata: Optional[Dict] = None) -> None:
        """保存一条对话记录到短期记忆（user / assistant）。"""
        get_short_term(user_id).add_turn(role, content, metadata)

    def add_short_term_summary(self, user_id: int, content: str) -> None:
        """保存一条摘要到短期记忆（role='summary'）。"""
        get_short_term(user_id).add_summary(content)

    def add_long_term_memory(self, user_id: int, content: str,
                             category: str = "general",
                             metadata: Optional[Dict] = None) -> str:
        return get_long_term(user_id).add_memory(content, category, metadata)

    def retrieve_relevant_memories(self, user_id: int, query: str,
                                   top_k: int = 3) -> List[Dict]:
        return get_long_term(user_id).retrieve_memories(query, top_k)

    def get_context(self, user_id: int, query: str) -> Dict:
        short = get_short_term(user_id)
        long = get_long_term(user_id)

        context_text = ""

        # 短期记忆：最近的对话记录
        recent_turns = short.get_turns(count=6)
        turn_texts = []
        for t in recent_turns:
            turn_texts.append(f"{t['role']}: {t['content']}")
        if turn_texts:
            context_text += "近期对话：\n" + "\n".join(turn_texts) + "\n"

        # 短期记忆：已有摘要
        summaries = short.get_summaries(count=3)
        if summaries:
            context_text += "\n对话摘要：\n"
            for i, s in enumerate(summaries, 1):
                context_text += f"{i}. {s['content']}\n"

        # 长期记忆：语义检索
        memories = long.retrieve_memories(query, top_k=3)
        if memories:
            context_text += "\n相关记忆：\n"
            for i, m in enumerate(memories, 1):
                context_text += f"{i}. {m['content']}\n"

        return {
            "text": context_text.strip(),
            "used": bool(turn_texts) or bool(summaries) or bool(memories),
        }

    def clear_all(self, user_id: int) -> None:
        get_short_term(user_id).clear()
        get_long_term(user_id).clear()

    def get_stats(self, user_id: int) -> Dict:
        short = get_short_term(user_id)
        long = get_long_term(user_id)
        counts = short.count_all()
        return {
            "short_term_count": counts["turns"] + counts["summaries"],
            "long_term_count": len(long.get_all_memories()),
        }

    def get_all_memories(self, user_id: int) -> Dict:
        short = get_short_term(user_id)
        long = get_long_term(user_id)
        all_short = short.get_all()
        return {
            "short_term": [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "metadata": m["metadata"],
                    "timestamp": m["timestamp"],
                }
                for m in all_short
            ],
            "long_term": long.get_all_memories(),
        }

    def needs_long_term_summary(self, user_id: int) -> bool:
        """判断短期记忆是否已达到需要总结并入长期记忆的阈值。"""
        return get_short_term(user_id).needs_summary()


memory_manager = MemoryManager()
