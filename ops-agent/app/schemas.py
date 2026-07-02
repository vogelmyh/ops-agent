from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DecisionClass(str, Enum):
    EXECUTE = "execute"
    APPROVE = "approve"
    UNCERTAIN = "uncertain"
    OUT_OF_SCOPE = "out_of_scope"
    # Legacy aliases (deprecated; kept for backward-compatible deserialization)
    INVESTIGATE = "investigate"
    RECOMMEND_ONLY = "recommend_only"


class EscalationChoice(str, Enum):
    APPROVE_ACTIONS = "approve_actions"
    START_INVESTIGATION = "start_investigation"
    MANUAL_RESOLVED = "manual_resolved"
    ABORT = "abort"


class StreamStatus(str, Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DELETED = "DELETED"


class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    message: str
    service: str
    stream: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LogQueryRequest(BaseModel):
    service: str
    keyword: str | None = None
    limit: int = 50


class LogQueryResult(BaseModel):
    query: LogQueryRequest
    total: int
    entries: list[LogEntry]


class PodStatus(BaseModel):
    name: str
    ready: bool
    restarts: int
    phase: str
    image: str
    reason: str | None = None


class ServiceStatus(BaseModel):
    service: str
    healthy: bool
    replicas_ready: int
    replicas_desired: int
    pods: list[PodStatus]
    message: str | None = None


class StreamState(BaseModel):
    project: str
    stream: str
    status: StreamStatus
    topic: str
    last_ingest_at: datetime | None = None


class MetricPoint(BaseModel):
    timestamp: datetime
    value: float


class MetricSeries(BaseModel):
    service: str
    metric: str
    unit: str
    points: list[MetricPoint]


class OperationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class OperationResult(BaseModel):
    operation_id: str
    service: str
    action: str
    status: OperationStatus
    message: str
    started_at: datetime
    finished_at: datetime | None = None


class K8sEvent(BaseModel):
    """Infrastructure-layer event from the K8s control plane (kubelet/scheduler/controller)."""

    timestamp: datetime
    type: str  # "Normal" | "Warning"
    reason: str  # e.g. "BackOff", "Failed", "Killing", "Pulled"
    involved_object: str  # e.g. "pod/ecomm-order-0", "deployment/ecomm-order"
    message: str
    service: str


class K8sEventResult(BaseModel):
    service: str
    total: int
    events: list[K8sEvent]


class RunbookChunk(BaseModel):
    doc_id: str
    title: str
    content: str
    score: float


class Evidence(BaseModel):
    source: str
    snippet: str
    ref: str


class IncidentInput(BaseModel):
    service: str
    description: str
    severity: str = "medium"
    thread_id: str | None = None


class DiagnoseRequest(BaseModel):
    incident: IncidentInput


class ApproveRequest(BaseModel):
    thread_id: str
    approved: bool
    comment: str | None = None


class DiagnoseResponse(BaseModel):
    thread_id: str
    summary: str
    root_cause: str
    evidence: list[Evidence]
    pending_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    execution_results: list[dict[str, Any]] = Field(default_factory=list)
    needs_approval: bool
    status: str
    novel_scenario: bool = False
    runbook_draft: str | None = None
    decision_class: str | None = None
    decide_outcome: str | None = None
    escalation_hint: str | None = None
    recommendations: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    incident_resolved: bool | None = None
    remediation_attempt: int = 0
    # eval_runbook / RAG (optional — populated after eval_runbook node)
    symptom_query: str | None = None
    novel_reason: str | None = None
    selected_runbook_id: str | None = None
    match_score: float | None = None
    runbook_eval_reasoning: str | None = None
    diagnosis_confidence: float | None = None
    confidence_sufficient: bool | None = None
    needs_human_review: bool | None = None


class EscalationRequest(BaseModel):
    thread_id: str
    choice: EscalationChoice
    comment: str | None = None


class InvestigationMessageRequest(BaseModel):
    thread_id: str
    message: str = ""
    done: bool = False


class RunbookNotesRequest(BaseModel):
    thread_id: str
    notes: str


class RunbookReviewRequest(BaseModel):
    thread_id: str
    approved: bool
    comment: str | None = None
