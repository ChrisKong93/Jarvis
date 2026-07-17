import json
import re
import time
from typing import Any, Dict, Generator, List, Optional, TypedDict

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
                if param_info.get("required", False):
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
        memory_context = memory_manager.get_context(state["provider_config"].get("user_id"), last_user_message)
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
        
        if not state["tool_used"] and llm_response and llm_response.get("content"):
            return {
                **state,
                "final_response": llm_response["content"],
            }

        # 将 tool 角色消息转为 user 格式（兼容不支持 tool 角色的自定义模型）
        sanitized = []
        for m in state["messages"]:
            if m["role"] == "tool":
                sanitized.append({"role": "user", "content": f"[工具执行结果]\n{m['content']}"})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                sanitized.append({"role": "assistant", "content": f"[调用了工具: {m['tool_calls']}]"})
            else:
                sanitized.append(m)

        final_messages = sanitized + [{
            "role": "user",
            "content": "请根据以上对话内容（包含工具执行结果），用自然友好的语言给出最终回答。"
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
        
        # 短期记忆：每 N 轮生成对话总结
        if len(user_messages) % self.summary_frequency == 0:
            summary = self._generate_summary(messages, state["provider_config"])
            if summary:
                memory_manager.add_short_term_summary(state["provider_config"].get("user_id"), messages, summary)

        # 长期记忆：仅当重要性 >= 6 时才写入（带自动去重）
        importance_info = self._extract_important_info(
            state["last_user_message"],
            response,
            state["provider_config"],
        )
        print(f"\n📝 [长期记忆] 重要性评估: has_important={importance_info.get('has_important')}, importance={importance_info.get('importance')}, content={importance_info.get('content')}", flush=True)
        if importance_info and importance_info.get("importance", 0) >= 6:
            print(f"✅ [长期记忆] 已存储 (重要性 {importance_info['importance']} ≥ 6): {importance_info['content']}", flush=True)
            memory_manager.add_long_term_memory(
                state["provider_config"].get("user_id"),
                importance_info["content"],
                category="knowledge",
            )
        else:
            print(f"⏭️ [长期记忆] 跳过存储 (重要性 < 6 或无重要信息)", flush=True)

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

    def _extract_important_info(self, user_query: str, response: str, provider_config: Dict) -> Dict:
        """分析对话是否有值得长期记忆的信息，返回重要性评分和内容。

        Returns:
            Dict: {"has_important": bool, "importance": int 1-10, "content": str}
                  重要性 <= 3 表示日常闲聊，4-5 有用但不关键，>= 6 值得记忆。
        """
        try:
            extract_messages = [
                {
                    "role": "system",
                    "content": """分析以下对话，判断是否有值得长期记忆的重要信息。

值得记忆的信息包括：
- 用户个人信息（姓名、职业、所在地、联系方式等）
- 用户的明确偏好或习惯（"我喜欢用 Python"）
- 重要决策或计划
- 用户明确要求记住的内容

不值得记忆的信息包括：
- 日常问候、闲聊
- 临时性事务（"今天天气不错"）
- 当前对话中的普通问答

请严格按 JSON 格式回复（不要加 markdown 代码标记）：
{"has_important": true/false, "importance": 1-10, "content": "提炼后的信息（一句话）"}

重要性评分标准：
1-3: 日常闲聊，不记忆
4-5: 有些用但不关键
6-7: 值得记忆的背景信息
8-10: 关键个人信息或重要决策""",
                },
                {"role": "user", "content": f"用户：{user_query}\n助手：{response}"},
            ]
            result = self._call_llm(extract_messages, provider_config)
            content = result["content"].strip()

            # 尝试解析 JSON
            import json
            # 去掉可能的 markdown 代码标记
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(l for l in lines if not l.startswith("```"))
            parsed = json.loads(content)

            if parsed.get("has_important") and parsed.get("importance", 0) >= 6:
                info_content = parsed.get("content", "").strip()
                if len(info_content) >= 10:
                    return {
                        "has_important": True,
                        "importance": min(parsed["importance"], 10),
                        "content": info_content,
                    }

            return {"has_important": False, "importance": 0, "content": ""}
        except (json.JSONDecodeError, Exception):
            return {"has_important": False, "importance": 0, "content": ""}

    def _edge_decide_next(self, state: AgentState) -> str:
        tool_call = state.get("tool_call")

        if not tool_call:
            return "generate_final_response"

        if state.get("is_error") and state["reflection_count"] < state["max_reflection_attempts"]:
            return "reflection"

        return "generate_final_response"

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("prepare_state", self._node_prepare_state)
        graph.add_node("call_llm", self._node_call_llm)
        graph.add_node("parse_and_execute_tool", self._node_parse_and_execute_tool)
        graph.add_node("reflection", self._node_reflection)
        graph.add_node("generate_final_response", self._node_final_response)
        graph.add_node("update_memory", self._node_update_memory)

        graph.set_entry_point("prepare_state")

        graph.add_edge("prepare_state", "call_llm")
        graph.add_edge("call_llm", "parse_and_execute_tool")
        graph.add_conditional_edges("parse_and_execute_tool", self._edge_decide_next)
        graph.add_edge("reflection", "parse_and_execute_tool")
        graph.add_edge("generate_final_response", "update_memory")
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
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()

        provider_config = {
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "max_tokens": max_tokens,
            "original_messages": messages,
            "user_id": user_id,
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

    def run_stream(
        self,
        messages: List[Dict],
        max_tokens: int = 2048,
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """流式运行 agent，逐事件产出。

        Yields:
            {"type": "token", "content": str}          — 文本 token
            {"type": "tool_call", ...}                 — 工具调用信息
            {"type": "tool_result", ...}               — 工具执行结果
            {"type": "thinking", "content": str}       — 思考/状态信息
            {"type": "summary_start"}                  — 开始生成最终总结
            {"type": "done", "content": str, "stats": dict}  — 完成
            {"type": "error", "content": str}          — 错误
        """
        start_time = time.time()

        # ---------- 准备阶段 ----------
        last_user_message = messages[-1]["content"] if messages else ""
        truncated_messages = truncate_messages(messages, max_tokens)
        memory_context = memory_manager.get_context(user_id, last_user_message)
        tools_for_llm = self._get_tools_for_llm()

        system_prompt = self._build_system_prompt(memory_context)
        full_messages = [{"role": "system", "content": system_prompt}] + truncated_messages

        provider_config = {
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "max_tokens": max_tokens,
        }

        current_messages = full_messages.copy()
        tool_results = []
        thinking_steps = []
        reflection_count = 0
        tool_used = False
        final_response = ""
        llm_stats = {"completion_tokens": 0, "prompt_tokens": 0, "model": model}

        # ---------- 第一阶段：首次 LLM 调用（非流式，检测是否需要工具） ----------
        try:
            llm_response = self._call_llm(
                current_messages,
                provider_config,
                tools=tools_for_llm,
            )
        except LLMError as exc:
            yield {"type": "error", "content": str(exc)}
            return

        llm_stats["completion_tokens"] += llm_response["completion_tokens"]
        llm_stats["prompt_tokens"] += llm_response["prompt_tokens"]
        llm_stats["llm_time"] = llm_stats.get("llm_time", 0) + llm_response.get("response_time", 0)
        used_model = llm_response.get("model") or model

        tool_call = self._parse_tool_call(llm_response)

        # 模型没调用工具时：自动匹配
        if not tool_call:
            guessed_tool = self._guess_tool_for_query(last_user_message)
            if guessed_tool:
                thinking_steps.append(f"模型未调用工具，自动匹配到 {guessed_tool} 工具")
                yield {"type": "thinking", "content": thinking_steps[-1]}
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

        # ---------- 第二阶段：执行工具（如果需要） ----------
        if tool_call:
            yield {"type": "tool_call", "tool_name": tool_call["name"], "parameters": tool_call["parameters"]}

            tool_result = self._execute_tool(tool_call["name"], tool_call["parameters"])
            tool_used = True

            tool_results.append({
                "tool_name": tool_call["name"],
                "parameters": tool_call["parameters"],
                "result": tool_result,
            })

            yield {"type": "tool_result", "tool_name": tool_call["name"], "result": tool_result}

            # 添加 tool_call / tool 消息到上下文
            current_messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "type": "function",
                    "function": {
                        "name": tool_call["name"],
                        "arguments": json.dumps(tool_call["parameters"], ensure_ascii=False),
                    },
                }],
            })
            current_messages.append({"role": "tool", "content": tool_result})

            is_error = "错误" in tool_result or "失败" in tool_result

            # 错误时反思
            if is_error and reflection_count < self.max_reflection_attempts:
                reflection_count += 1
                thinking_steps.append(f"反思第{reflection_count}次：工具调用失败，尝试调整策略")
                yield {"type": "thinking", "content": thinking_steps[-1]}

                reflect_messages = current_messages + [{
                    "role": "assistant",
                    "content": f"反思：工具执行失败。上一步结果：{tool_result}。请分析原因并给出调整后的方案，可以调用其他工具或直接回答。",
                }]

                try:
                    reflect_response = self._call_llm(
                        reflect_messages,
                        provider_config,
                        tools=tools_for_llm,
                    )
                except LLMError as exc:
                    yield {"type": "error", "content": str(exc)}
                    return

                llm_stats["completion_tokens"] += reflect_response["completion_tokens"]
                llm_stats["prompt_tokens"] += reflect_response["prompt_tokens"]
                llm_stats["llm_time"] = llm_stats.get("llm_time", 0) + reflect_response.get("response_time", 0)
                used_model = reflect_response.get("model") or used_model

                reflect_tool_call = self._parse_tool_call(reflect_response)
                if reflect_tool_call:
                    yield {"type": "tool_call", "tool_name": reflect_tool_call["name"], "parameters": reflect_tool_call["parameters"], "is_reflection": True}
                    reflect_result = self._execute_tool(reflect_tool_call["name"], reflect_tool_call["parameters"])
                    tool_results.append({
                        "tool_name": reflect_tool_call["name"],
                        "parameters": reflect_tool_call["parameters"],
                        "result": reflect_result,
                        "is_reflection": True,
                    })
                    yield {"type": "tool_result", "tool_name": reflect_tool_call["name"], "result": reflect_result, "is_reflection": True}

                    current_messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "type": "function",
                            "function": {
                                "name": reflect_tool_call["name"],
                                "arguments": json.dumps(reflect_tool_call["parameters"], ensure_ascii=False),
                            },
                        }],
                    })
                    current_messages.append({"role": "tool", "content": reflect_result})
                else:
                    final_response = reflect_response["content"]

        # ---------- 第三阶段：生成最终回答（流式） ----------
        if not final_response or tool_used:
            yield {"type": "summary_start"}

            # Sanitize messages
            sanitized = []
            for m in current_messages:
                if m["role"] == "tool":
                    sanitized.append({"role": "user", "content": f"[工具执行结果]\n{m['content']}"})
                elif m["role"] == "assistant" and m.get("tool_calls"):
                    sanitized.append({"role": "assistant", "content": f"[调用了工具: {m['tool_calls']}]"})
                else:
                    sanitized.append(m)

            final_messages = sanitized + [{
                "role": "user",
                "content": "请根据以上对话内容（包含工具执行结果），用自然友好的语言给出最终回答。"
            }]

            try:
                for event in llm_client.chat_completion_stream(
                    messages=final_messages,
                    provider_id=provider,
                    model=used_model,
                    max_tokens=max_tokens,
                    api_key=api_key,
                    base_url=base_url,
                ):
                    if event["type"] == "token":
                        final_response += event["content"]
                        yield {"type": "token", "content": event["content"]}
                    elif event["type"] == "error":
                        yield event
                        return
                    elif event["type"] == "done":
                        llm_stats["model"] = event.get("model") or used_model
            except LLMError as exc:
                yield {"type": "error", "content": str(exc)}
                return

        # ---------- 记忆更新 ----------
        try:
            memory_provider_config = provider_config.copy()
            memory_provider_config["original_messages"] = messages
            memory_provider_config["user_id"] = user_id
            self._node_update_memory({
                "provider_config": memory_provider_config,
                "final_response": final_response,
                "last_user_message": last_user_message,
            })
        except Exception as exc:
            print(f"[记忆更新] 异常: {exc}", flush=True)

        elapsed_time = time.time() - start_time
        total_tokens = llm_stats["completion_tokens"] + llm_stats["prompt_tokens"]
        llm_time = llm_stats.get("llm_time", 0)
        tokens_per_second = round(llm_stats["completion_tokens"] / llm_time, 2) if llm_time > 0 else 0

        yield {
            "type": "done",
            "content": final_response,
            "tool_used": tool_used,
            "tool_info": tool_results if tool_results else None,
            "thinking": thinking_steps,
            "reflection_count": reflection_count,
            "completion_tokens": llm_stats["completion_tokens"],
            "prompt_tokens": llm_stats["prompt_tokens"],
            "total_tokens": total_tokens,
            "tokens_per_second": tokens_per_second,
            "response_time": round(elapsed_time, 2),
            "provider": provider,
            "model": llm_stats.get("model") or model,
        }
