import json
import re
import http.client
from typing import Dict, List, Any, Optional
from .tools.base import tool_registry
from .memory import memory_manager
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from context_manager import truncate_messages, calculate_messages_tokens


class Agent:
    def __init__(self, llama_cpp_url: str = "http://192.168.0.201:8082"):
        self.llama_cpp_url = llama_cpp_url
        self._load_tools()
        self.summary_frequency = 5
        self.max_thinking_steps = 5
        self.max_reflection_attempts = 2

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

    def _build_system_prompt(self) -> str:
        tools_desc = tool_registry.get_tool_descriptions()
        return f"""你是一个智能助手Jarvis，具备任务规划和反思能力。

## 可用工具
{tools_desc}

## 思考模式
你可以使用<think>标签进行思考，使用<tool_call>标签调用工具，或直接回答问题。

### 思考格式
<think>你的思考内容，包括分析问题、制定计划、评估结果等</think>

### 工具调用格式
<tool_call>
{{
    "name": "工具名称",
    "parameters": {{
        "参数名": "参数值"
    }}
}}
</tool_call>

### 任务规划流程
1. 分析问题：理解用户的需求
2. 制定计划：将复杂任务分解为子任务
3. 执行计划：调用工具完成每个子任务
4. 观察结果：检查工具执行结果
5. 反思调整：如果结果不理想，反思原因并调整策略
6. 总结回答：综合所有结果给出最终答案

### 反思机制
- 当工具调用失败时，尝试其他工具或方法
- 当结果不完整时，补充调用其他工具
- 当结果与预期不符时，重新分析问题

你可以直接回答简单问题，复杂问题请使用思考和工具调用。"""

    def _parse_think(self, text: str) -> Optional[str]:
        pattern = r'<think>(.*?)</think>'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

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

    def _parse_response(self, text: str) -> Dict[str, Any]:
        think = self._parse_think(text)
        tool_call = self._parse_tool_call(text)
        
        response_text = text
        if think:
            response_text = response_text.replace(f'<think>{think}</think>', '').strip()
        if tool_call:
            response_text = response_text.replace(f'<tool_call>{json.dumps(tool_call)}</tool_call>', '').strip()
        
        return {
            "think": think,
            "tool_call": tool_call,
            "response_text": response_text
        }

    def _reflect_and_adjust(self, conversation_history: List[Dict], last_result: str, error: bool = False) -> Dict[str, Any]:
        reflect_messages = [
            {
                "role": "system",
                "content": """请反思以下对话，分析问题所在并给出调整策略。

反思要点：
1. 当前结果是否满足用户需求？
2. 如果失败，原因是什么？
3. 需要尝试哪些新方法或工具？
4. 下一步应该做什么？

请使用<think>标签输出反思内容，可以使用<tool_call>标签调用工具，或直接给出最终回答。"""
            }
        ] + conversation_history + [
            {
                "role": "assistant",
                "content": f"反思：{'工具执行失败' if error else '结果分析'}。上一步结果：{last_result}"
            }
        ]
        
        response = self._call_llm(reflect_messages, max_tokens=500)
        return self._parse_response(response["content"])

    def run(self, messages: List[Dict], max_tokens: int = 2048) -> Dict[str, Any]:
        import time
        start_time = time.time()
        
        truncated_messages = truncate_messages(messages, max_tokens)
        
        last_user_message = messages[-1]["content"] if messages else ""
        memory_context = memory_manager.get_context(last_user_message)
        
        system_prompt = self._build_system_prompt()
        if memory_context["used"]:
            system_prompt += f"\n\n## 相关记忆\n{memory_context['text']}"
        
        full_messages = [
            {"role": "system", "content": system_prompt}
        ] + truncated_messages

        tool_used = False
        tool_info_list = []
        thinking_steps = []
        reflection_count = 0
        final_response = ""
        
        total_completion_tokens = 0
        total_prompt_tokens = 0
        
        current_messages = full_messages.copy()
        step_count = 0
        
        while step_count < self.max_thinking_steps:
            llm_response = self._call_llm(current_messages, max_tokens)
            response_text = llm_response["content"]
            total_completion_tokens += llm_response["completion_tokens"]
            total_prompt_tokens += llm_response["prompt_tokens"]
            
            parsed = self._parse_response(response_text)
            
            if parsed["think"]:
                thinking_steps.append(parsed["think"])
            
            if parsed["tool_call"]:
                tool_used = True
                
                tool_name = parsed["tool_call"]['name']
                parameters = parsed["tool_call"]['parameters']
                
                tool_result = self._execute_tool(tool_name, parameters)
                
                tool_info_list.append({
                    "tool_name": tool_name,
                    "parameters": parameters,
                    "result": tool_result,
                    "thinking": parsed["think"]
                })
                
                is_error = "错误" in tool_result or "失败" in tool_result
                
                current_messages.append({
                    "role": "assistant",
                    "content": f"<think>{parsed['think']}</think>\n使用{tool_name}工具，参数：{json.dumps(parameters)}"
                })
                current_messages.append({
                    "role": "tool",
                    "content": tool_result
                })
                
                if is_error and reflection_count < self.max_reflection_attempts:
                    reflection_count += 1
                    thinking_steps.append(f"反思第{reflection_count}次：工具调用失败，尝试调整策略")
                    
                    reflect_parsed = self._reflect_and_adjust(current_messages, tool_result, error=True)
                    
                    if reflect_parsed["think"]:
                        thinking_steps.append(reflect_parsed["think"])
                    
                    if reflect_parsed["tool_call"]:
                        reflect_tool_name = reflect_parsed["tool_call"]['name']
                        reflect_params = reflect_parsed["tool_call"]['parameters']
                        reflect_result = self._execute_tool(reflect_tool_name, reflect_params)
                        
                        tool_info_list.append({
                            "tool_name": reflect_tool_name,
                            "parameters": reflect_params,
                            "result": reflect_result,
                            "thinking": reflect_parsed["think"],
                            "is_reflection": True
                        })
                        
                        current_messages.append({
                            "role": "assistant",
                            "content": f"<think>{reflect_parsed['think']}</think>\n反思后使用{reflect_tool_name}工具"
                        })
                        current_messages.append({
                            "role": "tool",
                            "content": reflect_result
                        })
                    else:
                        final_response = reflect_parsed["response_text"]
                        break
                
                step_count += 1
            else:
                final_response = parsed["response_text"]
                break
        
        if not final_response:
            final_response_messages = current_messages + [
                {"role": "assistant", "content": "请根据以上对话，给出最终总结回答。"}
            ]
            llm_response = self._call_llm(final_response_messages, max_tokens)
            final_response = llm_response["content"]
            total_completion_tokens += llm_response["completion_tokens"]
            total_prompt_tokens += llm_response["prompt_tokens"]

        self._update_memories(messages, final_response)

        elapsed_time = time.time() - start_time
        tokens_per_second = round(total_completion_tokens / elapsed_time, 2) if elapsed_time > 0 else 0

        return {
            "content": final_response,
            "tool_used": tool_used,
            "tool_info": tool_info_list if tool_info_list else None,
            "thinking": thinking_steps,
            "reflection_count": reflection_count,
            "memory_saved": False,
            "memory_context": memory_context,
            "context_tokens": calculate_messages_tokens(truncated_messages),
            "original_messages_count": len(messages),
            "truncated_messages_count": len(truncated_messages),
            "completion_tokens": total_completion_tokens,
            "prompt_tokens": total_prompt_tokens,
            "total_tokens": total_completion_tokens + total_prompt_tokens,
            "tokens_per_second": tokens_per_second,
            "response_time": round(elapsed_time, 2)
        }

    def _update_memories(self, messages: List[Dict], response: str) -> None:
        if len(messages) % self.summary_frequency == 0:
            summary = self._generate_summary(messages)
            if summary:
                memory_manager.add_short_term_summary(messages, summary)
        
        important_info = self._extract_important_info(messages[-1]["content"], response)
        if important_info:
            memory_manager.add_long_term_memory(important_info, category="knowledge")

    def _generate_summary(self, messages: List[Dict]) -> str:
        try:
            summary_messages = [
                {"role": "system", "content": "请用简短的中文总结以下对话内容，突出关键信息和结论。"},
                {"role": "user", "content": "\n".join([f"{m['role']}: {m['content']}" for m in messages[-10:]])}
            ]
            response = self._call_llm(summary_messages, max_tokens=200)
            return response["content"].strip()
        except Exception:
            return ""

    def _extract_important_info(self, user_query: str, response: str) -> str:
        try:
            extract_messages = [
                {"role": "system", "content": "请提取以下对话中的重要事实、信息或结论，用简短的中文描述，适合作为长期记忆保存。如果没有重要信息，返回空字符串。"},
                {"role": "user", "content": f"用户：{user_query}\n助手：{response}"}
            ]
            response = self._call_llm(extract_messages, max_tokens=100)
            result = response["content"].strip()
            return result if len(result) > 10 else ""
        except Exception:
            return ""