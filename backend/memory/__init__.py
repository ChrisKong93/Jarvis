from .short_term import ShortTermMemory
from .long_term import LongTermMemory
from typing import Dict, List, Optional

class MemoryManager:
    def __init__(self):
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory()

    def add_short_term_summary(self, messages: List[Dict], summary: str) -> None:
        self.short_term.add_summary(messages, summary)

    def add_long_term_memory(self, content: str, category: str = "general", metadata: Optional[Dict] = None) -> str:
        return self.long_term.add_memory(content, category, metadata)

    def retrieve_relevant_memories(self, query: str, top_k: int = 3) -> List[Dict]:
        return self.long_term.retrieve_memories(query, top_k)

    def get_context(self, query: str) -> Dict:
        short_summaries = []
        long_memories = []
        context_text = ""
        
        summaries = self.short_term.get_recent_summaries(count=3)
        if summaries:
            short_summaries = summaries
            context_text += "近期对话总结：\n"
            for i, summary in enumerate(summaries, 1):
                context_text += f"{i}. {summary['summary']}\n"
        
        memories = self.retrieve_relevant_memories(query, top_k=3)
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

    def clear_all(self) -> None:
        self.short_term.clear()
        self.long_term.clear()

    def get_stats(self) -> Dict:
        return {
            "short_term_summaries": len(self.short_term.get_all_summaries()),
            "long_term_memories": len(self.long_term.get_all_memories())
        }

    def get_all_memories(self) -> Dict:
        return {
            "short_term": self.short_term.get_all_summaries(),
            "long_term": self.long_term.get_all_memories()
        }

memory_manager = MemoryManager()