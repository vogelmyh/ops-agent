from app.graph.diagnose_spec import (
    DiagnosisConfidenceRubric,
    mock_confidence_rubric,
)


def test_confidence_score_from_rubric_sum():
    rubric = mock_confidence_rubric("ecomm-manager")
    assert rubric.confidence_score == (
        rubric.evidence_grounding
        + rubric.causal_specificity
        + rubric.alternative_excluded
        + rubric.contradiction_clear
    )


def test_low_confidence_service_rubric():
    rubric = mock_confidence_rubric("ecomm-search")
    assert rubric.confidence_score < 0.55


def test_confidence_score_max_one():
    rubric = DiagnosisConfidenceRubric(
        evidence_grounding=0.25,
        causal_specificity=0.25,
        alternative_excluded=0.25,
        contradiction_clear=0.25,
    )
    assert rubric.confidence_score == 1.0
