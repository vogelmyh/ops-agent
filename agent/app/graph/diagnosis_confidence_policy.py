"""Diagnosis confidence — CoT categorical rubric + deterministic routing."""

from __future__ import annotations

from dataclasses import dataclass

from app.graph.categorical_rubric import DimensionAssessment, Rating

CONFIDENCE_DIMS = (
    "evidence_grounding",
    "causal_specificity",
    "alternative_excluded",
    "contradiction_clear",
)


@dataclass(frozen=True)
class DiagnosisConfidencePolicy:
    require_pass: frozenset[str] = frozenset({"evidence_grounding"})
    hard_fail_any: bool = True
    max_partial: int = 1


def policy_from_settings(settings=None) -> DiagnosisConfidencePolicy:
    from app.config import get_settings

    settings = settings or get_settings()
    return DiagnosisConfidencePolicy(
        max_partial=settings.diagnosis_confidence_max_partial,
    )


def is_diagnostic_reliable(
    assessment: dict[str, DimensionAssessment],
    *,
    policy: DiagnosisConfidencePolicy | None = None,
) -> bool:
    policy = policy or DiagnosisConfidencePolicy()
    ratings = [assessment[dim].rating for dim in CONFIDENCE_DIMS if dim in assessment]
    if policy.hard_fail_any and "FAIL" in ratings:
        return False
    for dim in policy.require_pass:
        if assessment.get(dim) is None or assessment[dim].rating != "PASS":
            return False
    if ratings.count("PARTIAL") > policy.max_partial:
        return False
    return True


def build_confidence_gate_reason(
    assessment: dict[str, DimensionAssessment],
    *,
    reliable: bool,
    policy: DiagnosisConfidencePolicy | None = None,
) -> str:
    policy = policy or DiagnosisConfidencePolicy()
    if reliable:
        partial_dims = [
            dim for dim in CONFIDENCE_DIMS
            if dim in assessment and assessment[dim].rating == "PARTIAL"
        ]
        if partial_dims:
            return (
                "Diagnosis reliable: all required dimensions PASS; "
                f"partial on {', '.join(partial_dims)}."
            )
        return "Diagnosis reliable: all confidence dimensions PASS."

    reasons: list[str] = []
    ratings = {dim: assessment[dim].rating for dim in CONFIDENCE_DIMS if dim in assessment}
    if policy.hard_fail_any and "FAIL" in ratings.values():
        fail_dims = [d for d, r in ratings.items() if r == "FAIL"]
        reasons.append(f"FAIL on {', '.join(fail_dims)}")
    for dim in policy.require_pass:
        rating = ratings.get(dim)
        if rating != "PASS":
            reasons.append(f"{dim} is {rating or 'missing'} (required PASS)")
    partial_count = list(ratings.values()).count("PARTIAL")
    if partial_count > policy.max_partial:
        reasons.append(
            f"PARTIAL count {partial_count} exceeds max {policy.max_partial}",
        )
    detail = "; ".join(reasons) if reasons else "confidence gate failed"
    return f"Diagnosis not reliable: {detail}."
