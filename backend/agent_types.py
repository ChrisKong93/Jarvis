from typing import Any, Dict, List, TypedDict


# ---------------------------------------------------------------------------
# Unified AgentState — 所有模式共用
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: List[Dict]
    final_response: str
    llm_stats: Dict
    provider_config: Dict
    last_user_message: str
    tools_for_llm: List[Dict]

    # ReAct 状态
    tool_results: List[Dict]
    thinking_steps: List[str]
    memory_context: Dict
    tool_used: bool
    reflection_count: int
    step_count: int
    max_thinking_steps: int
    max_reflection_attempts: int
    llm_response: Dict
    tool_calls: List[Dict]
    tool_results_batch: List[Dict]
    has_error: bool

    # Plan & Execute 状态
    plan: List[Dict]
    groups: List[List[Dict]]
    current_group_index: int
    step_results: List[Dict]
    total_steps: int
    plan_steps: List[str]
