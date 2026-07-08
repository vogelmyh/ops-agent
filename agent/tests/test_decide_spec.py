"""Tests for DecideAssessment LLM JSON coercion."""

from app.graph.decide_spec import DecideAssessment, DecideOutcome, coerce_decide_assessment


def test_coerce_classification_to_outcome():
    data = coerce_decide_assessment({
        "classification": "out_of_scope",
        "recommendations": "Escalate to platform team",
    })
    assert data["outcome"] == "out_of_scope"
    assert data["recommendations"] == ["Escalate to platform team"]


def test_coerce_outcome_value_normalization():
    data = coerce_decide_assessment({
        "outcome": "out-of-scope",
        "reasoning": "Code defect",
    })
    assert data["outcome"] == "out_of_scope"


def test_coerce_missing_reasoning_defaults_empty():
    model = DecideAssessment.model_validate(coerce_decide_assessment({
        "outcome": "uncertain",
        "recommendations": [],
        "knowledge_gaps": ["need more logs"],
    }))
    assert model.reasoning == ""
    assert model.outcome == DecideOutcome.UNCERTAIN


def test_coerce_reasoning_from_explanation_alias():
    model = DecideAssessment.model_validate(coerce_decide_assessment({
        "decision": "actionable",
        "explanation": "Rollback is safe per runbook.",
        "recommendations": [],
    }))
    assert model.outcome == DecideOutcome.ACTIONABLE
    assert model.reasoning == "Rollback is safe per runbook."


def test_coerce_escalation_hint_null_string():
    model = DecideAssessment.model_validate(coerce_decide_assessment({
        "outcome": "out_of_scope",
        "reasoning": "Hardware fault",
        "escalation_hint": "null",
    }))
    assert model.escalation_hint is None


def test_coerce_assessment_alias_to_outcome():
    model = DecideAssessment.model_validate(coerce_decide_assessment({
        "assessment": "actionable",
        "reasoning": "",
        "recommendations": [],
    }))
    assert model.outcome == DecideOutcome.ACTIONABLE


def test_coerce_assessment_nested_dict():
    model = DecideAssessment.model_validate(coerce_decide_assessment({
        "assessment": {"outcome": "out_of_scope"},
        "reasoning": "Code defect outside ops catalog",
    }))
    assert model.outcome == DecideOutcome.OUT_OF_SCOPE


def test_coerce_outcome_prefix_with_extra_text():
    data = coerce_decide_assessment({
        "outcome": "actionable: patch_config is appropriate",
        "reasoning": "Rate limit misconfiguration",
    })
    assert data["outcome"] == "actionable"
