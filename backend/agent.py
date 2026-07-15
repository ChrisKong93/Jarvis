import json
import re
import time
from typing import Any, Dict, List, Optional

from context_manager import calculate_messages_tokens, truncate_messages

from .memory import memory_manager
from .providers import LLMError, llm_client
from .tools.base import tool_registry


class Agent:
    def __init__(self):
        self._load_tools()
        self.summary_frequency = 5
        self.max_thinking_steps = 5
        self.max_reflection_attempts = 2

    def _load_tools(self):
        from .tools import calculator, datetime_tool, file_tool, search, weather  # noqa: F401

    def _get_tools_for_llm(self) -> List[Dict[str, Any]]:
        tools = []
        for tool in tool_registry.tools.values():
            params = {}
            required = []
            for param_name, param_info in tool.parameters.items():
                params[param_name] = {
                    "type": param_info.get("type", "string"),
                    "description": param_info.get("description", ""),
                }
                if param_info.get("required") or param_info.get("description"):
                    required.append(param_name)
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": params,
                        "required": required,
                    },
                },
            })
        return tools

    def _guess_tool_for_query(self, query: str) -> Optional[str]:
        keywords = {
            "calculator": ["计算", "算", "加", "减", "乘", "除", "等于", "多少", "平方", "开方", "sin", "cos", "tan"],
            "weather": ["天气", "温度", "气温", "下雨", "晴天", "预报"],
            "datetime": ["时间", "几点", "日期", "现在", "今天", "明天"],
            "search": ["搜索", "查找", "信息", "新闻", "最新", "进展"],
            "file": ["文件", "读取", "写入", "保存"],
        }
        for tool_name, terms in keywords.items():
            for term in terms:
                if term in query:
                    return tool_name
        return None

    def _call_llm(
        self,
        messages: List[Dict],
        max_tokens: int = 2048,
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        response = llm_client.chat_completion(
            messages=messages,
            provider_id=provider,
            model=model,
            max_tokens=max_tokens,
            api_key=api_key,
            base_url=base_url,
            stop=["</s>"],
            tools=tools,
            tool_choice="auto" if tools else None,
        )
        return response

    def _build_system_prompt(self) -> str:
        return """你是一个工具调用助手。当用户的问题需要计算、查询、搜索等操作时，必须调用工具。

如果用户问数学问题（如：2+3、123*456），使用 calculator 工具。
如果用户问天气（如：北京天气），使用 weather 工具。
如果用户问时间（如：现在几点），使用 datetime 工具。
如果用户需要搜索（如：人工智能最新进展），使用 search 工具。
如果用户需要文件操作（如：读取文件），使用 file 工具。

请直接调用工具，不要说其他废话。"""

    def _parse_tool_call(self, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc.get("type") == "function":
                    func = tc.get("function", {})
                    try:
                        params = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        params = {}
                    return {
                        "name": func.get("name"),
                        "parameters": params,
                    }
        
        text = response.get("content", "")
        pattern = r"<tool_call>(.*?)</tool_call>"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                tool_call = json.loads(match.group(1))
                if isinstance(tool_call, dict) and "name" in tool_call and "parameters" in tool_call:
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

    def run(
        self,
        messages: List[Dict],
        max_tokens: int = 2048,
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()

        truncated_messages = truncate_messages(messages, max_tokens)
        last_user_message = messages[-1]["content"] if messages else ""
        memory_context = memory_manager.get_context(last_user_message)

        system_prompt = self._build_system_prompt()
        if memory_context["used"]:
            system_prompt += f"\n\n## 相关记忆\n{memory_context['text']}"

        tools_for_llm = self._get_tools_for_llm()
        full_messages = [{"role": "system", "content": system_prompt}] + truncated_messages

        tool_used = False
        tool_info_list = []
        thinking_steps = []
        reflection_count = 0
        final_response = ""

        total_completion_tokens = 0
        total_prompt_tokens = 0
        total_llm_time = 0
        used_model = model

        current_messages = full_messages.copy()
        step_count = 0

        while step_count < self.max_thinking_steps:
            llm_response = self._call_llm(
                current_messages,
                max_tokens,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                tools=tools_for_llm if step_count == 0 else None,
            )
            response_text = llm_response["content"]
            total_completion_tokens += llm_response["completion_tokens"]
            total_prompt_tokens += llm_response["prompt_tokens"]
            total_llm_time += llm_response.get("response_time", 0)
            used_model = llm_response.get("model") or used_model

            tool_call = self._parse_tool_call(llm_response)

            if not tool_call and step_count == 0:
                guessed_tool = self._guess_tool_for_query(last_user_message)
                if guessed_tool:
                    thinking_steps.append(f"模型未调用工具，自动匹配到 {guessed_tool} 工具")
                    if guessed_tool == "calculator":
                        match = re.search(r'[\d+\-*/().%\s]+', last_user_message)
                        expression = match.group(0).strip() if match else last_user_message
                        tool_call = {"name": "calculator", "parameters": {"expression": expression}}
                    elif guessed_tool == "weather":
                        cities = ["北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", "重庆", "天津", "苏州", "郑州", "长沙", "东莞"]
                        city = next((c for c in cities if c in last_user_message), "北京")
                        tool_call = {"name": "weather", "parameters": {"city": city}}
                    elif guessed_tool == "datetime":
                        tool_call = {"name": "datetime", "parameters": {"action": "now"}}
                    elif guessed_tool == "search":
                        tool_call = {"name": "search", "parameters": {"query": last_user_message}}
                    elif guessed_tool == "file":
                        tool_call = {"name": "file", "parameters": {"action": "read", "file_path": last_user_message}}

            if tool_call:
                tool_used = True

                tool_name = tool_call["name"]
                parameters = tool_call["parameters"]

                tool_result = self._execute_tool(tool_name, parameters)

                tool_info_list.append(
                    {
                        "tool_name": tool_name,
                        "parameters": parameters,
                        "result": tool_result,
                    }
                )

                is_error = "错误" in tool_result or "失败" in tool_result

                current_messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(parameters, ensure_ascii=False),
                            },
                        }],
                    }
                )
                current_messages.append({"role": "tool", "content": tool_result})

                if is_error and reflection_count < self.max_reflection_attempts:
                    reflection_count += 1
                    thinking_steps.append(f"反思第{reflection_count}次：工具调用失败，尝试调整策略")

                    reflect_messages = current_messages + [
                        {
                            "role": "assistant",
                            "content": f"反思：工具执行失败。上一步结果：{tool_result}。请分析原因并给出调整后的方案，可以调用其他工具或直接回答。",
                        }
                    ]

                    reflect_response = self._call_llm(
                        reflect_messages,
                        max_tokens=500,
                        provider=provider,
                        model=model,
                        api_key=api_key,
                        base_url=base_url,
                        tools=tools_for_llm,
                    )

                    reflect_tool_call = self._parse_tool_call(reflect_response)

                    if reflect_tool_call:
                        reflect_tool_name = reflect_tool_call["name"]
                        reflect_params = reflect_tool_call["parameters"]
                        reflect_result = self._execute_tool(reflect_tool_name, reflect_params)

                        tool_info_list.append(
                            {
                                "tool_name": reflect_tool_name,
                                "parameters": reflect_params,
                                "result": reflect_result,
                                "is_reflection": True,
                            }
                        )

                        current_messages.append(
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [{
                                    "type": "function",
                                    "function": {
                                        "name": reflect_tool_name,
                                        "arguments": json.dumps(reflect_params, ensure_ascii=False),
                                    },
                                }],
                            }
                        )
                        current_messages.append({"role": "tool", "content": reflect_result})
                    else:
                        final_response = reflect_response["content"]
                        break

                step_count += 1
            else:
                final_response = response_text
                break

        if not final_response:
            final_response_messages = current_messages + [
                {"role": "assistant", "content": "请根据以上对话，给出最终总结回答。"}
            ]
            llm_response = self._call_llm(
                final_response_messages,
                max_tokens,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
            final_response = llm_response["content"]
            total_completion_tokens += llm_response["completion_tokens"]
            total_prompt_tokens += llm_response["prompt_tokens"]
            total_llm_time += llm_response.get("response_time", 0)
            used_model = llm_response.get("model") or used_model

        self._update_memories(
            messages,
            final_response,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

        elapsed_time = time.time() - start_time
        tokens_per_second = round(total_completion_tokens / total_llm_time, 2) if total_llm_time > 0 else 0

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
            "response_time": round(elapsed_time, 2),
            "provider": provider,
            "model": used_model,
        }

    def _update_memories(
        self,
        messages: List[Dict],
        response: str,
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        if len(messages) % self.summary_frequency == 0:
            summary = self._generate_summary(
                messages,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
            if summary:
                memory_manager.add_short_term_summary(messages, summary)

        important_info = self._extract_important_info(
            messages[-1]["content"],
            response,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        if important_info:
            memory_manager.add_long_term_memory(important_info, category="knowledge")

    def _generate_summary(
        self,
        messages: List[Dict],
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> str:
        try:
            summary_messages = [
                {"role": "system", "content": "请用简短的中文总结以下对话内容，突出关键信息和结论。"},
                {
                    "role": "user",
                    "content": "\n".join([f"{m['role']}: {m['content']}" for m in messages[-10:]]),
                },
            ]
            response = self._call_llm(
                summary_messages,
                max_tokens=200,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
            return response["content"].strip()
        except Exception:
            return ""

    def _extract_important_info(
        self,
        user_query: str,
        response: str,
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> str:
        try:
            extract_messages = [
                {
                    "role": "system",
                    "content": "请提取以下对话中的重要事实、信息或结论，用简短的中文描述，适合作为长期记忆保存。如果没有重要信息，返回空字符串。",
                },
                {"role": "user", "content": f"用户：{user_query}\n助手：{response}"},
            ]
            result = self._call_llm(
                extract_messages,
                max_tokens=100,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
            content = result["content"].strip()
            return content if len(content) > 10 else ""
        except Exception:
            return ""
