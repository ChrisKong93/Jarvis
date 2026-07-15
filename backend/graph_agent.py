import json
import re
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END

from context_manager import calculate_messages_tokens, truncate_messages

from .memory import memory_manager
from .providers import LLMError, llm_client
from .tools.base import tool_registry


class AgentState(TypedDict):
    messages: List[Dict]
    tool_results: List[Dict]
    thinking_steps: List[str]
    memory_context: Dict
    final_response: str
    tool_used: bool
    reflection_count: int
    step_count: int
    llm_stats: Dict
    provider_config: Dict
    last_user_message: str
    tools_for_llm: List[Dict]
    max_thinking_steps: int
    max_reflection_attempts: int
    llm_response: Dict
    tool_call: Optional[Dict]
    tool_result: str
    is_error: bool


class GraphAgent:
    def __init__(self):
        self._load_tools()
        self.summary_frequency = 5
        self.max_thinking_steps = 5
        self.max_reflection_attempts = 2
        self.graph = self._build_graph()

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
        provider_config: Dict,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        return llm_client.chat_completion(
            messages=messages,
            provider_id=provider_config["provider"],
            model=provider_config["model"],
            max_tokens=provider_config["max_tokens"],
            api_key=provider_config["api_key"],
            base_url=provider_config["base_url"],
            stop=["</s>"],
            tools=tools,
            tool_choice="auto" if tools else None,
        )

    def _build_system_prompt(self, memory_context: Dict) -> str:
        prompt = """你是一个工具调用助手。当用户的问题需要计算、查询、搜索等操作时，必须调用工具。

如果用户问数学问题（如：2+3、123*456），使用 calculator 工具。
如果用户问天气（如：北京天气），使用 weather 工具。
如果用户问时间（如：现在几点），使用 datetime 工具。
如果用户需要搜索（如：人工智能最新进展），使用 search 工具。
如果用户需要文件操作（如：读取文件），使用 file 工具。

请直接调用工具，不要说其他废话。"""

        if memory_context.get("used"):
            prompt += f"\n\n## 相关记忆\n{memory_context.get('text', '')}"

        return prompt

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

    def _node_prepare_state(self, state: AgentState) -> AgentState:
        messages = state["provider_config"].get("original_messages", [])
        last_user_message = messages[-1]["content"] if messages else ""
        truncated_messages = truncate_messages(messages, state["provider_config"]["max_tokens"])
        memory_context = memory_manager.get_context(last_user_message)
        tools_for_llm = self._get_tools_for_llm()

        system_prompt = self._build_system_prompt(memory_context)
        full_messages = [{"role": "system", "content": system_prompt}] + truncated_messages

        return {
            **state,
            "messages": full_messages,
            "tool_results": [],
            "thinking_steps": [],
            "memory_context": memory_context,
            "final_response": "",
            "tool_used": False,
            "reflection_count": 0,
            "step_count": 0,
            "llm_stats": {"completion_tokens": 0, "prompt_tokens": 0},
            "last_user_message": last_user_message,
            "tools_for_llm": tools_for_llm,
            "max_thinking_steps": self.max_thinking_steps,
            "max_reflection_attempts": self.max_reflection_attempts,
        }

    def _node_call_llm(self, state: AgentState) -> AgentState:
        tools_for_llm = state["tools_for_llm"] if state["step_count"] == 0 else None

        llm_response = self._call_llm(
            state["messages"],
            state["provider_config"],
            tools=tools_for_llm,
        )

        tool_call = self._parse_tool_call(llm_response)
        thinking_steps = state["thinking_steps"].copy()

        if not tool_call and state["step_count"] == 0:
            guessed_tool = self._guess_tool_for_query(state["last_user_message"])
            if guessed_tool:
                thinking_steps.append(f"模型未调用工具，自动匹配到 {guessed_tool} 工具")
                if guessed_tool == "calculator":
                    match = re.search(r'[\d+\-*/().%\s]+', state["last_user_message"])
                    expression = match.group(0).strip() if match else state["last_user_message"]
                    tool_call = {"name": "calculator", "parameters": {"expression": expression}}
                elif guessed_tool == "weather":
                    cities = ["北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", "重庆", "天津", "苏州", "郑州", "长沙", "东莞"]
                    city = next((c for c in cities if c in state["last_user_message"]), "北京")
                    tool_call = {"name": "weather", "parameters": {"city": city}}
                elif guessed_tool == "datetime":
                    tool_call = {"name": "datetime", "parameters": {"action": "now"}}
                elif guessed_tool == "search":
                    tool_call = {"name": "search", "parameters": {"query": state["last_user_message"]}}
                elif guessed_tool == "file":
                    tool_call = {"name": "file", "parameters": {"action": "read", "file_path": state["last_user_message"]}}

        return {
            **state,
            "messages": state["messages"],
            "llm_response": llm_response,
            "tool_call": tool_call,
            "thinking_steps": thinking_steps,
            "llm_stats": {
                "completion_tokens": state["llm_stats"]["completion_tokens"] + llm_response["completion_tokens"],
                "prompt_tokens": state["llm_stats"]["prompt_tokens"] + llm_response["prompt_tokens"],
                "llm_time": state["llm_stats"].get("llm_time", 0) + llm_response.get("response_time", 0),
                "model": llm_response.get("model") or state["provider_config"].get("model"),
            },
        }

    def _node_parse_and_execute_tool(self, state: AgentState) -> AgentState:
        tool_call = state.get("tool_call")
        if not tool_call:
            return {
                **state,
                "final_response": state.get("llm_response", {}).get("content", ""),
            }

        tool_name = tool_call["name"]
        parameters = tool_call["parameters"]
        tool_result = self._execute_tool(tool_name, parameters)

        tool_info = {
            "tool_name": tool_name,
            "parameters": parameters,
            "result": tool_result,
        }

        new_tool_results = state["tool_results"].copy()
        new_tool_results.append(tool_info)

        new_messages = state["messages"].copy()
        new_messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(parameters, ensure_ascii=False),
                },
            }],
        })
        new_messages.append({"role": "tool", "content": tool_result})

        return {
            **state,
            "messages": new_messages,
            "tool_results": new_tool_results,
            "tool_used": True,
            "tool_result": tool_result,
            "is_error": "错误" in tool_result or "失败" in tool_result,
            "step_count": state["step_count"] + 1,
        }

    def _node_reflection(self, state: AgentState) -> AgentState:
        new_reflection_count = state["reflection_count"] + 1
        new_thinking_steps = state["thinking_steps"].copy()
        new_thinking_steps.append(f"反思第{new_reflection_count}次：工具调用失败，尝试调整策略")

        reflect_messages = state["messages"].copy()
        reflect_messages.append({
            "role": "assistant",
            "content": f"反思：工具执行失败。上一步结果：{state['tool_result']}。请分析原因并给出调整后的方案，可以调用其他工具或直接回答。",
        })

        reflect_response = self._call_llm(
            reflect_messages,
            state["provider_config"],
            tools=state["tools_for_llm"],
        )

        reflect_tool_call = self._parse_tool_call(reflect_response)

        return {
            **state,
            "messages": reflect_messages,
            "llm_response": reflect_response,
            "tool_call": reflect_tool_call,
            "thinking_steps": new_thinking_steps,
            "reflection_count": new_reflection_count,
            "llm_stats": {
                "completion_tokens": state["llm_stats"]["completion_tokens"] + reflect_response["completion_tokens"],
                "prompt_tokens": state["llm_stats"]["prompt_tokens"] + reflect_response["prompt_tokens"],
                "llm_time": state["llm_stats"].get("llm_time", 0) + reflect_response.get("response_time", 0),
                "model": reflect_response.get("model") or state["llm_stats"].get("model"),
            },
        }

    def _node_final_response(self, state: AgentState) -> AgentState:
        if state["final_response"]:
            return state

        llm_response = state.get("llm_response")
        if llm_response and llm_response.get("content"):
            return {
                **state,
                "final_response": llm_response["content"],
            }

        final_messages = state["messages"] + [{
            "role": "user",
            "content": "请根据以上对话内容和工具执行结果，用自然友好的语言给出最终回答。"
        }]
        final_response = self._call_llm(
            final_messages,
            state["provider_config"],
        )

        return {
            **state,
            "final_response": final_response["content"],
            "llm_stats": {
                "completion_tokens": state["llm_stats"]["completion_tokens"] + final_response["completion_tokens"],
                "prompt_tokens": state["llm_stats"]["prompt_tokens"] + final_response["prompt_tokens"],
                "llm_time": state["llm_stats"].get("llm_time", 0) + final_response.get("response_time", 0),
                "model": final_response.get("model") or state["llm_stats"].get("model"),
            },
        }

    def _node_update_memory(self, state: AgentState) -> AgentState:
        messages = state["provider_config"].get("original_messages", [])
        response = state["final_response"]

        user_messages = [m for m in messages if m.get("role") == "user"]
        
        if len(user_messages) % self.summary_frequency == 0:
            summary = self._generate_summary(messages, state["provider_config"])
            if summary:
                memory_manager.add_short_term_summary(messages, summary)

        important_info = self._extract_important_info(
            state["last_user_message"],
            response,
            state["provider_config"],
        )
        if important_info:
            memory_manager.add_long_term_memory(important_info, category="knowledge")

        return state

    def _generate_summary(self, messages: List[Dict], provider_config: Dict) -> str:
        try:
            summary_messages = [
                {"role": "system", "content": "请用简短的中文总结以下对话内容，突出关键信息和结论。"},
                {
                    "role": "user",
                    "content": "\n".join([f"{m['role']}: {m['content']}" for m in messages[-10:]]),
                },
            ]
            response = self._call_llm(summary_messages, provider_config)
            return response["content"].strip()
        except Exception:
            return ""

    def _extract_important_info(self, user_query: str, response: str, provider_config: Dict) -> str:
        try:
            extract_messages = [
                {
                    "role": "system",
                    "content": "请提取以下对话中的重要事实、信息或结论，用简短的中文描述，适合作为长期记忆保存。如果没有重要信息，返回空字符串。",
                },
                {"role": "user", "content": f"用户：{user_query}\n助手：{response}"},
            ]
            result = self._call_llm(extract_messages, provider_config)
            content = result["content"].strip()
            return content if len(content) > 10 else ""
        except Exception:
            return ""

    def _edge_decide_next(self, state: AgentState) -> str:
        tool_call = state.get("tool_call")

        if not tool_call:
            return "final_response"

        if state.get("is_error") and state["reflection_count"] < state["max_reflection_attempts"]:
            return "reflection"

        return "final_response"

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("prepare_state", self._node_prepare_state)
        graph.add_node("call_llm", self._node_call_llm)
        graph.add_node("parse_and_execute_tool", self._node_parse_and_execute_tool)
        graph.add_node("reflection", self._node_reflection)
        graph.add_node("final_response", self._node_final_response)
        graph.add_node("update_memory", self._node_update_memory)

        graph.set_entry_point("prepare_state")

        graph.add_edge("prepare_state", "call_llm")
        graph.add_edge("call_llm", "parse_and_execute_tool")
        graph.add_conditional_edges("parse_and_execute_tool", self._edge_decide_next)
        graph.add_edge("reflection", "parse_and_execute_tool")
        graph.add_edge("final_response", "update_memory")
        graph.add_edge("update_memory", END)

        return graph.compile()

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

        provider_config = {
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "max_tokens": max_tokens,
            "original_messages": messages,
        }

        initial_state: AgentState = {
            "messages": [],
            "tool_results": [],
            "thinking_steps": [],
            "memory_context": {},
            "final_response": "",
            "tool_used": False,
            "reflection_count": 0,
            "step_count": 0,
            "llm_stats": {"completion_tokens": 0, "prompt_tokens": 0, "model": model},
            "provider_config": provider_config,
            "last_user_message": "",
            "tools_for_llm": [],
            "max_thinking_steps": self.max_thinking_steps,
            "max_reflection_attempts": self.max_reflection_attempts,
        }

        result = self.graph.invoke(initial_state)

        elapsed_time = time.time() - start_time
        llm_time = result["llm_stats"].get("llm_time", 0)
        tokens_per_second = round(result["llm_stats"]["completion_tokens"] / llm_time, 2) if llm_time > 0 else 0

        truncated_messages = truncate_messages(messages, max_tokens)

        return {
            "content": result["final_response"],
            "tool_used": result["tool_used"],
            "tool_info": result["tool_results"] if result["tool_results"] else None,
            "thinking": result["thinking_steps"],
            "reflection_count": result["reflection_count"],
            "memory_saved": False,
            "memory_context": result["memory_context"],
            "context_tokens": calculate_messages_tokens(truncated_messages),
            "original_messages_count": len(messages),
            "truncated_messages_count": len(truncated_messages),
            "completion_tokens": result["llm_stats"]["completion_tokens"],
            "prompt_tokens": result["llm_stats"]["prompt_tokens"],
            "total_tokens": result["llm_stats"]["completion_tokens"] + result["llm_stats"]["prompt_tokens"],
            "tokens_per_second": tokens_per_second,
            "response_time": round(elapsed_time, 2),
            "provider": provider,
            "model": result["llm_stats"].get("model") or model,
        }
