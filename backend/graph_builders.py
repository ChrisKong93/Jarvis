from langgraph.graph import END, StateGraph

from .agent_types import AgentState


def build_chat_graph(agent) -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("prepare_state", agent._node_prepare_chat_state)
    builder.add_node("call_llm", agent._node_chat_call_llm)
    builder.add_node("update_memory", agent._node_update_memory)

    builder.set_entry_point("prepare_state")
    builder.add_edge("prepare_state", "call_llm")
    builder.add_edge("call_llm", "update_memory")
    builder.add_edge("update_memory", END)
    return builder.compile()


def build_react_graph(agent) -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("prepare_state", agent._node_prepare_state)
    builder.add_node("call_llm", agent._node_call_llm)
    builder.add_node("execute_tools", agent._node_execute_tools)
    builder.add_node("reflect", agent._node_reflect)
    builder.add_node("final", agent._node_final)
    builder.add_node("update_memory", agent._node_update_memory)

    builder.set_entry_point("prepare_state")
    builder.add_edge("prepare_state", "call_llm")
    builder.add_edge("call_llm", "execute_tools")
    builder.add_conditional_edges("execute_tools", agent._edge_react_next, {
        "reflect": "reflect",
        "final": "final",
    })
    builder.add_edge("reflect", "call_llm")
    builder.add_edge("final", "update_memory")
    builder.add_edge("update_memory", END)

    return builder.compile()


def build_plan_execute_graph(agent) -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("prepare_state", agent._node_prepare_state)
    builder.add_node("planner", agent._node_plan)
    builder.add_node("execute_group", agent._node_execute_group)
    builder.add_node("summarize", agent._node_summarize)
    builder.add_node("update_memory", agent._node_update_memory)

    builder.set_entry_point("prepare_state")
    builder.add_edge("prepare_state", "planner")
    builder.add_conditional_edges("planner", agent._edge_after_plan, {
        "memory": "update_memory",
        "execute": "execute_group",
    })
    builder.add_conditional_edges("execute_group", agent._edge_plan_next, {
        "execute_group": "execute_group",
        "summarize": "summarize",
    })
    builder.add_edge("summarize", "update_memory")
    builder.add_edge("update_memory", END)

    return builder.compile()
