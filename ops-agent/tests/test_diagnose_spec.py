from app.graph.diagnose_spec import (
    DiagnosisConfidenceRubric,
    compute_confidence_score,
    mock_confidence_rubric,
)


def test_compute_confidence_score_with_runbook_support():
    rubric = mock_confidence_rubric("ecomm-manager")
    rca, support, total = compute_confidence_score(rubric, runbook_support=0.25)
    assert rca == rubric.rca_rubric_sum
    assert support == 0.25
    assert total == rca + 0.25


def test_low_confidence_service_rubric():
    rubric = mock_confidence_rubric("ecomm-search")
    _, _, total = compute_confidence_score(rubric, runbook_support=0.0)
    assert total < 0.55


def test_rca_rubric_sum_capped():
    rubric = DiagnosisConfidenceRubric(
        evidence_grounding=0.25,
        causal_specificity=0.25,
        alternative_excluded=0.25,
        contradiction_clear=0.25,
    )
    assert rubric.rca_rubric_sum == 0.75
