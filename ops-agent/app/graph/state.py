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

    # eval_runbook
    collected_data: dict[str, Any]
    symptom_query: str
    novel_scenario: bool
    novel_reason: str | None
    relevant_runbook: str | None
    selected_runbook_id: str | None
    coverage_confidence: float | None
    runbook_candidates: list[dict[str, Any]]
    runbook_eval_reasoning: str

    # eval_diagnosis
    needs_human_review: bool
    diagnosis_eval_reasoning: str

    # eval_remediation (post write_tools)
    incident_resolved: bool
    remediation_attempt: int
    remediation_eval_reasoning: str
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
