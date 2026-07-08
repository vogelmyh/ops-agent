"""Wire investigation + escalation subgraph into the main StateGraph.

Usage (when re-enabling):
    from app.graph.extensions.investigation import attach_investigation
    attach_investigation(graph)
"""

from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from app.graph.extensions.investigation.escalate import escalate_node
from app.graph.extensions.investigation.nodes import (
    investigate_agent_node,
    investigate_finalize_node,
    investigate_human_node,
)
from app.graph.state import AgentState
from app.schemas import EscalationChoice
from app.tools import READ_TOOLS
from app.tools.policy import pending_tool_calls

investigate_tools_node = ToolNode(READ_TOOLS)


def route_after_escalate(state: AgentState) -> str:
    choice = (state.get("escalation") or {}).get("choice")
    if choice == EscalationChoice.START_INVESTIGATION.value:
        return "investigate_agent"
    if (
        choice == EscalationChoice.APPROVE_ACTIONS.value
        and pending_tool_calls(state.get("messages", []))
    ):
        return "approve"
    return "summarize"


def route_after_investigate_agent(state: AgentState) -> str:
    messages = state.get("messages", [])
    if messages and getattr(messages[-1], "tool_calls", None):
        return "investigate_tools"
    return "investigate_human"


def route_after_investigate_human(state: AgentState) -> str:
    if state.get("investigation_done"):
        return "investigate_finalize"
    return "investigate_agent"


def attach_investigation(graph: StateGraph) -> None:
    """Register investigation nodes and edges. Call after main nodes are added."""
    graph.add_node("escalate", escalate_node)
    graph.add_node("investigate_agent", investigate_agent_node)
    graph.add_node("investigate_tools", investigate_tools_node)
    graph.add_node("investigate_human", investigate_human_node)
    graph.add_node("investigate_finalize", investigate_finalize_node)

    graph.add_conditional_edges(
        "escalate",
        route_after_escalate,
        {
            "investigate_agent": "investigate_agent",
            "approve": "approve",
            "summarize": "summarize",
        },
    )
    graph.add_conditional_edges(
        "investigate_agent",
        route_after_investigate_agent,
        {
            "investigate_tools": "investigate_tools",
            "investigate_human": "investigate_human",
        },
    )
    graph.add_edge("investigate_tools", "investigate_agent")
    graph.add_conditional_edges(
        "investigate_human",
        route_after_investigate_human,
        {
            "investigate_finalize": "investigate_finalize",
            "investigate_agent": "investigate_agent",
        },
    )
    graph.add_edge("investigate_finalize", "decide")
