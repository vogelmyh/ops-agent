"""Pydantic schemas for eval nodes using with_structured_output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.graph.categorical_rubric import DimensionAssessment, coerce_dimension_assessment


# ---------------------------------------------------------------------------
# Runbook coverage eval (CoT categorical rubric)
# ---------------------------------------------------------------------------

class RetrievalScores(BaseModel):
    """Scores from the retrieval stack (vector / BM25 / rerank)."""

    vector_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None


MATCH_DIMENSION_FIELDS = (
    "service_scope",
    "symptom_match",
    "telemetry_match",
    "exclusion_clear",
)


def _nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def coerce_runbook_match_assessment(data: Any) -> Any:
    """Normalize per-candidate match rubric JSON from LLM."""
    if not isinstance(data, dict):
        return data

    out: dict[str, Any] = {"doc_id": data.get("doc_id", "")}
    for dim in MATCH_DIMENSION_FIELDS:
        nested = _nested_dict(data.get(dim))
        if nested:
            out[dim] = coerce_dimension_assessment(nested)
        elif dim in data:
            out[dim] = coerce_dimension_assessment(data[dim])
        else:
            out[dim] = {"reasoning": "", "rating": "FAIL"}
    return out


class RunbookMatchAssessment(BaseModel):
    """Per-candidate CoT categorical match rubric."""

    doc_id: str
    service_scope: DimensionAssessment = Field(default_factory=DimensionAssessment)
    symptom_match: DimensionAssessment = Field(default_factory=DimensionAssessment)
    telemetry_match: DimensionAssessment = Field(default_factory=DimensionAssessment)
    exclusion_clear: DimensionAssessment = Field(default_factory=DimensionAssessment)

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_shape(cls, data: Any) -> Any:
        return coerce_runbook_match_assessment(data)

    def model_dump_ratings(self) -> dict[str, str]:
        return {
            "service_scope": self.service_scope.rating,
            "symptom_match": self.symptom_match.rating,
            "telemetry_match": self.telemetry_match.rating,
            "exclusion_clear": self.exclusion_clear.rating,
        }


# LLM output element alias.
RunbookPerDocRubric = RunbookMatchAssessment


class RunbookCandidate(BaseModel):
    """Unified retrieval → eval carrier (chunk recall expands to parent document)."""

    doc_id: str
    service: str = ""
    title: str = ""
    content: str = ""
    chunk_type: str = "parent"
    retrieval_scores: RetrievalScores = Field(default_factory=RetrievalScores)
    match_assessment: RunbookMatchAssessment | None = None


def coerce_runbook_eval_llm_output(data: Any) -> Any:
    """Normalize LLM output JSON: bare rubric list → {rubrics: [...]}."""
    if isinstance(data, list):
        return {"rubrics": data}
    return data


class RunbookEvalLLMOutput(BaseModel):
    """Structured LLM output — per-doc categorical assessments only."""

    rubrics: list[RunbookMatchAssessment] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_output_shape(cls, data: Any) -> Any:
        return coerce_runbook_eval_llm_output(data)


class RunbookEvalResult(BaseModel):
    """Final coverage decision after policy finalize."""

    novel_scenario: bool
    novel_reason: str | None = None
    selected_doc_id: str | None = None
    relevant_runbook: str | None = None
    candidates: list[RunbookCandidate] = Field(default_factory=list)
    reasoning: str = ""


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
