from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from app.schemas import Evidence, IncidentInput


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    incident: IncidentInput
    service: str
    findings: list[dict[str, Any]]
    evidence: list[Evidence]
    approval: dict[str, Any] | None
    summary: str
    root_cause: str
    needs_approval: bool
    status: str

    # decide
    decision_class: str
    decide_outcome: str
    escalation_hint: str | None
    recommendations: list[str]
    knowledge_gaps: list[str]

    # retrieve_runbooks + diagnose coverage phase
    collected_data: dict[str, Any]
    symptom_query: str
    novel_scenario: bool
    novel_reason: str | None
    relevant_runbook: str | None
    selected_runbook_id: str | None
    runbook_match_rubrics: list[dict[str, Any]]
    match_gate_reason: str
    runbook_candidates: list[dict[str, Any]]
    # diagnose
    confidence_rubric: dict[str, Any]
    confidence_gate_reason: str
    confidence_sufficient: bool

    # verify_remediation (post write_tools)
    incident_resolved: bool
    remediation_attempt: int
    remediation_verify_reasoning: str
    remediation_history: list[dict[str, Any]]

    # INVESTIGATE_EXTENSION: fields used by extensions/investigation when re-attached
    escalation: dict[str, Any] | None
    investigation_done: bool
    investigation_summary: str | None

    # runbook write-back loop
    runbook_notes: str | None
    runbook_draft: str | None
    runbook_approved: bool | None
    runbook_saved_path: str | None
