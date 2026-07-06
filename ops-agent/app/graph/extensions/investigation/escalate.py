from langgraph.types import interrupt

from app.graph.state import AgentState
from app.tools.policy import enrich_tool_calls, pending_tool_calls


def escalate_node(state: AgentState) -> dict:
    """Multi-choice HITL when decide cannot proceed automatically."""
    tool_calls = enrich_tool_calls(pending_tool_calls(state.get("messages", [])))
    payload = {
        "message": "No automatic remediation path; choose next step.",
        "choices": [
            "approve_actions",
            "start_investigation",
            "manual_resolved",
            "abort",
        ],
        "root_cause": state.get("root_cause", ""),
        "recommendations": state.get("recommendations", []),
        "knowledge_gaps": state.get("knowledge_gaps", []),
        "pending_tool_calls": tool_calls,
        "runbook_available": state.get("runbook_available", False),
    }
    decision = interrupt(payload)
    return {
        "escalation": decision,
        "status": "awaiting_escalation",
    }
