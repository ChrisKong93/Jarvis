import json
import re
import http.client
from typing import Dict, List, Any, Optional
from .tools.base import tool_registry
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from context_manager import truncate_messages, calculate_messages_tokens


class Agent:
    def __init__(self, llama_cpp_url: str = "http://192.168.0.201:8082"):
        self.llama_cpp_url = llama_cpp_url
        self._load_tools()

    def _load_tools(self):
        from .tools import calculator, search, weather, file_tool, datetime_tool

    def _get_host_port(self):
        import urllib.parse
        parsed = urllib.parse.urlparse(self.llama_cpp_url)
        return parsed.hostname, parsed.port or 80

    def _call_llm(self, messages: List[Dict], max_tokens: int = 2048) -> Dict[str, Any]:
        host, port = self._get_host_port()
        conn = http.client.HTTPConnection(host, port, timeout=300)
        
        try:
            payload = json.dumps({
                "messages": messages,
                "stream": False,
                "max_tokens": max_tokens,
                "temperature": 0.7,
                "top_p": 0.9,
                "stop": ["</s>"]
            })
            conn.request('POST', '/chat/completions', payload, {'Content-Type': 'application/json'})
            response = conn.getresponse()
            content = response.read().decode('utf-8')
            result = json.loads(content)
            
            response_data = {
                "content": "",
                "completion_tokens": 0,
                "prompt_tokens": 0,
                "total_tokens": 0
            }
            
            if 'choices' in result and result['choices']:
                response_data["content"] = result['choices'][0]['message']['content']
            
            if 'usage' in result:
                response_data["completion_tokens"] = result['usage'].get('completion_tokens', 0)
                response_data["prompt_tokens"] = result['usage'].get('prompt_tokens', 0)
                response_data["total_tokens"] = result['usage'].get('total_tokens', 0)
            
            return response_data
        finally:
            conn.close()

    def _build_tool_prompt(self) -> str:
        tools_desc = tool_registry.get_tool_descriptions()
        return f"""你是一个智能助手，可以使用工具来回答问题。可用工具：

{tools_desc}

当你需要使用工具时，请按照以下格式输出：
<tool_call>
{{
    "name": "工具名称",
    "parameters": {{
        "参数名": "参数值"
    }}
}}
</tool_call>

如果你不需要使用工具，可以直接回答问题。"""

    def _parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        pattern = r'<tool_call>(.*?)</tool_call>'
        match = re.search(pattern, text, re.DOTALL)
        
        if match:
            try:
                tool_call = json.loads(match.group(1))
                if isinstance(tool_call, dict) and 'name' in tool_call and 'parameters' in tool_call:
                    return tool_call
            except json.JSONDecodeError:
                pass
        
        return None

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        tool = tool_registry.get_tool(tool_name)
        if tool:
            try:
                return tool.execute(**parameters)
            except Exception as e:
                return f"工具执行错误：{str(e)}"
        return f"未找到工具：{tool_name}"

    def run(self, messages: List[Dict], max_tokens: int = 2048) -> Dict[str, Any]:
        import time
        start_time = time.time()
        
        truncated_messages = truncate_messages(messages, max_tokens)
        
        system_prompt = self._build_tool_prompt()
        full_messages = [
            {"role": "system", "content": system_prompt}
        ] + truncated_messages

        tool_used = False
        tool_info = None
        thinking = None
        
        total_completion_tokens = 0
        total_prompt_tokens = 0

        llm_response = self._call_llm(full_messages, max_tokens)
        response_text = llm_response["content"]
        total_completion_tokens += llm_response["completion_tokens"]
        total_prompt_tokens += llm_response["prompt_tokens"]
        
        tool_call = self._parse_tool_call(response_text)
        
        if tool_call:
            tool_used = True
            thinking = response_text.replace(f'<tool_call>{json.dumps(tool_call)}</tool_call>', '').strip()
            
            tool_name = tool_call['name']
            parameters = tool_call['parameters']
            
            tool_result = self._execute_tool(tool_name, parameters)
            
            tool_info = {
                "tool_name": tool_name,
                "parameters": parameters,
                "result": tool_result
            }

            follow_up_messages = full_messages + [
                {"role": "assistant", "content": f"我将使用 {tool_name} 工具来回答这个问题。"},
                {"role": "tool", "content": tool_result}
            ]
            
            llm_response = self._call_llm(follow_up_messages, max_tokens)
            response_text = llm_response["content"]
            total_completion_tokens += llm_response["completion_tokens"]
            total_prompt_tokens += llm_response["prompt_tokens"]

        elapsed_time = time.time() - start_time
        tokens_per_second = round(total_completion_tokens / elapsed_time, 2) if elapsed_time > 0 else 0

        return {
            "content": response_text,
            "tool_used": tool_used,
            "tool_info": tool_info,
            "thinking": thinking,
            "context_tokens": calculate_messages_tokens(truncated_messages),
            "original_messages_count": len(messages),
            "truncated_messages_count": len(truncated_messages),
            "completion_tokens": total_completion_tokens,
            "prompt_tokens": total_prompt_tokens,
            "total_tokens": total_completion_tokens + total_prompt_tokens,
            "tokens_per_second": tokens_per_second,
            "response_time": round(elapsed_time, 2)
        }