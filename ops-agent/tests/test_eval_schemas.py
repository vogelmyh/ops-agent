"""Tests for eval schema coercion (nested LLM rubric JSON → flat RunbookPerDocRubric)."""

from __future__ import annotations

from app.graph.eval_schemas import (
    RunbookEvalLLMOutput,
    RunbookPerDocRubric,
    coerce_runbook_eval_llm_output,
    coerce_runbook_per_doc_rubric,
)
from app.graph.runbook_eval_policy import (
    attach_llm_rubrics,
    candidate_from_retrieval_dict,
    compute_relevance_score,
    finalize_runbook_eval,
)


def _nested_crashloop_rubric() -> dict:
    """Fixture shaped like qwen3.7 free JSON (neg-crashloop-no-restart-01)."""
    return {
        "doc_id": "ecomm-order-crashloop",
        "relevance": {
            "service_scope_match": 0.25,
            "symptom_match": 0.25,
            "telemetry_match": 0.25,
            "exclusion_clear": 0.25,
            "match_signals": ["CrashLoopBackOff", "BackOff"],
            "conflict_signals": [],
        },
        "coverage": {
            "root_cause_fit": 0.25,
            "remediation_fit": 0.25,
            "forbidden_clear": 0.25,
            "verification_fit": 0.25,
            "coverage_notes": "matches bad image crashloop",
        },
    }


def test_flat_rubric_unchanged():
    flat = RunbookPerDocRubric(
        doc_id="ecomm-order-crashloop",
        service_scope_match=0.25,
        symptom_match=0.25,
        telemetry_match=0.25,
        exclusion_clear=0.15,
        root_cause_fit=0.25,
        remediation_fit=0.25,
        forbidden_clear=0.20,
        verification_fit=0.20,
    )
    assert compute_relevance_score(flat.to_relevance()) == 0.9


def test_nested_rubric_coerced():
    rubric = RunbookPerDocRubric.model_validate(_nested_crashloop_rubric())
    assert rubric.doc_id == "ecomm-order-crashloop"
    assert rubric.service_scope_match == 0.25
    assert rubric.symptom_match == 0.25
    assert rubric.root_cause_fit == 0.25
    assert rubric.coverage_notes == "matches bad image crashloop"
    assert compute_relevance_score(rubric.to_relevance()) == 1.0


def test_coerce_helper_preserves_flat_input():
    flat = {
        "doc_id": "ecomm-manager-rate-limit",
        "service_scope_match": 0.25,
        "symptom_match": 0.15,
    }
    assert coerce_runbook_per_doc_rubric(flat) is flat


def test_nested_via_runbook_eval_llm_output():
    output = RunbookEvalLLMOutput.model_validate({
        "rubrics": [
            _nested_crashloop_rubric(),
            {
                "doc_id": "ecomm-order-memory-leak",
                "relevance": {
                    "service_scope_match": 0.25,
                    "symptom_match": 0.0,
                    "telemetry_match": 0.0,
                    "exclusion_clear": 0.0,
                    "match_signals": ["ecomm-order"],
                    "conflict_signals": ["OOMKilled"],
                },
                "coverage": {
                    "root_cause_fit": 0.0,
                    "remediation_fit": 0.0,
                    "forbidden_clear": 0.0,
                    "verification_fit": 0.0,
                    "coverage_notes": "wrong runbook",
                },
            },
        ],
    })
    assert len(output.rubrics) == 2
    assert compute_relevance_score(output.rubrics[0].to_relevance()) == 1.0
    assert output.rubrics[1].symptom_match == 0.0


def test_partial_nested_relevance_only():
    rubric = RunbookPerDocRubric.model_validate({
        "doc_id": "ecomm-order-crashloop",
        "relevance": {
            "service_scope_match": 0.25,
            "symptom_match": 0.15,
        },
    })
    assert rubric.service_scope_match == 0.25
    assert rubric.symptom_match == 0.15
    assert rubric.root_cause_fit == 0.0


def test_nested_rubric_finalize_selects_crashloop():
    candidate = candidate_from_retrieval_dict({
        "doc_id": "ecomm-order-crashloop",
        "title": "CrashLoop",
        "service": "ecomm-order",
        "chunk_type": "parent",
        "content": "## 适用范围\n仅适用于服务 `ecomm-order`\n",
        "rerank_score": 1.0,
    })
    llm_output = RunbookEvalLLMOutput(rubrics=[RunbookPerDocRubric.model_validate(
        _nested_crashloop_rubric(),
    )])
    enriched = attach_llm_rubrics("ecomm-order", [candidate], llm_output)
    result = finalize_runbook_eval("ecomm-order", enriched, llm_output)
    assert result.novel_scenario is False
    assert result.selected_doc_id == "ecomm-order-crashloop"


def test_bare_rubric_array_wrapped():
    bare = [_nested_crashloop_rubric()]
    assert coerce_runbook_eval_llm_output(bare) == {"rubrics": bare}
    output = RunbookEvalLLMOutput.model_validate(bare)
    assert len(output.rubrics) == 1
    assert output.rubrics[0].service_scope_match == 0.25


def test_coerce_flat_rubric_string_signals():
    rubric = RunbookPerDocRubric.model_validate({
        "doc_id": "ecomm-order-crashloop",
        "service_scope_match": 0.25,
        "match_signals": "service:ecomm-order; symptom:CrashLoop",
        "conflict_signals": "",
    })
    assert rubric.match_signals == ["service:ecomm-order", "symptom:CrashLoop"]
    assert rubric.conflict_signals == []


def test_coerce_remediation_eval_missing_reasoning_defaults_empty():
    from app.graph.eval_schemas import RemediationEvalAssessment, coerce_remediation_eval_assessment

    model = RemediationEvalAssessment.model_validate(coerce_remediation_eval_assessment({
        "resolved": False,
        "residual_symptoms": ["QPS still low"],
    }))
    assert model.reasoning == ""
    assert model.resolved is False
    assert model.residual_symptoms == ["QPS still low"]


def test_coerce_remediation_eval_reasoning_from_explanation_alias():
    from app.graph.eval_schemas import RemediationEvalAssessment, coerce_remediation_eval_assessment

    model = RemediationEvalAssessment.model_validate(coerce_remediation_eval_assessment({
        "is_resolved": True,
        "explanation": "Metrics recovered after config patch.",
    }))
    assert model.resolved is True
    assert model.reasoning == "Metrics recovered after config patch."
    assert model.residual_symptoms == []


def test_coerce_remediation_eval_residual_symptoms_from_string():
    from app.graph.eval_schemas import RemediationEvalAssessment, coerce_remediation_eval_assessment

    model = RemediationEvalAssessment.model_validate(coerce_remediation_eval_assessment({
        "resolved": "false",
        "symptoms": "admin_api_qps still depressed",
    }))
    assert model.resolved is False
    assert model.residual_symptoms == ["admin_api_qps still depressed"]
