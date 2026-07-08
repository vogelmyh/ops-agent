from langgraph.types import interrupt

from app.graph.state import AgentState


def review_runbook_node(state: AgentState) -> dict:
    payload = {
        "message": "请审阅以下 runbook 草稿，确认是否入库。",
        "runbook_draft": state.get("runbook_draft", ""),
        "service": state.get("service"),
    }
    decision = interrupt(payload)
    approved = bool(decision.get("approved", False))
    return {
        "runbook_approved": approved,
        "status": "runbook_approved" if approved else "runbook_rejected",
    }
