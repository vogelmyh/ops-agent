from langgraph.types import interrupt

from app.graph.state import AgentState


def request_runbook_notes_node(state: AgentState) -> dict:
    payload = {
        "message": (
            "本次故障为新场景（知识库无覆盖）。请用口语描述你的处置过程，"
            "无需格式，Agent 将据此生成 runbook 草稿。"
        ),
        "service": state.get("service"),
        "root_cause": state.get("root_cause", ""),
        "match_gate_reason": state.get("match_gate_reason", ""),
    }
    decision = interrupt(payload)
    notes = str(decision.get("notes", "")).strip()
    return {
        "runbook_notes": notes,
        "status": "awaiting_runbook_draft",
    }
