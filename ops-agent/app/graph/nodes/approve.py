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
        "needs_human_review": state.get("needs_human_review", False),
        "diagnosis_eval_reasoning": state.get("diagnosis_eval_reasoning", ""),
    }
    decision = interrupt(payload)
    approved = bool(decision.get("approved", False))
    return {
        "approval": decision,
        "status": "approved" if approved else "rejected",
    }
