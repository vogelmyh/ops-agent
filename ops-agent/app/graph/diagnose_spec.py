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


class EvidenceCitation(BaseModel):
    source: EvidenceSource
    snippet: str = Field(max_length=300)
    ref: str


class RootCauseDraft(BaseModel):
    root_cause: str = Field(description="Concise root cause analysis in Chinese, 2-4 sentences")
    evidence: list[EvidenceCitation] = Field(default_factory=list)


RCA_SYSTEM_PROMPT = """\
You are a senior cloud operations engineer.
Given incident telemetry (and an optional validated runbook excerpt), produce a root cause analysis.

Write root_cause in Chinese: 2-4 sentences, cite exact errors/metrics/misconfigurations.
List evidence items with source, snippet, and ref.
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
