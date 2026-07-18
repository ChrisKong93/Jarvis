import json
import re
import time
from typing import Any, Dict, Generator, List, Optional

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

    def _build_planning_prompt(self, memory_context: Dict) -> str:
        prompt = """你是 Plan-and-Execute 架构中的"规划器"(Planner)。

你的任务是：根据用户的问题，制定一个清晰的逐步执行计划。

要求：
1. 将复杂任务分解为 2-6 个具体步骤
2. 每个步骤应包含一个明确可执行的动作
3. 步骤之间要有逻辑顺序
4. 如果问题简单（如打招呼、闲聊），直接回答即可，不要编造计划

请严格按 JSON 格式回复（不要加 markdown 代码标记）：
对于需要计划的问题：
{"need_plan": true, "plan": [{"step": 1, "description": "步骤描述", "suggested_tool": "calculator/weather/search/datetime/file/null"}, ...]}

对于不需要计划的问题（简单问候、闲聊等）：
{"need_plan": false, "direct_response": "直接回复的内容"}"""
        if memory_context.get("used"):
            prompt += f"\n\n## 相关记忆\n{memory_context.get('text', '')}"
        return prompt

    def _build_executor_prompt(self, step_index: int, total_steps: int, step_desc: str, all_results: List[Dict]) -> str:
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

    def _generate_plan(
        self,
        query: str,
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        memory_context: Optional[Dict] = None,
    ) -> Dict:
        """生成执行计划。返回 {"need_plan": bool, "plan": [...], "direct_response": str}"""
        messages = [
            {"role": "system", "content": self._build_planning_prompt(memory_context or {})},
            {"role": "user", "content": query},
        ]
        try:
            response = self._call_llm(
                messages,
                max_tokens=1024,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
            content = response["content"].strip()
            # 去掉可能的 markdown 代码标记
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(l for l in lines if not l.startswith("```"))
            parsed = json.loads(content)
            if parsed.get("need_plan") and isinstance(parsed.get("plan"), list):
                return {"need_plan": True, "plan": parsed["plan"], "llm_response": response}
            return {"need_plan": False, "direct_response": parsed.get("direct_response", ""), "llm_response": response}
        except (json.JSONDecodeError, Exception) as e:
            return {"need_plan": False, "direct_response": "", "llm_response": None}

    def _parse_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 LLM 响应中提取所有工具调用。"""
        tool_calls = []
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc.get("type") == "function":
                    func = tc.get("function", {})
                    try:
                        params = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        params = {}
                    tool_calls.append({
                        "name": func.get("name"),
                        "parameters": params,
                    })

        if not tool_calls:
            text = response.get("content", "")
            pattern = r"<tool_call>(.*?)</tool_call>"
            matches = re.findall(pattern, text, re.DOTALL)
            for m in matches:
                try:
                    tc = json.loads(m)
                    if isinstance(tc, dict) and "name" in tc and "parameters" in tc:
                        tool_calls.append(tc)
                except json.JSONDecodeError:
                    pass

        return tool_calls

    def _execute_tools_parallel(self, tool_calls: List[Dict]) -> List[Dict]:
        """并行执行多个工具调用。"""
        import concurrent.futures

        def _execute_one(tc: Dict) -> Dict:
            name = tc["name"]
            params = tc["parameters"]
            result = self._execute_tool(name, params)
            return {"tool_name": name, "parameters": params, "result": result}

        if len(tool_calls) <= 1:
            return [_execute_one(tc) for tc in tool_calls]

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tool_calls)) as pool:
            future_to_idx = {pool.submit(_execute_one, tc): i for i, tc in enumerate(tool_calls)}
            results = [None] * len(tool_calls)
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                results[idx] = future.result()
            return results

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        tool = tool_registry.get_tool(tool_name)
        if tool:
            try:
                return tool.execute(**parameters)
            except Exception as e:
                return f"工具执行错误：{str(e)}"
        return f"未找到工具：{tool_name}"

    def _execute_step(
        self,
        step_desc: str,
        step_index: int,
        total_steps: int,
        all_results: List[Dict],
        tools_for_llm: List[Dict],
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> Dict:
        """执行计划中的一个步骤，返回执行结果。"""
        executor_prompt = self._build_executor_prompt(step_index, total_steps, step_desc, all_results)
        messages = [{"role": "system", "content": executor_prompt}, {"role": "user", "content": step_desc}]

        response = self._call_llm(
            messages,
            max_tokens=max_tokens,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            tools=tools_for_llm,
        )

        tool_calls = self._parse_tool_calls(response)
        if tool_calls:
            tc = tool_calls[0]  # 每个步骤只执行第一个工具调用
            result = self._execute_tool(tc["name"], tc["parameters"])
            return {
                "tool_name": tc["name"],
                "parameters": tc["parameters"],
                "tool_result": result,
                "answer": None,
                "llm_response": response,
            }

        return {
            "tool_name": None,
            "parameters": None,
            "tool_result": None,
            "answer": response.get("content", ""),
            "llm_response": response,
        }

    def run(
        self,
        messages: List[Dict],
        max_tokens: int = 2048,
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        user_id: Optional[int] = None,
        mode: str = "react",
    ) -> Dict[str, Any]:
        start_time = time.time()

        truncated_messages = truncate_messages(messages, max_tokens)
        last_user_message = messages[-1]["content"] if messages else ""
        memory_context = memory_manager.get_context(user_id, last_user_message)

        if mode == "plan_execute":
            return self._run_plan_execute(
                messages, truncated_messages, last_user_message, memory_context,
                max_tokens, provider, model, api_key, base_url, user_id, start_time,
            )

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

            tool_calls = self._parse_tool_calls(llm_response)

            if not tool_calls and step_count == 0:
                guessed_tool = self._guess_tool_for_query(last_user_message)
                if guessed_tool:
                    thinking_steps.append(f"模型未调用工具，自动匹配到 {guessed_tool} 工具")
                    if guessed_tool == "calculator":
                        match = re.search(r'[\d+\-*/().%\s]+', last_user_message)
                        expression = match.group(0).strip() if match else last_user_message
                        tool_calls = [{"name": "calculator", "parameters": {"expression": expression}}]
                    elif guessed_tool == "weather":
                        cities = ["北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", "重庆", "天津", "苏州", "郑州", "长沙", "东莞"]
                        city = next((c for c in cities if c in last_user_message), "北京")
                        tool_calls = [{"name": "weather", "parameters": {"city": city}}]
                    elif guessed_tool == "datetime":
                        tool_calls = [{"name": "datetime", "parameters": {"action": "now"}}]
                    elif guessed_tool == "search":
                        tool_calls = [{"name": "search", "parameters": {"query": last_user_message}}]
                    elif guessed_tool == "file":
                        tool_calls = [{"name": "file", "parameters": {"action": "read", "file_path": last_user_message}}]

            if tool_calls:
                tool_used = True

                # 并行执行所有工具
                results = self._execute_tools_parallel(tool_calls)

                for r in results:
                    tool_info_list.append(r)

                # 构建一个 assistant 消息（包含所有 tool_calls）
                assistant_tc = [
                    {
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["parameters"], ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ]
                current_messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": assistant_tc,
                })
                # 每个结果追加一条 tool 消息
                for r in results:
                    current_messages.append({"role": "tool", "content": r["result"]})

                has_error = any("错误" in r["result"] or "失败" in r["result"] for r in results)

                if has_error and reflection_count < self.max_reflection_attempts:
                    reflection_count += 1
                    thinking_steps.append(f"反思第{reflection_count}次：工具调用失败，尝试调整策略")

                    # 取第一个出错的结果作为反思上下文
                    last_error = next((r["result"] for r in results if "错误" in r["result"] or "失败" in r["result"]), results[-1]["result"])

                    reflect_messages = current_messages + [
                        {
                            "role": "assistant",
                            "content": f"反思：工具执行失败。上一步结果：{last_error}。请分析原因并给出调整后的方案，可以调用其他工具或直接回答。",
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
                    total_completion_tokens += reflect_response.get("completion_tokens", 0)
                    total_prompt_tokens += reflect_response.get("prompt_tokens", 0)
                    total_llm_time += reflect_response.get("response_time", 0)
                    used_model = reflect_response.get("model") or used_model

                    reflect_tool_calls = self._parse_tool_calls(reflect_response)

                    if reflect_tool_calls:
                        reflect_results = self._execute_tools_parallel(reflect_tool_calls)
                        for rr in reflect_results:
                            rr["is_reflection"] = True
                            tool_info_list.append(rr)

                        reflect_assistant_tc = [
                            {
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc["parameters"], ensure_ascii=False),
                                },
                            }
                            for tc in reflect_tool_calls
                        ]
                        current_messages.append({
                            "role": "assistant",
                            "content": "",
                            "tool_calls": reflect_assistant_tc,
                        })
                        for rr in reflect_results:
                            current_messages.append({"role": "tool", "content": rr["result"]})
                    else:
                        final_response = reflect_response["content"]
                        break

                step_count += 1
            else:
                final_response = response_text
                break

        if not final_response or tool_used:
            # 将 tool 角色消息转为 user 格式（兼容不支持 tool 角色的自定义模型）
            sanitized = []
            for m in current_messages:
                if m["role"] == "tool":
                    sanitized.append({"role": "user", "content": f"[工具执行结果]\n{m['content']}"})
                elif m["role"] == "assistant" and m.get("tool_calls"):
                    sanitized.append({"role": "assistant", "content": f"[调用了工具: {m['tool_calls']}]"})
                else:
                    sanitized.append(m)

            final_response_messages = sanitized + [
                {"role": "user", "content": "请根据以上对话内容（包含工具执行结果），用自然友好的语言给出最终回答。"}
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
            user_id=user_id,
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

    def run_stream(
        self,
        messages: List[Dict],
        max_tokens: int = 2048,
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        user_id: Optional[int] = None,
        mode: str = "react",
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

        truncated_messages = truncate_messages(messages, max_tokens)
        last_user_message = messages[-1]["content"] if messages else ""
        memory_context = memory_manager.get_context(user_id, last_user_message)

        if mode == "plan_execute":
            yield from self._run_stream_plan_execute(
                messages, truncated_messages, last_user_message, memory_context,
                max_tokens, provider, model, api_key, base_url, user_id, start_time,
            )
            return

        system_prompt = self._build_system_prompt()
        if memory_context["used"]:
            system_prompt += f"\n\n## 相关记忆\n{memory_context['text']}"

        tools_for_llm = self._get_tools_for_llm()
        full_messages = [{"role": "system", "content": system_prompt}] + truncated_messages

        current_messages = full_messages.copy()
        tool_results = []
        thinking_steps = []
        reflection_count = 0
        tool_used = False
        final_response = ""
        llm_stats = {"completion_tokens": 0, "prompt_tokens": 0, "model": model}

        # ---------- 第一阶段：首次 LLM 调用 ----------
        try:
            llm_response = self._call_llm(
                current_messages,
                max_tokens,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                tools=tools_for_llm,
            )
        except LLMError as exc:
            yield {"type": "error", "content": str(exc)}
            return

        llm_stats["completion_tokens"] += llm_response["completion_tokens"]
        llm_stats["prompt_tokens"] += llm_response["prompt_tokens"]
        llm_stats["llm_time"] = llm_stats.get("llm_time", 0) + llm_response.get("response_time", 0)
        used_model = llm_response.get("model") or model

        tool_calls = self._parse_tool_calls(llm_response)

        # 自动匹配
        if not tool_calls:
            guessed_tool = self._guess_tool_for_query(last_user_message)
            if guessed_tool:
                thinking_steps.append(f"模型未调用工具，自动匹配到 {guessed_tool} 工具")
                yield {"type": "thinking", "content": thinking_steps[-1]}
                if guessed_tool == "calculator":
                    match = re.search(r'[\d+\-*/().%\s]+', last_user_message)
                    expression = match.group(0).strip() if match else last_user_message
                    tool_calls = [{"name": "calculator", "parameters": {"expression": expression}}]
                elif guessed_tool == "weather":
                    cities = ["北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", "重庆", "天津", "苏州", "郑州", "长沙", "东莞"]
                    city = next((c for c in cities if c in last_user_message), "北京")
                    tool_calls = [{"name": "weather", "parameters": {"city": city}}]
                elif guessed_tool == "datetime":
                    tool_calls = [{"name": "datetime", "parameters": {"action": "now"}}]
                elif guessed_tool == "search":
                    tool_calls = [{"name": "search", "parameters": {"query": last_user_message}}]
                elif guessed_tool == "file":
                    tool_calls = [{"name": "file", "parameters": {"action": "read", "file_path": last_user_message}}]

        # ---------- 第二阶段：并行执行工具 ----------
        if tool_calls:
            # yield 所有工具调用事件
            for tc in tool_calls:
                yield {"type": "tool_call", "tool_name": tc["name"], "parameters": tc["parameters"]}

            # 并行执行
            results = self._execute_tools_parallel(tool_calls)
            tool_used = True

            for r in results:
                tool_results.append(r)
                yield {"type": "tool_result", "tool_name": r["tool_name"], "result": r["result"]}

            # 构建 assistant 消息（包含所有 tool_calls）
            assistant_tc = [
                {
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["parameters"], ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ]
            current_messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": assistant_tc,
            })
            for r in results:
                current_messages.append({"role": "tool", "content": r["result"]})

            has_error = any("错误" in r["result"] or "失败" in r["result"] for r in results)

            # 反思
            if has_error and reflection_count < self.max_reflection_attempts:
                reflection_count += 1
                thinking_steps.append(f"反思第{reflection_count}次：工具调用失败，尝试调整策略")
                yield {"type": "thinking", "content": thinking_steps[-1]}

                last_error = next((r["result"] for r in results if "错误" in r["result"] or "失败" in r["result"]), results[-1]["result"])

                reflect_messages = current_messages + [{
                    "role": "assistant",
                    "content": f"反思：工具执行失败。上一步结果：{last_error}。请分析原因并给出调整后的方案，可以调用其他工具或直接回答。",
                }]

                try:
                    reflect_response = self._call_llm(
                        reflect_messages,
                        max_tokens=500,
                        provider=provider,
                        model=model,
                        api_key=api_key,
                        base_url=base_url,
                        tools=tools_for_llm,
                    )
                except LLMError as exc:
                    yield {"type": "error", "content": str(exc)}
                    return

                llm_stats["completion_tokens"] += reflect_response["completion_tokens"]
                llm_stats["prompt_tokens"] += reflect_response["prompt_tokens"]
                llm_stats["llm_time"] = llm_stats.get("llm_time", 0) + reflect_response.get("response_time", 0)
                used_model = reflect_response.get("model") or used_model

                reflect_tool_calls = self._parse_tool_calls(reflect_response)
                if reflect_tool_calls:
                    for rtc in reflect_tool_calls:
                        yield {"type": "tool_call", "tool_name": rtc["name"], "parameters": rtc["parameters"], "is_reflection": True}

                    reflect_results = self._execute_tools_parallel(reflect_tool_calls)
                    for rr in reflect_results:
                        rr["is_reflection"] = True
                        tool_results.append(rr)
                        yield {"type": "tool_result", "tool_name": rr["tool_name"], "result": rr["result"], "is_reflection": True}

                    reflect_assistant_tc = [
                        {
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["parameters"], ensure_ascii=False),
                            },
                        }
                        for tc in reflect_tool_calls
                    ]
                    current_messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": reflect_assistant_tc,
                    })
                    for rr in reflect_results:
                        current_messages.append({"role": "tool", "content": rr["result"]})
                else:
                    final_response = reflect_response["content"]

        # ---------- 第三阶段：最终总结（流式） ----------
        if not final_response or tool_used:
            yield {"type": "summary_start"}

            sanitized = []
            for m in current_messages:
                if m["role"] == "tool":
                    sanitized.append({"role": "user", "content": f"[工具执行结果]\n{m['content']}"})
                elif m["role"] == "assistant" and m.get("tool_calls"):
                    sanitized.append({"role": "assistant", "content": f"[调用了工具: {m['tool_calls']}]"})
                else:
                    sanitized.append(m)

            final_messages = sanitized + [
                {"role": "user", "content": "请根据以上对话内容（包含工具执行结果），用自然友好的语言给出最终回答。"}
            ]

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
        self._update_memories(
            messages,
            final_response,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            user_id=user_id,
        )

        elapsed_time = time.time() - start_time
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
            "total_tokens": llm_stats["completion_tokens"] + llm_stats["prompt_tokens"],
            "tokens_per_second": tokens_per_second,
            "response_time": round(elapsed_time, 2),
            "provider": provider,
            "model": llm_stats.get("model") or model,
        }

    def _run_plan_execute(
        self,
        messages: List[Dict],
        truncated_messages: List[Dict],
        last_user_message: str,
        memory_context: Dict,
        max_tokens: int,
        provider: str,
        model: Optional[str],
        api_key: Optional[str],
        base_url: Optional[str],
        user_id: Optional[int],
        start_time: float,
    ) -> Dict[str, Any]:
        """Plan-and-Execute 模式的完整执行流程。"""
        tools_for_llm = self._get_tools_for_llm()
        total_completion_tokens = 0
        total_prompt_tokens = 0
        total_llm_time = 0
        used_model = model
        thinking_steps = []
        plan_steps = []
        tool_results = []
        tool_used = False

        # ---- 阶段 1: 生成计划 ----
        plan_result = self._generate_plan(
            last_user_message,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            memory_context=memory_context,
        )

        if plan_result.get("llm_response"):
            resp = plan_result["llm_response"]
            total_completion_tokens += resp.get("completion_tokens", 0)
            total_prompt_tokens += resp.get("prompt_tokens", 0)
            total_llm_time += resp.get("response_time", 0)
            used_model = resp.get("model") or used_model

        if not plan_result.get("need_plan"):
            direct_response = plan_result.get("direct_response", "")
            if direct_response:
                return {
                    "content": direct_response,
                    "tool_used": False,
                    "tool_info": None,
                    "thinking": thinking_steps,
                    "reflection_count": 0,
                    "memory_saved": False,
                    "memory_context": memory_context,
                    "context_tokens": calculate_messages_tokens(truncated_messages),
                    "original_messages_count": len(messages),
                    "truncated_messages_count": len(truncated_messages),
                    "completion_tokens": total_completion_tokens,
                    "prompt_tokens": total_prompt_tokens,
                    "total_tokens": total_completion_tokens + total_prompt_tokens,
                    "tokens_per_second": 0,
                    "response_time": round(time.time() - start_time, 2),
                    "provider": provider,
                    "model": used_model,
                }
            # fallback: 退回到普通 ReAct 模式
            return self.run(
                messages, max_tokens, provider, model, api_key, base_url, user_id, mode="react"
            )

        plan = plan_result["plan"]
        total_steps = len(plan)
        for step in plan:
            plan_steps.append(f"步骤{step['step']}: {step['description']}")

        # ---- 阶段 2: 逐步执行 ----
        step_results = []
        for i, step in enumerate(plan):
            step_num = step["step"]
            step_desc = step["description"]

            thinking_steps.append(f"正在执行步骤 {step_num}/{total_steps}: {step_desc}")

            step_result = self._execute_step(
                step_desc=step_desc,
                step_index=step_num,
                total_steps=total_steps,
                all_results=step_results,
                tools_for_llm=tools_for_llm,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                max_tokens=max_tokens,
            )

            resp = step_result.get("llm_response", {})
            total_completion_tokens += resp.get("completion_tokens", 0)
            total_prompt_tokens += resp.get("prompt_tokens", 0)
            total_llm_time += resp.get("response_time", 0)
            used_model = resp.get("model") or used_model

            if step_result.get("tool_name"):
                tool_used = True
                tool_results.append({
                    "tool_name": step_result["tool_name"],
                    "parameters": step_result["parameters"],
                    "result": step_result["tool_result"],
                    "step": step_num,
                })

            step_results.append({
                "step": step_num,
                "description": step_desc,
                "tool_name": step_result.get("tool_name"),
                "tool_result": step_result.get("tool_result"),
                "answer": step_result.get("answer"),
            })

            if step_result.get("tool_name"):
                thinking_steps.append(
                    f"步骤{step_num} → 调用了 {step_result['tool_name']}: {step_result['tool_result'][:100]}"
                )
            elif step_result.get("answer"):
                thinking_steps.append(f"步骤{step_num} → {step_result['answer'][:100]}")

        # ---- 阶段 3: 汇总生成最终回答 ----
        step_summary = "\n".join(
            f"步骤{r['step']} ({r['description']}): "
            + (f"工具结果: {r['tool_result']}" if r.get('tool_result') else f"回答: {r['answer']}")
            for r in step_results
        )

        sanitized = [{"role": "system", "content": "你是一个 AI 助手。请根据以下逐步执行的结果，用自然友好的语言给用户一个完整、清晰的回答。"}]
        sanitized += truncated_messages
        sanitized.append({"role": "user", "content": f"## 执行结果\n{step_summary}\n\n请根据以上结果，回答用户的原始问题。"})

        final_response = self._call_llm(
            sanitized,
            max_tokens=max_tokens,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        total_completion_tokens += final_response.get("completion_tokens", 0)
        total_prompt_tokens += final_response.get("prompt_tokens", 0)
        total_llm_time += final_response.get("response_time", 0)
        used_model = final_response.get("model") or used_model
        final_answer = final_response.get("content", "")

        # ---- 记忆更新 ----
        self._update_memories(
            messages, final_answer,
            provider=provider, model=model, api_key=api_key, base_url=base_url, user_id=user_id,
        )

        elapsed_time = time.time() - start_time
        tokens_per_second = round(total_completion_tokens / total_llm_time, 2) if total_llm_time > 0 else 0

        return {
            "content": final_answer,
            "tool_used": tool_used,
            "tool_info": tool_results if tool_results else None,
            "thinking": thinking_steps,
            "plan": plan_steps,
            "reflection_count": 0,
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

    def _run_stream_plan_execute(
        self,
        messages: List[Dict],
        truncated_messages: List[Dict],
        last_user_message: str,
        memory_context: Dict,
        max_tokens: int,
        provider: str,
        model: Optional[str],
        api_key: Optional[str],
        base_url: Optional[str],
        user_id: Optional[int],
        start_time: float,
    ) -> Generator[Dict[str, Any], None, None]:
        """流式 Plan-and-Execute 执行流程。"""
        tools_for_llm = self._get_tools_for_llm()
        llm_stats = {"completion_tokens": 0, "prompt_tokens": 0, "model": model}
        thinking_steps = []
        tool_results = []
        step_results = []
        tool_used = False

        # ---- 阶段 1: 生成计划 ----
        plan_result = self._generate_plan(
            last_user_message,
            provider=provider, model=model, api_key=api_key, base_url=base_url,
            memory_context=memory_context,
        )
        if plan_result.get("llm_response"):
            resp = plan_result["llm_response"]
            llm_stats["completion_tokens"] += resp.get("completion_tokens", 0)
            llm_stats["prompt_tokens"] += resp.get("prompt_tokens", 0)
            llm_stats["llm_time"] = llm_stats.get("llm_time", 0) + resp.get("response_time", 0)
            used_model = resp.get("model") or model

        if not plan_result.get("need_plan"):
            direct_response = plan_result.get("direct_response", "")
            if direct_response:
                yield {"type": "token", "content": direct_response}
                yield self._build_done_event(
                    direct_response, False, None, thinking_steps, tool_results,
                    llm_stats, memory_context, truncated_messages, messages, start_time,
                    provider, model,
                )
                return
            # fallback 到普通 ReAct
            yield from self.run_stream(
                messages, max_tokens, provider, model, api_key, base_url, user_id, mode="react",
            )
            return

        plan = plan_result["plan"]
        plan_steps = [f"步骤{s['step']}: {s['description']}" for s in plan]
        yield {"type": "plan", "plan": plan, "steps": plan_steps}

        # ---- 阶段 2: 逐步执行 ----
        for i, step in enumerate(plan):
            step_num = step["step"]
            step_desc = step["description"]
            # yield {"type": "thinking", "content": f"▶️ 正在执行步骤 {step_num}/{len(plan)}: {step_desc}"}

            step_result = self._execute_step(
                step_desc=step_desc, step_index=step_num, total_steps=len(plan),
                all_results=step_results, tools_for_llm=tools_for_llm,
                provider=provider, model=model, api_key=api_key, base_url=base_url,
                max_tokens=max_tokens,
            )

            resp = step_result.get("llm_response", {})
            llm_stats["completion_tokens"] += resp.get("completion_tokens", 0)
            llm_stats["prompt_tokens"] += resp.get("prompt_tokens", 0)
            llm_stats["llm_time"] = llm_stats.get("llm_time", 0) + resp.get("response_time", 0)
            used_model = resp.get("model") or used_model

            if step_result.get("tool_name"):
                tool_used = True
                yield {"type": "tool_call", "tool_name": step_result["tool_name"], "parameters": step_result["parameters"], "step": step_num}
                tool_results.append({
                    "tool_name": step_result["tool_name"],
                    "parameters": step_result["parameters"],
                    "result": step_result["tool_result"],
                    "step": step_num,
                })
                yield {"type": "tool_result", "tool_name": step_result["tool_name"], "result": step_result["tool_result"], "step": step_num}

            step_results.append({
                "step": step_num, "description": step_desc,
                "tool_name": step_result.get("tool_name"),
                "tool_result": step_result.get("tool_result"),
                "answer": step_result.get("answer"),
            })

            if step_result.get("tool_name"):
                thinking_steps.append(f"步骤{step_num} → 调用了 {step_result['tool_name']}")
            elif step_result.get("answer"):
                thinking_steps.append(f"步骤{step_num} → 完成")

        # ---- 阶段 3: 汇总生成最终回答 ----
        yield {"type": "summary_start"}

        step_summary = "\n".join(
            f"步骤{r['step']} ({r['description']}): "
            + (f"工具结果: {r['tool_result']}" if r.get('tool_result') else f"回答: {r['answer']}")
            for r in step_results
        )

        final_messages = [
            {"role": "system", "content": "你是一个 AI 助手。请根据以下逐步执行的结果，用自然友好的语言给用户一个完整、清晰的回答。"}
        ] + truncated_messages + [
            {"role": "user", "content": f"## 执行结果\n{step_summary}\n\n请根据以上结果，回答用户的原始问题。"}
        ]

        final_response = ""
        try:
            for event in llm_client.chat_completion_stream(
                messages=final_messages,
                provider_id=provider, model=used_model, max_tokens=max_tokens,
                api_key=api_key, base_url=base_url,
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

        self._update_memories(
            messages, final_response,
            provider=provider, model=model, api_key=api_key, base_url=base_url, user_id=user_id,
        )

        yield self._build_done_event(
            final_response, tool_used, tool_results if tool_results else None,
            thinking_steps, tool_results, llm_stats, memory_context,
            truncated_messages, messages, start_time, provider, model,
        )

    @staticmethod
    def _build_done_event(
        final_response, tool_used, tool_info, thinking_steps, tool_results,
        llm_stats, memory_context, truncated_messages, messages,
        start_time, provider, model,
    ) -> Dict:
        elapsed_time = time.time() - start_time
        llm_time = llm_stats.get("llm_time", 0)
        tokens_per_second = round(llm_stats["completion_tokens"] / llm_time, 2) if llm_time > 0 else 0
        return {
            "type": "done",
            "content": final_response,
            "tool_used": tool_used,
            "tool_info": tool_info,
            "thinking": thinking_steps,
            "reflection_count": 0,
            "completion_tokens": llm_stats["completion_tokens"],
            "prompt_tokens": llm_stats["prompt_tokens"],
            "total_tokens": llm_stats["completion_tokens"] + llm_stats["prompt_tokens"],
            "tokens_per_second": tokens_per_second,
            "response_time": round(elapsed_time, 2),
            "provider": provider,
            "model": llm_stats.get("model") or model,
        }

    def _update_memories(
        self,
        messages: List[Dict],
        response: str,
        provider: str = "llama_cpp",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> None:
        # 短期记忆：每 N 轮生成对话总结
        if len(messages) % self.summary_frequency == 0:
            summary = self._generate_summary(
                messages,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
            if summary:
                memory_manager.add_short_term_summary(user_id, messages, summary)

        # 长期记忆：仅当重要性 >= 6 时才写入（带自动去重）
        importance_info = self._extract_important_info(
            messages[-1]["content"],
            response,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        print(f"\n📝 [长期记忆] 重要性评估: has_important={importance_info.get('has_important')}, importance={importance_info.get('importance')}, content={importance_info.get('content')}", flush=True)
        if importance_info and importance_info.get("importance", 0) >= 6:
            print(f"✅ [长期记忆] 已存储 (重要性 {importance_info['importance']} ≥ 6): {importance_info['content']}", flush=True)
            memory_manager.add_long_term_memory(
                user_id,
                importance_info["content"],
                category="knowledge",
            )
        else:
            print(f"⏭️ [长期记忆] 跳过存储 (重要性 < 6 或无重要信息)", flush=True)

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
    ) -> Dict:
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
            result = self._call_llm(
                extract_messages,
                max_tokens=200,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
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
