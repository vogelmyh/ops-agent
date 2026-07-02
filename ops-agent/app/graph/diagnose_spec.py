"""RCA and confidence rubric prompts, schemas, and mock oracles."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.graph.eval_schemas import _as_str_list

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
Score the proposed root cause and evidence — NOT runbook selection (handled upstream).

Score each dimension 0, 0.15, or 0.25:
- evidence_grounding: evidence snippets align with telemetry
- causal_specificity: root cause is specific and testable
- alternative_excluded: main competing hypotheses are ruled out
- contradiction_clear: no obvious conflict with telemetry facts

Output numeric rubric fields and brief reasoning only.
"""


class DiagnosisConfidenceRubric(BaseModel):
    evidence_grounding: float = Field(default=0.0, ge=0.0, le=0.25)
    causal_specificity: float = Field(default=0.0, ge=0.0, le=0.25)
    alternative_excluded: float = Field(default=0.0, ge=0.0, le=0.25)
    contradiction_clear: float = Field(default=0.0, ge=0.0, le=0.25)
    reasoning: str = ""

    @property
    def rca_rubric_sum(self) -> float:
        return min(
            0.75,
            self.evidence_grounding
            + self.causal_specificity
            + self.alternative_excluded
            + self.contradiction_clear,
        )


def coerce_diagnosis_confidence_rubric(data) -> dict:
    if not isinstance(data, dict):
        return data
    out = dict(data)
    if not out.get("reasoning"):
        for alias in ("explanation", "summary", "rationale", "reason"):
            if alias in out and out[alias]:
                out["reasoning"] = str(out[alias])
                break
        else:
            out.setdefault("reasoning", "")
    return out


# Mock confidence profiles keyed by service for graph scenarios.
_LOW_CONFIDENCE_SERVICES = frozenset({"ecomm-search", "ecomm-catalog"})
_HIGH_CONFIDENCE_NOVEL = frozenset({"ecomm-cache"})


def mock_confidence_rubric(service: str) -> DiagnosisConfidenceRubric:
    if service in _LOW_CONFIDENCE_SERVICES:
        return DiagnosisConfidenceRubric(
            evidence_grounding=0.10,
            causal_specificity=0.10,
            alternative_excluded=0.05,
            contradiction_clear=0.05,
            reasoning="Ambiguous symptoms; RCA not converged enough for automated remediation.",
        )
    if service in _HIGH_CONFIDENCE_NOVEL:
        return DiagnosisConfidenceRubric(
            evidence_grounding=0.25,
            causal_specificity=0.25,
            alternative_excluded=0.20,
            contradiction_clear=0.20,
            reasoning="OOM/restart pattern is specific and grounded in telemetry.",
        )
    return DiagnosisConfidenceRubric(
        evidence_grounding=0.25,
        causal_specificity=0.25,
        alternative_excluded=0.20,
        contradiction_clear=0.20,
        reasoning="Diagnosis aligns with telemetry and selected runbook context.",
    )


def compute_confidence_score(
    rubric: DiagnosisConfidenceRubric,
    *,
    runbook_support: float,
) -> tuple[float, float, float]:
    """Return (rca_rubric_sum, runbook_support, confidence_score)."""
    rca_sum = rubric.rca_rubric_sum
    support = max(0.0, min(0.25, runbook_support))
    return rca_sum, support, min(1.0, rca_sum + support)
