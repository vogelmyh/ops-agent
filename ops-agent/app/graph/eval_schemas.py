"""Pydantic schemas for eval nodes using with_structured_output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, computed_field, model_validator


# ---------------------------------------------------------------------------
# Runbook coverage eval (relevance-only rubric → match_score)
# ---------------------------------------------------------------------------

class RetrievalScores(BaseModel):
    """Scores from the retrieval stack (vector / BM25 / rerank). Optional until hybrid PR."""

    vector_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None


class RunbookRelevanceRubric(BaseModel):
    """Per-doc match rubric. Each dimension 0, 0.15, or 0.25 (service_scope: 0 or 0.25)."""

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


def _coerce_str_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
        return parts if len(parts) > 1 else [text]
    return [str(value).strip()]


def coerce_runbook_per_doc_rubric(data: Any) -> Any:
    """Normalize LLM rubric JSON: flat fields or nested relevance group."""
    if not isinstance(data, dict):
        return data

    rel = _nested_dict(data.get("relevance"))
    if not rel:
        out = dict(data)
        changed = False
        if "match_signals" in out:
            coerced = _coerce_str_list(out["match_signals"])
            if coerced != out["match_signals"]:
                out["match_signals"] = coerced
                changed = True
        if "conflict_signals" in out:
            coerced = _coerce_str_list(out["conflict_signals"])
            if coerced != out["conflict_signals"]:
                out["conflict_signals"] = coerced
                changed = True
        return out if changed else data

    doc_id = data.get("doc_id") or rel.get("doc_id") or ""
    return {
        "doc_id": doc_id,
        "service_scope_match": _field_or_default(rel, data, "service_scope_match", 0.0),
        "symptom_match": _field_or_default(rel, data, "symptom_match", 0.0),
        "telemetry_match": _field_or_default(rel, data, "telemetry_match", 0.0),
        "exclusion_clear": _field_or_default(rel, data, "exclusion_clear", 0.0),
        "match_signals": _coerce_str_list(_field_or_default(rel, data, "match_signals", [])),
        "conflict_signals": _coerce_str_list(_field_or_default(rel, data, "conflict_signals", [])),
    }


class RunbookPerDocRubric(BaseModel):
    """Per-candidate relevance rubric — sole element of LLM structured output."""

    doc_id: str
    service_scope_match: float = Field(default=0.0, ge=0.0, le=0.25)
    symptom_match: float = Field(default=0.0, ge=0.0, le=0.25)
    telemetry_match: float = Field(default=0.0, ge=0.0, le=0.25)
    exclusion_clear: float = Field(default=0.0, ge=0.0, le=0.25)
    match_signals: list[str] = Field(default_factory=list)
    conflict_signals: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_rubric_shape(cls, data: Any) -> Any:
        return coerce_runbook_per_doc_rubric(data)

    @classmethod
    def from_relevance(cls, relevance: RunbookRelevanceRubric) -> "RunbookPerDocRubric":
        return cls(
            doc_id=relevance.doc_id,
            service_scope_match=relevance.service_scope_match,
            symptom_match=relevance.symptom_match,
            telemetry_match=relevance.telemetry_match,
            exclusion_clear=relevance.exclusion_clear,
            match_signals=list(relevance.match_signals),
            conflict_signals=list(relevance.conflict_signals),
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


class RunbookCandidate(BaseModel):
    """Unified retrieval → eval carrier (chunk recall expands to parent document)."""

    doc_id: str
    service: str = ""
    title: str = ""
    content: str = ""
    chunk_type: str = "parent"
    retrieval_scores: RetrievalScores = Field(default_factory=RetrievalScores)
    relevance: RunbookRelevanceRubric | None = None


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
    match_score: float | None = None
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


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


_RESOLVED_TRUTHY = frozenset({"true", "yes", "resolved", "recovered", "fixed", "healthy"})
_RESOLVED_FALSY = frozenset({"false", "no", "unresolved", "not_resolved", "failed", "broken"})


def coerce_remediation_eval_assessment(data: Any) -> Any:
    """Normalize LLM JSON drift into flat RemediationEvalAssessment fields."""
    if not isinstance(data, dict):
        return data

    out = dict(data)
    if "resolved" not in out:
        for alias in ("is_resolved", "incident_resolved", "recovery", "fixed"):
            if alias in out:
                out["resolved"] = out.pop(alias)
                break

    resolved = out.get("resolved")
    if isinstance(resolved, str):
        key = resolved.strip().lower().replace("-", "_").replace(" ", "_")
        if key in _RESOLVED_TRUTHY:
            out["resolved"] = True
        elif key in _RESOLVED_FALSY:
            out["resolved"] = False

    symptom_key = "residual_symptoms"
    if symptom_key not in out:
        for alias in ("remaining_symptoms", "symptoms", "residuals", "residual_issues"):
            if alias in out:
                out[symptom_key] = out.pop(alias)
                break
    if symptom_key in out:
        out[symptom_key] = _as_str_list(out[symptom_key])
    else:
        out.setdefault(symptom_key, [])

    if not out.get("reasoning"):
        for alias in (
            "explanation",
            "summary",
            "rationale",
            "reason",
            "verification_reasoning",
            "assessment",
            "comment",
        ):
            if alias in out and out[alias]:
                out["reasoning"] = str(out[alias])
                break
        else:
            out.setdefault("reasoning", "")

    return out


class RemediationEvalAssessment(BaseModel):
    resolved: bool = Field(description="True when post-remediation telemetry shows incident is fixed")
    reasoning: str = Field(description="Brief explanation of the verification outcome")
    residual_symptoms: list[str] = Field(
        default_factory=list,
        description="Remaining symptoms when resolved is false",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_assessment_shape(cls, data: Any) -> Any:
        return coerce_remediation_eval_assessment(data)
