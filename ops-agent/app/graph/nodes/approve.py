from langgraph.types import interrupt

from app.graph.state import AgentState
from app.tools.policy import enrich_tool_calls, pending_tool_calls


def approve_node(state: AgentState) -> dict:
    if not state.get("needs_approval"):
        return {"approval": {"approved": True, "auto": True}, "status": "approved"}

    tool_calls = enrich_tool_calls(pending_tool_calls(state.get("messages", [])))
    payload = {
        "message": "诊断评估或高风险操作需要人工审批",
        "pending_tool_calls": tool_calls,
        "runbook_available": state.get("runbook_available", False),
        "confidence_sufficient": state.get("confidence_sufficient"),
        "confidence_gate_reason": state.get("confidence_gate_reason"),
    }
    decision = interrupt(payload)
    approved = bool(decision.get("approved", False))
    return {
        "approval": decision,
        "status": "approved" if approved else "rejected",
    }
