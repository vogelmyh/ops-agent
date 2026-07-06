"""RCA and confidence CoT categorical rubric prompts, schemas, and mock oracles."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.graph.categorical_rubric import DimensionAssessment, coerce_dimension_assessment
from app.graph.diagnosis_confidence_policy import CONFIDENCE_DIMS

EvidenceSource = Literal[
    "app_logs",
    "k8s_events",
    "status",
    "metrics",
    "streams",
    "operation",
    "runbook",
]

EVIDENCE_SOURCE_VALUES: tuple[EvidenceSource, ...] = (
    "app_logs",
    "k8s_events",
    "status",
    "metrics",
    "streams",
    "operation",
    "runbook",
)

_SOURCE_ALIASES: dict[str, EvidenceSource] = {
    "app_logs": "app_logs",
    "application_logs": "app_logs",
    "application_log": "app_logs",
    "applicationlogs": "app_logs",
    "logs": "app_logs",
    "log": "app_logs",
    "k8s_events": "k8s_events",
    "kubernetes_events": "k8s_events",
    "k8s": "k8s_events",
    "events": "k8s_events",
    "status": "status",
    "service_status": "status",
    "metrics": "metrics",
    "metric": "metrics",
    "streams": "streams",
    "stream": "streams",
    "operation": "operation",
    "operations": "operation",
    "runbook": "runbook",
}


def _canonical_source_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def normalize_evidence_source(value: Any) -> EvidenceSource:
    """Map LLM-friendly labels to EvidenceSource literals."""
    if value is None:
        return "app_logs"
    text = str(value).strip()
    if not text:
        return "app_logs"
    if text in EVIDENCE_SOURCE_VALUES:
        return text  # type: ignore[return-value]
    base = text.split("(")[0].strip()
    key = _canonical_source_key(base)
    if key in _SOURCE_ALIASES:
        return _SOURCE_ALIASES[key]
    if key in EVIDENCE_SOURCE_VALUES:
        return key  # type: ignore[return-value]
    lowered = base.lower()
    if "metric" in lowered:
        return "metrics"
    if "k8s" in lowered or "kubernetes" in lowered or "event" in lowered:
        return "k8s_events"
    if "stream" in lowered:
        return "streams"
    if "runbook" in lowered:
        return "runbook"
    if "operation" in lowered:
        return "operation"
    if "status" in lowered:
        return "status"
    if "log" in lowered:
        return "app_logs"
    return "app_logs"


def coerce_root_cause_draft(data: Any) -> Any:
    """Normalize LLM JSON drift for RootCauseDraft (evidence.source labels)."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    evidence = out.get("evidence")
    if not isinstance(evidence, list):
        return out
    normalized: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        row = dict(item)
        if "source" in row:
            row["source"] = normalize_evidence_source(row["source"])
        normalized.append(row)
    out["evidence"] = normalized
    return out


class EvidenceCitation(BaseModel):
    source: EvidenceSource = Field(
        description=(
            "Telemetry source tag — exactly one of: "
            "app_logs, k8s_events, status, metrics, streams, operation, runbook"
        ),
    )
    snippet: str = Field(max_length=300)
    ref: str


class RootCauseDraft(BaseModel):
    root_cause: str = Field(description="Concise root cause analysis in Chinese, 2-4 sentences")
    evidence: list[EvidenceCitation] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_shape(cls, data: Any) -> Any:
        return coerce_root_cause_draft(data)


RCA_SYSTEM_PROMPT = """\
You are a senior cloud operations engineer.
Given incident telemetry (and an optional validated runbook excerpt), produce a root cause analysis.

Write root_cause in Chinese: 2-4 sentences, cite exact errors/metrics/misconfigurations.
List evidence items with source, snippet, and ref.
For each evidence item, source MUST be exactly one of these machine tags (no human labels):
app_logs | k8s_events | status | metrics | streams | operation | runbook

Example JSON shape:
{
  "root_cause": "…",
  "evidence": [
    {
      "source": "app_logs",
      "snippet": "ERROR discount validation failed",
      "ref": "query_app_logs:ecomm-manager"
    },
    {
      "source": "metrics",
      "snippet": "order_amount_error_rate elevated",
      "ref": "get_metrics:ecomm-manager"
    }
  ]
}
Do NOT recommend remediation steps or tool invocations.
"""


