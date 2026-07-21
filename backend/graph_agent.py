import concurrent.futures
import json
import logging
import queue
import re
import threading
import time
from itertools import groupby
from typing import Any, Dict, Generator, List, Optional

from backend.context_manager import calculate_messages_tokens, truncate_messages

from .agent_types import AgentState
from .graph_builders import build_chat_graph, build_plan_execute_graph, build_react_graph
from .memory import memory_manager
from .providers import LLMError, llm_client
from .tools.base import tool_registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GraphAgent
# ---------------------------------------------------------------------------

class GraphAgent:

    def __init__(self):
        self._load_tools()
        self.summary_frequency = 5
        self.max_thinking_steps = 5
        self.max_reflection_attempts = 2

        self._chat_graph: Optional[StateGraph] = None
        self._react_graph: Optional[StateGraph] = None
        self._plan_execute_graph: Optional[StateGraph] = None

    # ================================================================
    # Shared Helpers
    # ================================================================

    @staticmethod
    def _load_tools():
        from .tools import (  # noqa: F401
            calculator, datetime_tool, file_tool, search, weather,
        )

    def _get_tools_for_llm(self) -> List[Dict[str, Any]]:
        tools = []
        for tool in tool_registry.tools.values():
            params = {}
            required = []
            for pn, pi in tool.parameters.items():
                params[pn] = {"type": pi.get("type", "string"), "description": pi.get("description", "")}
                if pi.get("required", False):
                    required.append(pn)
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {"type": "object", "properties": params, "required": required},
                },
            })
        return tools

    # ---- Keyword-based tool guessing ----

    @staticmethod
    def _guess_tool_for_query(query: str) -> Optional[str]:
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

    def _build_guessed_tool_calls(self, query: str, guessed_tool: str) -> List[Dict]:
        if guessed_tool == "calculator":
            match = re.search(r'[\d+\-*/().%\s]+', query)
            expr = match.group(0).strip() if match else query
            return [{"name": "calculator", "parameters": {"expression": expr}}]
        elif guessed_tool == "weather":
            cities = ["北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安",
                       "重庆", "天津", "苏州", "郑州", "长沙", "东莞"]
            city = next((c for c in cities if c in query), "北京")
            return [{"name": "weather", "parameters": {"city": city}}]
        elif guessed_tool == "datetime":
            return [{"name": "datetime", "parameters": {"action": "now"}}]
        elif guessed_tool == "search":
            return [{"name": "search", "parameters": {"query": query}}]
        elif guessed_tool == "file":
            return [{"name": "file", "parameters": {"action": "read", "file_path": query}}]
        return []

    # ---- LLM calls ----

    def _call_llm(self, messages: List[Dict], provider_config: Dict,
                   tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        return llm_client.chat_completion(
            messages=messages,
            provider_id=provider_config["provider"],
            model=provider_config.get("model"),
            max_tokens=provider_config.get("max_tokens", 2048),
            api_key=provider_config.get("api_key"),
            base_url=provider_config.get("base_url"),
            tools=tools,
            tool_choice="auto" if tools else None,
        )

    def _call_llm_stream(self, messages: List[Dict], provider_config: Dict,
                          tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Streaming LLM call.
        If ``_stream_queue`` exists in provider_config, pushes ``token`` events.
        Returns same shape as ``_call_llm`` (without token counts if not available).
        """
        q: Optional[queue.Queue] = provider_config.get("_stream_queue")
        content = ""
        completion_tokens = 0
        prompt_tokens = 0
        response_time = 0.0
        used_model: Optional[str] = None

        for event in llm_client.chat_completion_stream(
            messages=messages,
            provider_id=provider_config["provider"],
            model=provider_config.get("model"),
            max_tokens=provider_config.get("max_tokens", 2048),
            api_key=provider_config.get("api_key"),
            base_url=provider_config.get("base_url"),
            tools=tools,
            tool_choice="auto" if tools else None,
        ):
            if event["type"] == "token":
                content += event["content"]
                if q is not None:
                    q.put({"type": "token", "content": event["content"]})
            elif event["type"] == "error":
                if q is not None:
                    q.put(event)
                raise LLMError(event["content"], status_code=event.get("status_code", 500))
            elif event["type"] == "done":
                response_time = event.get("response_time", 0.0)
                used_model = event.get("model", provider_config.get("model"))

        return {
            "content": content,
            "completion_tokens": completion_tokens,
            "prompt_tokens": prompt_tokens,
            "total_tokens": completion_tokens + prompt_tokens,
            "response_time": response_time,
            "model": used_model or provider_config.get("model"),
        }

    # ---- Tool execution ----

    @staticmethod
    def _parse_tool_calls(response: Dict[str, Any]) -> List[Dict[str, Any]]:
        tool_calls = []
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc.get("type") == "function":
                    func = tc.get("function", {})
                    try:
                        params = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        params = {}
                    tool_calls.append({"name": func.get("name"), "parameters": params})

        if not tool_calls:
            text = response.get("content", "")
            matches = re.findall(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL)
            for m in matches:
                try:
                    tc = json.loads(m)
                    if isinstance(tc, dict) and "name" in tc and "parameters" in tc:
                        tool_calls.append(tc)
                except json.JSONDecodeError:
                    pass
        return tool_calls

    def _execute_tools_parallel(self, tool_calls: List[Dict]) -> List[Dict]:
        def execute_one(tc: Dict) -> Dict:
            return {"tool_name": tc["name"], "parameters": tc["parameters"],
                    "result": self._execute_tool(tc["name"], tc["parameters"])}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(tool_calls))) as pool:
            fti = {pool.submit(execute_one, tc): i for i, tc in enumerate(tool_calls)}
            results = [None] * len(tool_calls)
            for future in concurrent.futures.as_completed(fti):
                results[fti[future]] = future.result()
            return results

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        tool = tool_registry.get_tool(tool_name)
        if tool:
            try:
                return tool.execute(**parameters)
            except Exception as e:
                return f"工具执行错误：{str(e)}"
        return f"未找到工具：{tool_name}"

    # ---- Error detection & analysis ----

    @staticmethod
    def _is_error_result(result: str) -> bool:
        if not result or not result.strip():
            return True
        keywords = [
            "错误", "失败", "异常", "超时", "找不到", "无法", "拒绝", "无效",
            "error", "fail", "exception", "timeout", "not found", "cannot",
            "unable", "denied", "invalid", "connection", "unavailable",
        ]
        rl = result.lower()
        return any(kw in rl for kw in keywords)

    @staticmethod
    def _analyze_error(last_error: str) -> str:
        analysis = []
        if any(kw in last_error.lower() for kw in ["timeout", "超时", "connection"]):
            analysis.append("- 连接超时或网络错误，建议检查网络或换一种方式查询")
        if any(kw in last_error.lower() for kw in ["api key", "unauthorized", "denied", "拒绝", "认证"]):
            analysis.append("- API Key 认证失败，建议不依赖此工具直接回答")
        if any(kw in last_error.lower() for kw in ["not found", "找不到", "invalid", "无效"]):
            analysis.append("- 参数无效或资源不存在，请换一个不同的参数或工具")
        if any(kw in last_error.lower() for kw in ["tool", "未找到"]):
            analysis.append("- 工具不存在，请换用其他可用工具")
        return ("\n错误分析：\n" + "\n".join(analysis)) if analysis else ""

    # ---- JSON parsing helper ----

    @staticmethod
    def _parse_json_from_llm(content: str) -> Optional[Dict]:
        """Strip markdown fences then parse JSON from LLM response."""
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(l for l in lines if not l.startswith("```"))
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    # ---- Prompt builders ----

    def _build_system_prompt(self, memory_context: Dict) -> str:
        prompt = """你是一个 AI 助手，可以使用工具来获取信息或执行操作。

## 可用工具
- calculator: 数学计算（如：2+3、123*456）
- weather: 天气查询（如：北京天气）
- datetime: 时间日期查询（如：现在几点）
- search: 信息搜索（如：人工智能最新进展）
- file: 文件读取/写入操作

## 工作方式
1. 收到用户问题后，先思考需要什么信息，再决定是否调用工具
2. 如果需要工具，选择合适的工具并调用
3. 如果多个独立信息需要查询（如两个城市的天气），可以同时调多次工具
4. 工具执行后，根据结果整理最终回答
5. 如果不需要工具，直接回答即可

注意：不要编造工具调用的结果，必须实际调用工具获取真实信息。"""
        if memory_context.get("used"):
            prompt += f"\n\n## 相关记忆\n{memory_context.get('text', '')}"
        return prompt

    def _build_planning_prompt(self, memory_context: Dict) -> str:
        prompt = """你是 Plan-and-Execute 架构中的"规划器"(Planner)。

你的任务是：根据用户的问题，制定一个清晰的逐步执行计划。

## 规划要求
1. 先理解用户问题的本质，拆解出需要完成的关键任务
2. 每个步骤应聚焦一个独立的任务，包含明确可执行的动作
3. 如果多个步骤之间没有依赖关系，标注 parallel_group 字段使它们可并行执行
4. 步骤之间要有逻辑顺序（有依赖的步骤必须在前）
5. 如果问题简单（如打招呼、闲聊），直接回答即可

请严格按 JSON 格式回复（不要加 markdown 代码标记）：
对于需要计划的问题：
{"need_plan": true, "plan": [{"step": 1, "parallel_group": null, "description": "步骤描述", "suggested_tool": "calculator/weather/search/datetime/file/null"}, ...]}

如果多个步骤属于同一 parallel_group（如查两个城市的天气），它们会被并行执行。
同一组的步骤必须相互独立、没有依赖关系。

对于不需要计划的问题（简单问候、闲聊等）：
{"need_plan": false, "direct_response": "直接回复的内容"}"""
        if memory_context.get("used"):
            prompt += f"\n\n## 相关记忆\n{memory_context.get('text', '')}"
        return prompt

    @staticmethod
    def _build_executor_prompt(step_index: int, total_steps: int, step_desc: str, all_results: List[Dict]) -> str:
        results_text = ""
        if all_results:
            results_text = "\n\n## 已完成的步骤结果\n"
            for r in all_results:
                results_text += f"- 步骤{r['step']}: {r['description']}\n"
                if r.get("tool_result"):
                    results_text += f"  工具结果: {r['tool_result']}\n"
                if r.get("answer"):
                    results_text += f"  回答: {r['answer']}\n"

        return f"""你是 Plan-and-Execute 架构中的"执行器"(Executor)。

当前进度：步骤 {step_index}/{total_steps}
当前步骤描述：{step_desc}

你的任务：
1. 如果当前步骤需要调用工具，请直接调用对应的工具
2. 如果当前步骤不需要工具，用自然语言回答步骤描述的问题
3. 不要提前执行后续步骤
{results_text}"""

    # ---- Plan & Execute helpers ----

    def _generate_plan(self, query: str, provider_config: Dict,
                        memory_context: Optional[Dict] = None) -> Dict:
        messages = [
            {"role": "system", "content": self._build_planning_prompt(memory_context or {})},
            {"role": "user", "content": query},
        ]
        try:
            response = self._call_llm(messages, {**provider_config, "max_tokens": 1024})
            parsed = self._parse_json_from_llm(response["content"])
            if parsed is None:
                raise ValueError("Invalid JSON from planner")
            if parsed.get("need_plan") and isinstance(parsed.get("plan"), list):
                return {"need_plan": True, "plan": parsed["plan"], "llm_response": response}
            return {"need_plan": False, "direct_response": parsed.get("direct_response", ""), "llm_response": response}
        except (json.JSONDecodeError, Exception):
            return {"need_plan": False, "direct_response": "", "llm_response": None}

    def _execute_step(self, step_desc: str, step_index: int, total_steps: int,
                       all_results: List[Dict], tools_for_llm: List[Dict],
                       provider_config: Dict) -> Dict:
        executor_prompt = self._build_executor_prompt(step_index, total_steps, step_desc, all_results)
        messages = [{"role": "system", "content": executor_prompt},
                    {"role": "user", "content": step_desc}]

        response = self._call_llm(messages, provider_config, tools=tools_for_llm)
        tool_calls = self._parse_tool_calls(response)

        if tool_calls:
            tc = tool_calls[0]
            result = self._execute_tool(tc["name"], tc["parameters"])
            return {"tool_name": tc["name"], "parameters": tc["parameters"],
                    "tool_result": result, "answer": None, "llm_response": response}

        return {"tool_name": None, "parameters": None, "tool_result": None,
                "answer": response.get("content", ""), "llm_response": response}

    @staticmethod
    def _group_plan_steps(plan: List[Dict]) -> List[List[Dict]]:
        def key(s):
            return s.get("parallel_group") or f"seq_{s['step']}"
        sorted_plan = sorted(plan, key=key)
        groups = []
        for _, steps in groupby(sorted_plan, key=key):
            groups.append(list(steps))
        return groups

    # ---- Memory helpers ----

    def _generate_summary(self, messages: List[Dict], provider_config: Dict) -> str:
        try:
            sm = [
                {"role": "system", "content": "请用简短的中文总结以下对话内容，突出关键信息和结论。"},
                {"role": "user", "content": "\n".join(f"{m['role']}: {m['content']}" for m in messages[-10:])},
            ]
            resp = self._call_llm(sm, {**provider_config, "max_tokens": 200})
            return resp["content"].strip()
        except Exception:
            return ""

    def _extract_important_info(self, user_query: str, response: str, provider_config: Dict) -> Dict:
        try:
            msgs = [
                {"role": "system", "content": """分析以下对话，判断是否有值得长期记忆的重要信息。

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
8-10: 关键个人信息或重要决策"""},
                {"role": "user", "content": f"用户：{user_query}\n助手：{response}"},
            ]
            result = self._call_llm(msgs, {**provider_config, "max_tokens": 200})
            parsed = self._parse_json_from_llm(result["content"])
            if parsed is None:
                raise ValueError("Invalid JSON from memory extractor")
            if parsed.get("has_important") and parsed.get("importance", 0) >= 6:
                info = parsed.get("content", "").strip()
                if len(info) >= 10:
                    return {"has_important": True, "importance": min(parsed["importance"], 10), "content": info}
            return {"has_important": False, "importance": 0, "content": ""}
        except (json.JSONDecodeError, Exception):
            return {"has_important": False, "importance": 0, "content": ""}

    def _update_memories(self, messages: List[Dict], response: str,
                          last_user_message: str, provider_config: Dict, user_id: Optional[int] = None):
        # Short-term
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if len(user_msgs) % self.summary_frequency == 0:
            summary = self._generate_summary(messages, provider_config)
            if summary:
                memory_manager.add_short_term_summary(user_id, messages, summary)

        # Long-term
        importance_info = self._extract_important_info(last_user_message, response, provider_config)
        logger.info(
            f"[长期记忆] 重要性评估: has_important={importance_info.get('has_important')}, "
            f"importance={importance_info.get('importance')}, "
            f"content={importance_info.get('content')}"
        )
        if importance_info and importance_info.get("importance", 0) >= 6:
            logger.info(f"[长期记忆] 已存储 (重要性 {importance_info['importance']} >= 6): {importance_info['content']}")
            memory_manager.add_long_term_memory(user_id, importance_info["content"], category="knowledge")
        else:
            logger.info("[长期记忆] 跳过存储 (重要性 < 6 或无重要信息)")

    # ---- LLM stats accumulator ----

    @staticmethod
    def _merge_llm_stats(current: Dict, response: Dict) -> Dict:
        return {
            "completion_tokens": current.get("completion_tokens", 0) + response.get("completion_tokens", 0),
            "prompt_tokens": current.get("prompt_tokens", 0) + response.get("prompt_tokens", 0),
            "llm_time": current.get("llm_time", 0) + response.get("response_time", 0),
            "model": response.get("model") or current.get("model"),
        }

    # ================================================================
    # CHAT Graph
    # ================================================================

    def _node_prepare_chat_state(self, state: AgentState) -> AgentState:
        provider_config = state["provider_config"]
        messages = provider_config.get("original_messages", [])
        truncated = truncate_messages(messages, provider_config.get("max_tokens", 2048))
        return {
            **state,
            "messages": truncated,
            "last_user_message": messages[-1]["content"] if messages else "",
        }

    def _node_chat_call_llm(self, state: AgentState) -> AgentState:
        provider_config = state["provider_config"]
        is_stream = provider_config.get("_stream_queue") is not None

        if is_stream:
            q = provider_config["_stream_queue"]
            q.put({"type": "summary_start"})
            response = self._call_llm_stream(state["messages"], provider_config)
        else:
            response = self._call_llm(state["messages"], provider_config)

        return {
            **state,
            "final_response": response["content"],
            "llm_response": response,
            "llm_stats": self._merge_llm_stats(state["llm_stats"], response),
        }

    # ================================================================
    # REACT Graph
    # ================================================================

    def _node_prepare_state(self, state: AgentState) -> AgentState:
        provider_config = state["provider_config"]
        messages = provider_config.get("original_messages", [])
        last_user_message = messages[-1]["content"] if messages else ""
        truncated = truncate_messages(messages, provider_config.get("max_tokens", 2048))
        memory_context = memory_manager.get_context(provider_config.get("user_id"), last_user_message)
        tools_for_llm = self._get_tools_for_llm()

        system_prompt = self._build_system_prompt(memory_context)
        full_messages = [{"role": "system", "content": system_prompt}] + truncated

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
            "llm_stats": {"completion_tokens": 0, "prompt_tokens": 0, "model": provider_config.get("model")},
            "last_user_message": last_user_message,
            "tools_for_llm": tools_for_llm,
            "max_thinking_steps": self.max_thinking_steps,
            "max_reflection_attempts": self.max_reflection_attempts,
        }

    def _node_call_llm(self, state: AgentState) -> AgentState:
        # Only pass tools on the first step (traditional ReAct style)
        tools = state["tools_for_llm"] if state["step_count"] == 0 else None

        response = self._call_llm(state["messages"], state["provider_config"], tools=tools)

        tool_calls = self._parse_tool_calls(response)
        thinking = state["thinking_steps"].copy()

        # Try keyword fallback on first step if no tool calls
        if not tool_calls and state["step_count"] == 0:
            guessed = self._guess_tool_for_query(state["last_user_message"])
            if guessed:
                thinking.append(f"模型未调用工具，自动匹配到 {guessed} 工具")
                tool_calls = self._build_guessed_tool_calls(state["last_user_message"], guessed)

        q: Optional[queue.Queue] = state["provider_config"].get("_stream_queue")
        if q is not None and thinking != state["thinking_steps"]:
            q.put({"type": "thinking", "content": thinking[-1]})

        return {
            **state,
            "llm_response": response,
            "tool_calls": tool_calls,
            "thinking_steps": thinking,
            "llm_stats": self._merge_llm_stats(state["llm_stats"], response),
        }

    def _node_execute_tools(self, state: AgentState) -> AgentState:
        tool_calls = state.get("tool_calls")
        if not tool_calls:
            return {**state, "final_response": state.get("llm_response", {}).get("content", "")}

        q: Optional[queue.Queue] = state["provider_config"].get("_stream_queue")

        # Emit tool_call events
        if q is not None:
            for tc in tool_calls:
                q.put({"type": "tool_call", "tool_name": tc["name"], "parameters": tc["parameters"]})

        # Parallel execution
        results = self._execute_tools_parallel(tool_calls)

        # Emit tool_result events
        if q is not None:
            for r in results:
                q.put({"type": "tool_result", "tool_name": r["tool_name"], "result": r["result"]})

        # Append to message history
        new_messages = state["messages"].copy()
        assistant_tc = [
            {"type": "function", "function": {"name": tc["name"],
                                               "arguments": json.dumps(tc["parameters"], ensure_ascii=False)}}
            for tc in tool_calls
        ]
        new_messages.append({"role": "assistant", "content": "", "tool_calls": assistant_tc})
        for r in results:
            new_messages.append({"role": "tool", "content": r["result"]})

        new_tool_results = state["tool_results"].copy()
        new_tool_results.extend(results)

        has_error = any(self._is_error_result(r["result"]) for r in results)

        return {
            **state,
            "messages": new_messages,
            "tool_results": new_tool_results,
            "tool_used": True,
            "tool_results_batch": results,
            "has_error": has_error,
            "step_count": state["step_count"] + 1,
        }

    def _node_reflect(self, state: AgentState) -> AgentState:
        count = state["reflection_count"] + 1
        thinking = state["thinking_steps"].copy()
        thinking.append(f"反思第{count}次：工具调用失败，尝试调整策略")

        q: Optional[queue.Queue] = state["provider_config"].get("_stream_queue")
        if q is not None:
            q.put({"type": "thinking", "content": thinking[-1]})

        batch = state.get("tool_results_batch", [])
        if not batch:
            return {**state, "reflection_count": count, "thinking_steps": thinking}
        last_error = batch[-1]["result"]
        error_analysis = self._analyze_error(last_error)

        reflect_messages = state["messages"].copy()
        reflect_messages.append({
            "role": "assistant",
            "content": f"反思：上一步工具调用失败。结果：{last_error}。{error_analysis}\n"
                       f"请分析原因并选择：1) 换不同的参数重试 2) 换一个不同的工具 3) 直接回答用户说无法完成。",
        })

        response = self._call_llm(reflect_messages, state["provider_config"], tools=state["tools_for_llm"])
        tool_calls = self._parse_tool_calls(response)

        return {
            **state,
            "messages": reflect_messages,
            "llm_response": response,
            "tool_calls": tool_calls,
            "thinking_steps": thinking,
            "reflection_count": count,
            "llm_stats": self._merge_llm_stats(state["llm_stats"], response),
        }

    def _node_final(self, state: AgentState) -> AgentState:
        # If already have a final response (no tools case), skip LLM call
        if state["final_response"]:
            return state

        provider_config = state["provider_config"]

        # Sanitize messages for models that don't support tool role
        sanitized = []
        for m in state["messages"]:
            if m["role"] == "tool":
                sanitized.append({"role": "user", "content": f"[工具执行结果]\n{m['content']}"})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                sanitized.append({"role": "assistant", "content": f"[调用了工具: {m['tool_calls']}]"})
            else:
                sanitized.append(m)

        final_messages = sanitized + [
            {"role": "user", "content": "请根据以上对话内容（包含工具执行结果），用自然友好的语言给出最终回答。"}
        ]

        is_stream = provider_config.get("_stream_queue") is not None
        if is_stream:
            q = provider_config["_stream_queue"]
            q.put({"type": "summary_start"})
            response = self._call_llm_stream(final_messages, provider_config)
        else:
            response = self._call_llm(final_messages, provider_config)

        return {
            **state,
            "final_response": response["content"],
            "llm_response": response,
            "llm_stats": self._merge_llm_stats(state["llm_stats"], response),
        }

    def _edge_react_next(self, state: AgentState) -> str:
        tool_calls = state.get("tool_calls")

        if not tool_calls:
            return "final"

        if state.get("has_error") and state["reflection_count"] < state["max_reflection_attempts"]:
            return "reflect"

        return "final"

    # ================================================================
    # PLAN & EXECUTE Graph
    # ================================================================

    def _node_plan(self, state: AgentState) -> AgentState:
        provider_config = state["provider_config"]
        plan_result = self._generate_plan(
            state["last_user_message"],
            provider_config,
            memory_context=state.get("memory_context"),
        )

        # Accumulate LLM stats from planner call
        if plan_result.get("llm_response"):
            llm_stats = self._merge_llm_stats(
                state["llm_stats"],
                plan_result["llm_response"],
            )
        else:
            llm_stats = state["llm_stats"]

        # No plan needed
        if not plan_result.get("need_plan"):
            direct = plan_result.get("direct_response", "")
            # Emit streaming token so frontend displays the response
            q: Optional[queue.Queue] = provider_config.get("_stream_queue")
            if q is not None and direct:
                q.put({"type": "token", "content": direct})
            return {
                **state,
                "final_response": direct,
                "plan": [],
                "groups": [],
                "plan_steps": [],
                "total_steps": 0,
                "current_group_index": 0,
                "step_results": [],
                "llm_stats": llm_stats,
            }

        plan = plan_result["plan"]
        groups = self._group_plan_steps(plan)
        plan_steps = [f"步骤{s['step']}: {s['description']}" for s in plan]

        # Emit plan event (streaming)
        q: Optional[queue.Queue] = provider_config.get("_stream_queue")
        if q is not None:
            q.put({"type": "plan", "plan": plan, "steps": plan_steps})

        return {
            **state,
            "plan": plan,
            "groups": groups,
            "plan_steps": plan_steps,
            "total_steps": len(plan),
            "current_group_index": 0,
            "step_results": [],
            "tool_results": [],
            "tool_used": False,
            "llm_stats": llm_stats,
        }

    def _node_execute_group(self, state: AgentState) -> AgentState:
        groups = state.get("groups", [])
        idx = state.get("current_group_index", 0)

        if idx >= len(groups):
            return {**state, "current_group_index": idx}

        group = groups[idx]
        q: Optional[queue.Queue] = state["provider_config"].get("_stream_queue")
        tools_for_llm = state["tools_for_llm"]
        provider_config = state["provider_config"]
        total_steps = state["total_steps"]
        thinking = state["thinking_steps"].copy()
        step_results = state["step_results"].copy()
        tool_results = state["tool_results"].copy()
        tool_used = state["tool_used"]
        llm_stats = state["llm_stats"]

        is_parallel = group[0].get("parallel_group") is not None and len(group) > 1

        if is_parallel:
            thinking.append(f"并行执行 {len(group)} 个独立步骤")
            if q is not None:
                q.put({"type": "thinking", "content": thinking[-1]})

            def exec_one(s):
                return s, self._execute_step(
                    step_desc=s["description"], step_index=s["step"],
                    total_steps=total_steps, all_results=step_results,
                    tools_for_llm=tools_for_llm, provider_config=provider_config,
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=len(group)) as pool:
                futures = {pool.submit(exec_one, s): s for s in group}
                for future in concurrent.futures.as_completed(futures):
                    s, result = future.result()
                    step_num = s["step"]
                    self._record_step_result(result, step_num, s["description"],
                                              step_results, tool_results, thinking, q)
                    llm_stats = self._merge_llm_stats(llm_stats, result.get("llm_response", {}))
                    if result.get("tool_name"):
                        tool_used = True
        else:
            for s in group:
                step_num = s["step"]
                step_desc = s["description"]
                msg = f"正在执行步骤 {step_num}/{total_steps}: {step_desc}"
                thinking.append(msg)
                if q is not None:
                    q.put({"type": "thinking", "content": msg})

                result = self._execute_step(
                    step_desc=step_desc, step_index=step_num,
                    total_steps=total_steps, all_results=step_results,
                    tools_for_llm=tools_for_llm, provider_config=provider_config,
                )
                self._record_step_result(result, step_num, step_desc,
                                          step_results, tool_results, thinking, q)
                llm_stats = self._merge_llm_stats(llm_stats, result.get("llm_response", {}))
                if result.get("tool_name"):
                    tool_used = True

        return {
            **state,
            "current_group_index": idx + 1,
            "step_results": step_results,
            "tool_results": tool_results,
            "tool_used": tool_used,
            "thinking_steps": thinking,
            "llm_stats": llm_stats,
        }

    @staticmethod
    def _record_step_result(step_result: Dict, step_num: int, desc: str,
                             step_results: List, tool_results: List,
                             thinking: List, q: Optional[queue.Queue]):
        step_results.append({
            "step": step_num,
            "description": desc,
            "tool_name": step_result.get("tool_name"),
            "tool_result": step_result.get("tool_result"),
            "answer": step_result.get("answer"),
        })
        if step_result.get("tool_name"):
            tool_results.append({
                "tool_name": step_result["tool_name"],
                "parameters": step_result["parameters"],
                "result": step_result["tool_result"],
                "step": step_num,
            })
            note = f"步骤{step_num} → 调用了 {step_result['tool_name']}: {(step_result.get('tool_result') or '')[:100]}"
            thinking.append(note)
            if q is not None:
                q.put({"type": "tool_call", "tool_name": step_result["tool_name"],
                       "parameters": step_result["parameters"], "step": step_num})
                q.put({"type": "tool_result", "tool_name": step_result["tool_name"],
                       "result": step_result["tool_result"], "step": step_num})
        elif step_result.get("answer"):
            note = f"步骤{step_num} → {(step_result['answer'] or '')[:100]}"
            thinking.append(note)

    def _node_summarize(self, state: AgentState) -> AgentState:
        provider_config = state["provider_config"]

        step_summary = "\n".join(
            f"步骤{r['step']} ({r['description']}): "
            + (f"工具结果: {r['tool_result']}" if r.get("tool_result") else f"回答: {r['answer']}")
            for r in state.get("step_results", [])
        )

        original_messages = provider_config.get("original_messages", [])
        truncated = truncate_messages(original_messages, provider_config.get("max_tokens", 2048))

        final_messages = [
            {"role": "system",
             "content": "你是一个 AI 助手。请根据以下逐步执行的结果，用自然友好的语言给用户一个完整、清晰的回答。"},
        ] + truncated + [
            {"role": "user", "content": f"## 执行结果\n{step_summary}\n\n请根据以上结果，回答用户的原始问题。"}
        ]

        is_stream = provider_config.get("_stream_queue") is not None
        if is_stream:
            q = provider_config["_stream_queue"]
            q.put({"type": "summary_start"})
            response = self._call_llm_stream(final_messages, provider_config)
        else:
            response = self._call_llm(final_messages, provider_config)

        return {
            **state,
            "final_response": response["content"],
            "llm_stats": self._merge_llm_stats(state["llm_stats"], response),
        }

    def _edge_after_plan(self, state: AgentState) -> str:
        if state.get("final_response"):
            return "memory"
        return "execute"

    def _edge_plan_next(self, state: AgentState) -> str:
        if state["current_group_index"] >= len(state.get("groups", [])):
            return "summarize"
        return "execute_group"

    # ================================================================
    # Shared Node: update_memory
    # ================================================================

    def _node_update_memory(self, state: AgentState) -> AgentState:
        provider_config = state["provider_config"]
        final_response = state["final_response"]
        last_user_message = state["last_user_message"]
        user_id = provider_config.get("user_id")

        self._update_memories(
            messages=provider_config.get("original_messages", []),
            response=final_response,
            last_user_message=last_user_message,
            provider_config=provider_config,
            user_id=user_id,
        )
        return state

    # ================================================================
    # Graph Selection
    # ================================================================

    def _build_provider_config(self, messages: List[Dict], max_tokens: int,
                                provider: str, model: Optional[str],
                                api_key: Optional[str], base_url: Optional[str],
                                user_id: Optional[int] = None,
                                stream_queue: Optional[queue.Queue] = None) -> Dict:
        config: Dict[str, Any] = {
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "max_tokens": max_tokens,
            "original_messages": messages,
            "user_id": user_id,
        }
        if stream_queue is not None:
            config["_stream_queue"] = stream_queue
        return config

    def _build_initial_state(self, model: Optional[str]) -> AgentState:
        return {
            "messages": [],
            "final_response": "",
            "llm_stats": {"completion_tokens": 0, "prompt_tokens": 0, "model": model},
            "provider_config": {},
            "last_user_message": "",
            "tools_for_llm": [],
            # ReAct
            "tool_results": [],
            "thinking_steps": [],
            "memory_context": {},
            "tool_used": False,
            "reflection_count": 0,
            "step_count": 0,
            "max_thinking_steps": self.max_thinking_steps,
            "max_reflection_attempts": self.max_reflection_attempts,
            "llm_response": {},
            "tool_calls": [],
            "tool_results_batch": [],
            "has_error": False,
            # Plan & Execute
            "plan": [],
            "groups": [],
            "current_group_index": 0,
            "step_results": [],
            "total_steps": 0,
            "plan_steps": [],
        }

    def _get_graph(self, mode: str):
        if mode == "chat":
            if self._chat_graph is None:
                self._chat_graph = build_chat_graph(self)
            return self._chat_graph
        elif mode == "react":
            if self._react_graph is None:
                self._react_graph = build_react_graph(self)
            return self._react_graph
        elif mode == "plan_execute":
            if self._plan_execute_graph is None:
                self._plan_execute_graph = build_plan_execute_graph(self)
            return self._plan_execute_graph
        else:
            raise ValueError(f"Unknown agent mode: {mode}")

    # ================================================================
    # Public API
    # ================================================================

    def run(self, messages: List[Dict], max_tokens: int = 2048,
            provider: str = "llama_cpp", model: Optional[str] = None,
            api_key: Optional[str] = None, base_url: Optional[str] = None,
            user_id: Optional[int] = None,
            mode: str = "react") -> Dict[str, Any]:
        """Non-streaming execution. Routes to the appropriate LangGraph based on *mode*."""
        start = time.time()

        provider_config = self._build_provider_config(
            messages, max_tokens, provider, model, api_key, base_url, user_id,
        )

        graph = self._get_graph(mode)

        initial: AgentState = self._build_initial_state(model)  # type: ignore[typeddict-item]
        initial["provider_config"] = provider_config

        result = graph.invoke(initial)

        elapsed = time.time() - start
        llm_time = result["llm_stats"].get("llm_time", 0)
        tps = round(result["llm_stats"]["completion_tokens"] / llm_time, 2) if llm_time > 0 else 0
        truncated = truncate_messages(messages, max_tokens)

        return {
            "content": result["final_response"],
            "tool_used": result["tool_used"],
            "tool_info": result["tool_results"] if result["tool_results"] else None,
            "thinking": result["thinking_steps"],
            "plan": result.get("plan_steps"),
            "reflection_count": result["reflection_count"],
            "memory_saved": False,
            "memory_context": result.get("memory_context", {}),
            "context_tokens": calculate_messages_tokens(truncated),
            "original_messages_count": len(messages),
            "truncated_messages_count": len(truncated),
            "completion_tokens": result["llm_stats"]["completion_tokens"],
            "prompt_tokens": result["llm_stats"]["prompt_tokens"],
            "total_tokens": result["llm_stats"]["completion_tokens"] + result["llm_stats"]["prompt_tokens"],
            "tokens_per_second": tps,
            "response_time": round(elapsed, 2),
            "provider": provider,
            "model": result["llm_stats"].get("model") or model,
        }

    def run_stream(self, messages: List[Dict], max_tokens: int = 2048,
                   provider: str = "llama_cpp", model: Optional[str] = None,
                   api_key: Optional[str] = None, base_url: Optional[str] = None,
                   user_id: Optional[int] = None,
                   mode: str = "react") -> Generator[Dict[str, Any], None, None]:
        """Streaming execution.
        Runs the LangGraph in a background thread; pushes events through a queue.
        Yields the same event types as before (token, tool_call, tool_result, …).
        """
        start = time.time()
        q: queue.Queue = queue.Queue()

        provider_config = self._build_provider_config(
            messages, max_tokens, provider, model, api_key, base_url, user_id, stream_queue=q,
        )

        graph = self._get_graph(mode)

        initial: AgentState = self._build_initial_state(model)  # type: ignore[typeddict-item]
        initial["provider_config"] = provider_config

        result_container: Dict[str, Any] = {}

        def _run():
            try:
                res = graph.invoke(initial)
                result_container.update(res)
            except Exception as exc:
                logger.exception("LangGraph streaming thread error")
                q.put({"type": "error", "content": str(exc)})
            finally:
                q.put(None)  # sentinel

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        # Drain queue
        full_content = ""
        while True:
            event = q.get()
            if event is None:
                break
            if event["type"] == "token":
                full_content += event.get("content", "")
            yield event

        thread.join()

        # Build final done event
        if not result_container:
            return

        elapsed = time.time() - start
        llm_stats = result_container.get("llm_stats", {})
        llm_time = llm_stats.get("llm_time", 0)
        tps = round(llm_stats.get("completion_tokens", 0) / llm_time, 2) if llm_time > 0 else 0

        yield {
            "type": "done",
            "content": full_content or result_container.get("final_response", ""),
            "tool_used": result_container.get("tool_used", False),
            "tool_info": result_container.get("tool_results") or None,
            "thinking": result_container.get("thinking_steps", []),
            "plan": result_container.get("plan_steps"),
            "reflection_count": result_container.get("reflection_count", 0),
            "completion_tokens": llm_stats.get("completion_tokens", 0),
            "prompt_tokens": llm_stats.get("prompt_tokens", 0),
            "total_tokens": llm_stats.get("completion_tokens", 0) + llm_stats.get("prompt_tokens", 0),
            "tokens_per_second": tps,
            "response_time": round(elapsed, 2),
            "provider": provider,
            "model": llm_stats.get("model") or model,
        }
