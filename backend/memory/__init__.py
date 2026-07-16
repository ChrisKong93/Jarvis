from typing import Dict, List, Optional

from .short_term import ShortTermMemory
from .long_term import LongTermMemory


def get_short_term(user_id: int) -> ShortTermMemory:
    return ShortTermMemory(user_id)


def get_long_term(user_id: int) -> LongTermMemory:
    return LongTermMemory(user_id)


class MemoryManager:
    def add_short_term_summary(self, user_id: int, messages: List[Dict], summary: str) -> None:
        get_short_term(user_id).add_summary(messages, summary)

    def add_long_term_memory(self, user_id: int, content: str, category: str = "general", metadata: Optional[Dict] = None) -> str:
        return get_long_term(user_id).add_memory(content, category, metadata)

    def retrieve_relevant_memories(self, user_id: int, query: str, top_k: int = 3) -> List[Dict]:
        return get_long_term(user_id).retrieve_memories(query, top_k)

    def get_context(self, user_id: int, query: str) -> Dict:
        short = get_short_term(user_id)
        long = get_long_term(user_id)

        short_summaries = []
        long_memories = []
        context_text = ""

        summaries = short.get_recent_summaries(count=3)
        if summaries:
            short_summaries = summaries
            context_text += "近期对话总结：\n"
            for i, summary in enumerate(summaries, 1):
                context_text += f"{i}. {summary['summary']}\n"

        memories = long.retrieve_memories(query, top_k=3)
        if memories:
            long_memories = memories
            context_text += "\n相关记忆：\n"
            for i, memory in enumerate(memories, 1):
                context_text += f"{i}. {memory['content']}\n"

        return {
            "text": context_text.strip(),
            "short_term": short_summaries,
            "long_term": long_memories,
            "used": len(short_summaries) > 0 or len(long_memories) > 0
        }

    def clear_all(self, user_id: int) -> None:
        get_short_term(user_id).clear()
        get_long_term(user_id).clear()

    def get_stats(self, user_id: int) -> Dict:
        short = get_short_term(user_id)
        long = get_long_term(user_id)
        return {
            "short_term_summaries": len(short.get_all_summaries()),
            "long_term_memories": len(long.get_all_memories())
        }

    def get_all_memories(self, user_id: int) -> Dict:
        short = get_short_term(user_id)
        long = get_long_term(user_id)
        return {
            "short_term": short.get_all_summaries(),
            "long_term": long.get_all_memories()
        }


memory_manager = MemoryManager()
