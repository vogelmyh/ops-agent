"""Tests for eval schema coercion (CoT categorical rubric JSON)."""

from __future__ import annotations

from app.graph.eval_schemas import (
    RunbookEvalLLMOutput,
    RunbookMatchAssessment,
    coerce_runbook_eval_llm_output,
    coerce_runbook_match_assessment,
)
from app.graph.runbook_match_policy import (
    attach_llm_assessments,
    candidate_from_retrieval_dict,
    finalize_runbook_match,
    is_candidate_selectable,
)


def _nested_crashloop_rubric() -> dict:
    return {
        "doc_id": "ecomm-order-crashloop",
        "service_scope": {
            "reasoning": "scope matches ecomm-order",
            "rating": "PASS",
        },
        "symptom_match": {
            "reasoning": "CrashLoopBackOff in symptoms",
            "rating": "PASS",
        },
        "telemetry_match": {
            "reasoning": "K8s BackOff events align",
            "rating": "PASS",
        },
        "exclusion_clear": {
            "reasoning": "no OOM exclusion conflict",
            "rating": "PASS",
        },
    }


def test_nested_match_assessment_coerced():
    rubric = RunbookMatchAssessment.model_validate(_nested_crashloop_rubric())
    assert rubric.doc_id == "ecomm-order-crashloop"
    assert rubric.symptom_match.rating == "PASS"
    assert is_candidate_selectable(rubric) is True


def test_coerce_helper_preserves_flat_input():
    flat = {
        "doc_id": "ecomm-manager-rate-limit",
        "service_scope": {"reasoning": "ok", "rating": "PASS"},
    }
    coerced = coerce_runbook_match_assessment(flat)
    assert coerced["doc_id"] == "ecomm-manager-rate-limit"


def test_nested_via_runbook_eval_llm_output():
    output = RunbookEvalLLMOutput.model_validate({
        "rubrics": [
            _nested_crashloop_rubric(),
            {
                "doc_id": "ecomm-order-memory-leak",
                "service_scope": {"reasoning": "ok", "rating": "PASS"},
                "symptom_match": {"reasoning": "OOM not crashloop", "rating": "FAIL"},
                "telemetry_match": {"reasoning": "mismatch", "rating": "FAIL"},
                "exclusion_clear": {"reasoning": "n/a", "rating": "PARTIAL"},
            },
        ],
    })
    assert len(output.rubrics) == 2
    assert output.rubrics[1].symptom_match.rating == "FAIL"


def test_nested_rubric_finalize_selects_crashloop():
    candidate = candidate_from_retrieval_dict({
        "doc_id": "ecomm-order-crashloop",
        "title": "CrashLoop",
        "service": "ecomm-order",
        "chunk_type": "parent",
        "content": "## 适用范围\n仅适用于服务 `ecomm-order`\n",
        "rerank_score": 1.0,
    })
    llm_output = RunbookEvalLLMOutput(
        rubrics=[RunbookMatchAssessment.model_validate(_nested_crashloop_rubric())],
    )
    enriched = attach_llm_assessments("ecomm-order", [candidate], llm_output)
    result = finalize_runbook_match("ecomm-order", enriched, llm_output)
    assert result.novel_scenario is False
    assert result.selected_doc_id == "ecomm-order-crashloop"


def test_bare_rubric_array_wrapped():
    bare = [_nested_crashloop_rubric()]
    assert coerce_runbook_eval_llm_output(bare) == {"rubrics": bare}
    output = RunbookEvalLLMOutput.model_validate(bare)
    assert len(output.rubrics) == 1
    assert output.rubrics[0].service_scope.rating == "PASS"


def test_coerce_remediation_eval_missing_reasoning_defaults_empty():
    from app.graph.eval_schemas import RemediationEvalAssessment, coerce_remediation_eval_assessment

    model = RemediationEvalAssessment.model_validate(coerce_remediation_eval_assessment({
        "resolved": False,
        "residual_symptoms": ["QPS still low"],
    }))
    assert model.reasoning == ""
    assert model.resolved is False
