from app.graph.categorical_rubric import DimensionAssessment, coerce_rating
from app.graph.diagnose_spec import DiagnosisConfidenceAssessment, mock_confidence_assessment
from app.graph.diagnosis_confidence_policy import (
    DiagnosisConfidencePolicy,
    build_confidence_gate_reason,
    is_diagnostic_reliable,
)


def _dim(reasoning: str, rating: str) -> DimensionAssessment:
    return DimensionAssessment(reasoning=reasoning, rating=rating)  # type: ignore[arg-type]


def test_coerce_rating_aliases():
    assert coerce_rating("pass") == "PASS"
    assert coerce_rating("PARTIAL") == "PARTIAL"
    assert coerce_rating("unknown", default="FAIL") == "FAIL"


def test_low_confidence_service_not_reliable():
    assessment = mock_confidence_assessment("ecomm-search")
    assert is_diagnostic_reliable(assessment.as_dict()) is False


def test_high_confidence_novel_reliable():
    assessment = mock_confidence_assessment("ecomm-cache")
    assert is_diagnostic_reliable(assessment.as_dict()) is True


def test_fail_any_blocks():
    assessment = DiagnosisConfidenceAssessment(
        evidence_grounding=_dim("ok", "PASS"),
        causal_specificity=_dim("ok", "PASS"),
        alternative_excluded=_dim("bad", "FAIL"),
        contradiction_clear=_dim("ok", "PASS"),
    )
    assert is_diagnostic_reliable(assessment.as_dict()) is False


def test_grounding_must_pass():
    assessment = DiagnosisConfidenceAssessment(
        evidence_grounding=_dim("weak", "PARTIAL"),
        causal_specificity=_dim("ok", "PASS"),
        alternative_excluded=_dim("ok", "PASS"),
        contradiction_clear=_dim("ok", "PASS"),
    )
    assert is_diagnostic_reliable(assessment.as_dict()) is False


def test_max_partial_enforced():
    assessment = DiagnosisConfidenceAssessment(
        evidence_grounding=_dim("ok", "PASS"),
        causal_specificity=_dim("a", "PARTIAL"),
        alternative_excluded=_dim("b", "PARTIAL"),
        contradiction_clear=_dim("ok", "PASS"),
    )
    assert is_diagnostic_reliable(assessment.as_dict(), policy=DiagnosisConfidencePolicy(max_partial=1)) is False


def test_gate_reason_when_unreliable():
    assessment = mock_confidence_assessment("ecomm-search")
    reason = build_confidence_gate_reason(assessment.as_dict(), reliable=False)
    assert "not reliable" in reason.lower()
