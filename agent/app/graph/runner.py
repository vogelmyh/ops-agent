import uuid
from collections.abc import Callable
from typing import Any

from langgraph.types import Command

from app.graph.builder import build_graph
from app.schemas import DiagnoseResponse, IncidentInput
from app.tools.policy import enrich_tool_calls, pending_tool_calls, tool_execution_results


def _graph():
    return build_graph()


def _pending_interrupt(snapshot) -> tuple[bool, str | None]:
    if not snapshot or not snapshot.next:
        return False, None
    return True, snapshot.next[0]


def _state_from_snapshot(snapshot) -> dict[str, Any]:
    if snapshot and snapshot.values:
        return dict(snapshot.values)
    return {}


def _status_from_pending(node: str | None, result: dict) -> str:
    mapping = {
        "approve": "awaiting_approval",
        "request_runbook_notes": "awaiting_runbook_notes",
        "review_runbook": "awaiting_runbook_review",
        # INVESTIGATE_EXTENSION: "escalate": "awaiting_escalation", "investigate_human": "awaiting_investigation"
    }
    if node in mapping:
        return mapping[node]
    return result.get("status", "completed")


def _to_response(thread_id: str, result: dict, pending_node: str | None = None) -> DiagnoseResponse:
    messages = result.get("messages", [])
    return DiagnoseResponse(
        thread_id=thread_id,
        summary=result.get("summary", ""),
        root_cause=result.get("root_cause", ""),
        evidence=result.get("evidence", []),
        pending_tool_calls=enrich_tool_calls(pending_tool_calls(messages)),
        execution_results=tool_execution_results(messages),
        needs_approval=result.get("needs_approval", False),
        status=_status_from_pending(pending_node, result),
        runbook_available=result.get("runbook_available", False),
        runbook_draft=result.get("runbook_draft"),
        decision_class=result.get("decision_class"),
        decide_outcome=result.get("decide_outcome"),
        escalation_hint=result.get("escalation_hint"),
        recommendations=result.get("recommendations", []),
        knowledge_gaps=result.get("knowledge_gaps", []),
        incident_resolved=result.get("incident_resolved"),
        remediation_attempt=result.get("remediation_attempt", 0),
        symptom_query=result.get("symptom_query"),
        runbook_unavailable_reason=result.get("runbook_unavailable_reason"),
        selected_runbook_id=result.get("selected_runbook_id"),
        match_gate_reason=result.get("match_gate_reason"),
        confidence_sufficient=result.get("confidence_sufficient"),
        confidence_gate_reason=result.get("confidence_gate_reason"),
    )


def _stream_graph(
    input_payload: dict[str, Any] | Command,
    config: dict[str, Any],
    *,
    on_node_update: Callable[[str, dict[str, Any]], None] | None = None,
) -> list[str]:
    graph = _graph()
    visited: list[str] = []
    for chunk in graph.stream(input_payload, config=config, stream_mode="updates"):
        for node_name, update in chunk.items():
            visited.append(node_name)
            if on_node_update is not None:
                on_node_update(node_name, dict(update or {}))
    return visited


def stream_diagnosis(
    incident: IncidentInput,
    *,
    on_node_update: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[str, DiagnoseResponse, dict[str, Any], list[str]]:
    """Run diagnosis with per-node updates (demo narration). invoke() path unchanged."""
    thread_id = incident.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    visited = _stream_graph(
        {"incident": incident, "messages": []},
        config,
        on_node_update=on_node_update,
    )
    snapshot = _graph().get_state(config)
    pending, pending_node = _pending_interrupt(snapshot)
    state = _state_from_snapshot(snapshot)
    response = _to_response(thread_id, state, pending_node if pending else None)
    meta = {
        "pending_interrupt": pending,
        "pending_node": pending_node,
        "visited_nodes": visited,
    }
    return thread_id, response, meta, visited


def stream_resume(
    thread_id: str,
    payload: dict[str, Any],
    *,
    on_node_update: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[DiagnoseResponse, dict[str, Any], list[str]]:
    config = {"configurable": {"thread_id": thread_id}}
    visited = _stream_graph(Command(resume=payload), config, on_node_update=on_node_update)
    snapshot = _graph().get_state(config)
    pending, pending_node = _pending_interrupt(snapshot)
    state = _state_from_snapshot(snapshot)
    response = _to_response(thread_id, state, pending_node if pending else None)
    meta = {
        "pending_interrupt": pending,
        "pending_node": pending_node,
        "visited_nodes": visited,
    }
    return response, meta, visited


def start_diagnosis(incident: IncidentInput) -> tuple[str, DiagnoseResponse, dict[str, Any]]:
    thread_id = incident.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    graph = _graph()
    result = graph.invoke({"incident": incident, "messages": []}, config=config)
    snapshot = graph.get_state(config)
    pending, pending_node = _pending_interrupt(snapshot)
    state = _state_from_snapshot(snapshot) or result
    response = _to_response(thread_id, state, pending_node if pending else None)
    return thread_id, response, {
        "pending_interrupt": pending,
        "pending_node": pending_node,
    }


def resume_graph(thread_id: str, payload: dict[str, Any]) -> tuple[DiagnoseResponse, dict[str, Any]]:
    config = {"configurable": {"thread_id": thread_id}}
    graph = _graph()
    result = graph.invoke(Command(resume=payload), config=config)
    snapshot = graph.get_state(config)
    pending, pending_node = _pending_interrupt(snapshot)
    state = _state_from_snapshot(snapshot) or result
    response = _to_response(thread_id, state, pending_node if pending else None)
    return response, {
        "pending_interrupt": pending,
        "pending_node": pending_node,
    }


def resume_approval(thread_id: str, approved: bool, comment: str | None = None) -> DiagnoseResponse:
    response, _ = resume_graph(thread_id, {"approved": approved, "comment": comment})
    return response


def resume_runbook_notes(thread_id: str, notes: str) -> DiagnoseResponse:
    response, _ = resume_graph(thread_id, {"notes": notes})
    return response


def resume_runbook_review(thread_id: str, approved: bool, comment: str | None = None) -> DiagnoseResponse:
    response, _ = resume_graph(thread_id, {"approved": approved, "comment": comment})
    return response
