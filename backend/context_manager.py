import re
from typing import List, Dict, Optional

def estimate_token_count(text: str) -> int:
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    other_chars = len(text) - chinese_chars - english_words

    return chinese_chars + english_words // 2 + other_chars // 2

def calculate_messages_tokens(messages: List[Dict]) -> int:
    total_tokens = 0
    for msg in messages:
        if 'content' in msg:
            total_tokens += estimate_token_count(msg['content'])
        if 'role' in msg:
            total_tokens += estimate_token_count(msg['role'])
        total_tokens += 4
    return total_tokens

def truncate_messages(
    messages: List[Dict],
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None
) -> List[Dict]:
    system_tokens = estimate_token_count(system_prompt) if system_prompt else 0
    available_tokens = max_tokens - system_tokens - 512

    if calculate_messages_tokens(messages) <= available_tokens:
        return messages

    truncated = []
    total_tokens = 0

    for msg in reversed(messages):
        msg_tokens = calculate_messages_tokens([msg])

        if total_tokens + msg_tokens <= available_tokens:
            truncated.insert(0, msg)
            total_tokens += msg_tokens
        else:
            if not truncated:
                content = msg.get('content', '')
                content_tokens = estimate_token_count(content)
                if content_tokens > available_tokens:
                    ratio = available_tokens / content_tokens
                    truncated_content = content[:int(len(content) * ratio)]
                    truncated.insert(0, {
                        'role': msg['role'],
                        'content': truncated_content + '...'
                    })
            break

    return truncated
