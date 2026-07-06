"""Shared CoT categorical rubric types (PASS / PARTIAL / FAIL)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Rating = Literal["PASS", "PARTIAL", "FAIL"]

_RATING_ALIASES: dict[str, Rating] = {
    "PASS": "PASS",
    "PARTIAL": "PARTIAL",
    "FAIL": "FAIL",
    "pass": "PASS",
    "partial": "PARTIAL",
    "fail": "FAIL",
    "YES": "PASS",
    "NO": "FAIL",
    "MAYBE": "PARTIAL",
}


def coerce_rating(value: Any, *, default: Rating = "FAIL") -> Rating:
    if value is None:
        return default
    text = str(value).strip().upper()
    if text in _RATING_ALIASES:
        return _RATING_ALIASES[text]
    if text in ("PASS", "PARTIAL", "FAIL"):
        return text  # type: ignore[return-value]
    return default


def _nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def coerce_dimension_assessment(data: Any, *, default_rating: Rating = "FAIL") -> Any:
    """Normalize LLM dimension JSON: flat rating or {reasoning, rating}."""
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    if not isinstance(data, dict):
        if isinstance(data, str):
            return {"reasoning": "", "rating": coerce_rating(data, default=default_rating)}
        return {"reasoning": "", "rating": default_rating}

    out = dict(data)
    rating_raw = out.get("rating", out.get("score", out.get("label")))
    if rating_raw is None and len(out) == 1:
        only_key = next(iter(out))
        if only_key.upper() in _RATING_ALIASES or only_key.upper() in ("PASS", "PARTIAL", "FAIL"):
            rating_raw = only_key
            out = {"reasoning": str(out[only_key]), "rating": rating_raw}

    reasoning = ""
    for key in ("reasoning", "reason", "explanation", "rationale"):
        if out.get(key):
            reasoning = str(out[key]).strip()
            break

    return {
        "reasoning": reasoning,
        "rating": coerce_rating(rating_raw, default=default_rating),
    }


class DimensionAssessment(BaseModel):
    reasoning: str = Field(default="", max_length=500)
    rating: Rating = "FAIL"

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data: Any) -> Any:
        return coerce_dimension_assessment(data)


def ratings_summary(assessments: dict[str, DimensionAssessment]) -> list[Rating]:
    return [a.rating for a in assessments.values()]


def count_ratings(ratings: list[Rating]) -> dict[Rating, int]:
    counts: dict[Rating, int] = {"PASS": 0, "PARTIAL": 0, "FAIL": 0}
    for rating in ratings:
        counts[rating] += 1
    return counts