CONFIDENCE_SYSTEM_PROMPT = """\
You are the diagnosis confidence rubric module of an ops agent.
Evaluate whether the proposed root cause and evidence are reliable enough for automated remediation.
Do NOT re-evaluate runbook selection (handled upstream).

For EACH dimension below you MUST:
1. Write reasoning first — cite concrete telemetry vs evidence/root_cause alignment.
2. Then assign rating — exactly one of: PASS, PARTIAL, FAIL.

[evidence_grounding]
- PASS: evidence snippets match telemetry facts (errors, metrics, timestamps).
- PARTIAL: directionally aligned but missing key metric/log or timing is vague.
- FAIL: evidence contradicts telemetry or appears fabricated.

[causal_specificity]
- PASS: root cause names a specific, testable failure mode (config key, error class, resource).
- PARTIAL: plausible but lacks observable proof or is overly generic.
- FAIL: vague hand-waving or untestable hypothesis.

[alternative_excluded]
- PASS: main competing hypotheses are ruled out using telemetry.
- PARTIAL: some alternatives excluded, one plausible alternative remains.
- FAIL: obvious alternative not addressed.

[contradiction_clear]
- PASS: no conflict between root cause and telemetry facts.
- PARTIAL: minor tension explained or low-risk ambiguity.
- FAIL: clear contradiction with known telemetry.

Output structured JSON with one object per dimension: {reasoning, rating}.
"""


def coerce_diagnosis_confidence_assessment(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    out: dict[str, object] = {}
    for dim in CONFIDENCE_DIMS:
        if dim in data:
            out[dim] = coerce_dimension_assessment(data[dim])
        else:
            out[dim] = {"reasoning": "", "rating": "FAIL"}
    return out


class DiagnosisConfidenceAssessment(BaseModel):
    evidence_grounding: DimensionAssessment = Field(default_factory=DimensionAssessment)
    causal_specificity: DimensionAssessment = Field(default_factory=DimensionAssessment)
    alternative_excluded: DimensionAssessment = Field(default_factory=DimensionAssessment)
    contradiction_clear: DimensionAssessment = Field(default_factory=DimensionAssessment)

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_shape(cls, data: Any) -> Any:
        return coerce_diagnosis_confidence_assessment(data)

    def as_dict(self) -> dict[str, DimensionAssessment]:
        return {
            "evidence_grounding": self.evidence_grounding,
            "causal_specificity": self.causal_specificity,
            "alternative_excluded": self.alternative_excluded,
            "contradiction_clear": self.contradiction_clear,
        }


# Backward-compatible alias.
DiagnosisConfidenceRubric = DiagnosisConfidenceAssessment


_LOW_CONFIDENCE_SERVICES = frozenset({"ecomm-search", "ecomm-catalog"})
_HIGH_CONFIDENCE_NOVEL = frozenset({"ecomm-cache"})


def _dim(reasoning: str, rating: str) -> DimensionAssessment:
    return DimensionAssessment(reasoning=reasoning, rating=rating)  # type: ignore[arg-type]


def mock_confidence_assessment(service: str) -> DiagnosisConfidenceAssessment:
    if service in _LOW_CONFIDENCE_SERVICES:
        return DiagnosisConfidenceAssessment(
            evidence_grounding=_dim("Symptoms ambiguous; log alignment weak.", "PARTIAL"),
            causal_specificity=_dim("Root cause not specific enough for auto-remediation.", "PARTIAL"),
            alternative_excluded=_dim("Competing hypotheses not ruled out.", "FAIL"),
            contradiction_clear=_dim("Minor tension with sparse telemetry.", "FAIL"),
        )
    if service in _HIGH_CONFIDENCE_NOVEL:
        return DiagnosisConfidenceAssessment(
            evidence_grounding=_dim("OOM/restart pattern grounded in k8s events.", "PASS"),
            causal_specificity=_dim("OOMKilled + memory limit is specific and testable.", "PASS"),
            alternative_excluded=_dim("Network and disk alternatives unlikely given events.", "PASS"),
            contradiction_clear=_dim("No contradiction with pod restart telemetry.", "PASS"),
        )
    return DiagnosisConfidenceAssessment(
        evidence_grounding=_dim("Evidence snippets align with collected telemetry.", "PASS"),
        causal_specificity=_dim("Root cause cites concrete misconfiguration or error.", "PASS"),
        alternative_excluded=_dim("Main alternatives addressed in RCA.", "PARTIAL"),
        contradiction_clear=_dim("No obvious telemetry conflict.", "PASS"),
    )


mock_confidence_rubric = mock_confidence_assessment
