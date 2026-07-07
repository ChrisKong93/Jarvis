from typing import Dict, List, Optional
import json
import time

class ShortTermMemory:
    def __init__(self):
        self.summaries: List[Dict] = []
        self.max_summaries = 10

    def add_summary(self, messages: List[Dict], summary: str) -> None:
        entry = {
            "id": str(time.time()),
            "timestamp": time.time(),
            "summary": summary,
            "message_count": len(messages),
            "key_points": self._extract_key_points(summary)
        }
        self.summaries.insert(0, entry)
        
        if len(self.summaries) > self.max_summaries:
            self.summaries.pop()

    def _extract_key_points(self, summary: str) -> List[str]:
        lines = summary.split('\n')
        key_points = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('-'):
                key_points.append(line[:50])
        return key_points[:5]

    def get_recent_summaries(self, count: int = 3) -> List[Dict]:
        return self.summaries[:count]

    def get_all_summaries(self) -> List[Dict]:
        return self.summaries

    def clear(self) -> None:
        self.summaries = []

    def get_summary_text(self, count: int = 3) -> str:
        summaries = self.get_recent_summaries(count)
        if not summaries:
            return ""
        
        result = "近期对话总结：\n"
        for i, summary in enumerate(summaries, 1):
            result += f"{i}. {summary['summary']}\n"
        return result.strip()