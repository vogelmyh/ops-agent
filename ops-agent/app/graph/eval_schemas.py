"""Pydantic schemas for eval nodes using with_structured_output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, computed_field, model_validator


# ---------------------------------------------------------------------------
# Runbook coverage eval (PR1 contracts — used by runbook_eval_policy; PR2 wires LLM)
# ---------------------------------------------------------------------------

class RetrievalScores(BaseModel):
    """Scores from the retrieval stack (vector / BM25 / rerank). Optional until hybrid PR."""

    vector_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None


class RunbookRelevanceRubric(BaseModel):
    """Stage A: symptom–runbook fit. Each dimension 0, 0.15, or 0.25 (service_scope: 0 or 0.25)."""

    doc_id: str
    service_scope_match: float = Field(default=0.0, ge=0.0, le=0.25)
    symptom_match: float = Field(default=0.0, ge=0.0, le=0.25)
    telemetry_match: float = Field(default=0.0, ge=0.0, le=0.25)
    exclusion_clear: float = Field(default=0.0, ge=0.0, le=0.25)
    match_signals: list[str] = Field(default_factory=list)
    conflict_signals: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def relevance_score(self) -> float:
        if self.service_scope_match <= 0:
            return 0.0
        return min(
            1.0,
            self.service_scope_match
            + self.symptom_match
            + self.telemetry_match
            + self.exclusion_clear,
        )


class RunbookCoverageRubric(BaseModel):
    """Stage B: whether the runbook can safely guide remediation for this incident."""

    doc_id: str
    root_cause_fit: float = Field(default=0.0, ge=0.0, le=0.25)
    remediation_fit: float = Field(default=0.0, ge=0.0, le=0.25)
    forbidden_clear: float = Field(default=0.0, ge=0.0, le=0.25)
    verification_fit: float = Field(default=0.0, ge=0.0, le=0.25)
    coverage_notes: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def coverage_confidence(self) -> float:
        return min(
            1.0,
            self.root_cause_fit
            + self.remediation_fit
            + self.forbidden_clear
            + self.verification_fit,
        )


def _nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _field_or_default(
    nested: dict[str, Any],
    flat: dict[str, Any],
    key: str,
    default: Any,
) -> Any:
    if key in nested:
        return nested[key]
    if key in flat:
        return flat[key]
    return default


def coerce_runbook_per_doc_rubric(data: Any) -> Any:
    """Normalize LLM rubric JSON: flat fields or nested relevance/coverage groups."""
    if not isinstance(data, dict):
        return data

    rel = _nested_dict(data.get("relevance"))
    cov = _nested_dict(data.get("coverage"))
    if not rel and not cov:
        return data

    doc_id = (
        data.get("doc_id")
        or rel.get("doc_id")
        or cov.get("doc_id")
        or ""
    )
    return {
        "doc_id": doc_id,
        "service_scope_match": _field_or_default(rel, data, "service_scope_match", 0.0),
        "symptom_match": _field_or_default(rel, data, "symptom_match", 0.0),
        "telemetry_match": _field_or_default(rel, data, "telemetry_match", 0.0),
        "exclusion_clear": _field_or_default(rel, data, "exclusion_clear", 0.0),
        "match_signals": _field_or_default(rel, data, "match_signals", []),
        "conflict_signals": _field_or_default(rel, data, "conflict_signals", []),
        "root_cause_fit": _field_or_default(cov, data, "root_cause_fit", 0.0),
        "remediation_fit": _field_or_default(cov, data, "remediation_fit", 0.0),
        "forbidden_clear": _field_or_default(cov, data, "forbidden_clear", 0.0),
        "verification_fit": _field_or_default(cov, data, "verification_fit", 0.0),
        "coverage_notes": _field_or_default(cov, data, "coverage_notes", ""),
    }


class RunbookPerDocRubric(BaseModel):
    """Merged Stage A + B rubric for one candidate — sole element of LLM structured output."""

    doc_id: str
    service_scope_match: float = Field(default=0.0, ge=0.0, le=0.25)
    symptom_match: float = Field(default=0.0, ge=0.0, le=0.25)
    telemetry_match: float = Field(default=0.0, ge=0.0, le=0.25)
    exclusion_clear: float = Field(default=0.0, ge=0.0, le=0.25)
    match_signals: list[str] = Field(default_factory=list)
    conflict_signals: list[str] = Field(default_factory=list)
    root_cause_fit: float = Field(default=0.0, ge=0.0, le=0.25)
    remediation_fit: float = Field(default=0.0, ge=0.0, le=0.25)
    forbidden_clear: float = Field(default=0.0, ge=0.0, le=0.25)
    verification_fit: float = Field(default=0.0, ge=0.0, le=0.25)
    coverage_notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_rubric_shape(cls, data: Any) -> Any:
        return coerce_runbook_per_doc_rubric(data)

    @classmethod
    def from_relevance_coverage(
        cls,
        relevance: RunbookRelevanceRubric,
        coverage: RunbookCoverageRubric | None = None,
    ) -> "RunbookPerDocRubric":
        cov = coverage or RunbookCoverageRubric(doc_id=relevance.doc_id)
        return cls(
            doc_id=relevance.doc_id,
            service_scope_match=relevance.service_scope_match,
            symptom_match=relevance.symptom_match,
            telemetry_match=relevance.telemetry_match,
            exclusion_clear=relevance.exclusion_clear,
            match_signals=list(relevance.match_signals),
            conflict_signals=list(relevance.conflict_signals),
            root_cause_fit=cov.root_cause_fit,
            remediation_fit=cov.remediation_fit,
            forbidden_clear=cov.forbidden_clear,
            verification_fit=cov.verification_fit,
            coverage_notes=cov.coverage_notes,
        )

    def to_relevance(self) -> RunbookRelevanceRubric:
        return RunbookRelevanceRubric(
            doc_id=self.doc_id,
            service_scope_match=self.service_scope_match,
            symptom_match=self.symptom_match,
            telemetry_match=self.telemetry_match,
            exclusion_clear=self.exclusion_clear,
            match_signals=list(self.match_signals),
            conflict_signals=list(self.conflict_signals),
        )

    def to_coverage(self) -> RunbookCoverageRubric:
        return RunbookCoverageRubric(
            doc_id=self.doc_id,
            root_cause_fit=self.root_cause_fit,
            remediation_fit=self.remediation_fit,
            forbidden_clear=self.forbidden_clear,
            verification_fit=self.verification_fit,
            coverage_notes=self.coverage_notes,
        )


class RunbookCandidate(BaseModel):
    """Unified retrieval → eval carrier (chunk recall expands to parent document)."""

    doc_id: str
    service: str = ""
    title: str = ""
    content: str = ""
    chunk_type: str = "parent"
    retrieval_scores: RetrievalScores = Field(default_factory=RetrievalScores)
    relevance: RunbookRelevanceRubric | None = None
    coverage: RunbookCoverageRubric | None = None


def coerce_runbook_eval_llm_output(data: Any) -> Any:
    """Normalize LLM output JSON: bare rubric list → {rubrics: [...]}."""
    if isinstance(data, list):
        return {"rubrics": data}
    return data


class RunbookEvalLLMOutput(BaseModel):
    """Structured LLM output — per-doc rubric scores only; selection and reasoning are code-owned."""

    rubrics: list[RunbookPerDocRubric] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_output_shape(cls, data: Any) -> Any:
        return coerce_runbook_eval_llm_output(data)


class RunbookEvalResult(BaseModel):
    """Final coverage decision after policy finalize (code-owned thresholds)."""

    novel_scenario: bool
    novel_reason: str | None = None
    selected_doc_id: str | None = None
    relevant_runbook: str | None = None
    coverage_confidence: float | None = None
    candidates: list[RunbookCandidate] = Field(default_factory=list)
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Legacy / other eval nodes (unchanged for PR1)
# ---------------------------------------------------------------------------

class RunbookEvalAssessment(BaseModel):
    novel_scenario: bool = Field(
        description="True when no runbook can guide remediation for this incident",
    )
    relevant_runbook: str | None = Field(
        default=None,
        description="Full text of the most relevant runbook when novel_scenario is false",
    )
    reasoning: str = Field(description="Brief explanation of the coverage decision")


class DiagnosisEvalAssessment(BaseModel):
    needs_human_review: bool = Field(
        description="True when diagnosis is not reliable enough for unsupervised follow-up",
    )
    reasoning: str = Field(description="Brief explanation of diagnosis confidence")


class RemediationEvalAssessment(BaseModel):
    resolved: bool = Field(description="True when post-remediation telemetry shows incident is fixed")
    reasoning: str = Field(description="Brief explanation of the verification outcome")
    residual_symptoms: list[str] = Field(
        default_factory=list,
        description="Remaining symptoms when resolved is false",
    )
