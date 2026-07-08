"""Unit tests for runbook_match_policy (CoT categorical finalize)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("BACKEND_MODE", "mock")

pytestmark = pytest.mark.rag_coverage

from app.graph.categorical_rubric import DimensionAssessment
from app.graph.eval_schemas import (
    RunbookCandidate,
    RunbookEvalLLMOutput,
    RunbookMatchAssessment,
)
from app.graph.runbook_match_policy import (
    NOVEL_LOW_MATCH,
    NOVEL_NO_RETRIEVAL,
    NOVEL_SERVICE_MISMATCH,
    RunbookMatchPolicy,
    attach_llm_assessments,
    build_match_gate_reason,
    candidate_from_retrieval_dict,
    enforce_service_scope_on_assessment,
    finalize_runbook_match,
    is_candidate_selectable,
    resolve_selected_runbook,
    runbook_declared_service,
)
from app.rag.parent import load_runbook_by_stem


def _dim(reasoning: str, rating: str) -> DimensionAssessment:
    return DimensionAssessment(reasoning=reasoning, rating=rating)  # type: ignore[arg-type]


def _assessment(
    doc_id: str,
    *,
    service_scope: str = "PASS",
    symptom: str = "PASS",
    telemetry: str = "PASS",
    exclusion: str = "PASS",
) -> RunbookMatchAssessment:
    return RunbookMatchAssessment(
        doc_id=doc_id,
        service_scope=_dim("scope", service_scope),
        symptom_match=_dim("symptom", symptom),
        telemetry_match=_dim("telemetry", telemetry),
        exclusion_clear=_dim("exclusion", exclusion),
    )


def _llm_output(*assessments: RunbookMatchAssessment) -> RunbookEvalLLMOutput:
    return RunbookEvalLLMOutput(rubrics=list(assessments))


def _candidate(
    doc_id: str,
    *,
    service: str = "ecomm-order",
    content: str | None = None,
) -> RunbookCandidate:
    text = content if content is not None else (load_runbook_by_stem(doc_id) or "")
    return RunbookCandidate(
        doc_id=doc_id,
        service=service,
        content=text,
        chunk_type="parent",
    )


def test_runbook_declared_service_parses_scope_line():
    text = load_runbook_by_stem("ecomm-order-crashloop")
    assert runbook_declared_service(text or "") == "ecomm-order"


def test_service_mismatch_forces_fail():
    candidate = _candidate("ecomm-order-crashloop", service="ecomm-manager")
    assessment = _assessment(candidate.doc_id)
    enforced = enforce_service_scope_on_assessment("ecomm-manager", candidate, assessment)
    assert enforced.service_scope.rating == "FAIL"
    assert enforced.symptom_match.rating == "FAIL"


def test_symptom_partial_not_selectable():
    assessment = _assessment("x", symptom="PARTIAL")
    assert is_candidate_selectable(assessment) is False


def test_symptom_pass_selectable():
    assessment = _assessment("x")
    assert is_candidate_selectable(assessment) is True


def test_exclusion_fail_not_selectable():
    assessment = _assessment("x", exclusion="FAIL")
    assert is_candidate_selectable(assessment) is False


def test_finalize_no_candidates():
    result = finalize_runbook_match("ecomm-order", [])
    assert result.runbook_available is False
    assert result.runbook_unavailable_reason == NOVEL_NO_RETRIEVAL


def test_finalize_all_service_mismatch():
    wrong = _candidate("ecomm-manager-rate-limit", service="ecomm-manager")
    assessment = _assessment(wrong.doc_id)
    result = finalize_runbook_match(
        "ecomm-order",
        [wrong],
        _llm_output(assessment),
    )
    assert result.runbook_available is False
    assert result.runbook_unavailable_reason == NOVEL_SERVICE_MISMATCH


def test_finalize_low_match():
    candidate = _candidate("ecomm-order-crashloop")
    assessment = _assessment(candidate.doc_id, symptom="FAIL")
    result = finalize_runbook_match("ecomm-order", [candidate], _llm_output(assessment))
    assert result.runbook_available is False
    assert result.runbook_unavailable_reason == NOVEL_LOW_MATCH


def test_finalize_close_scores_top1_wins():
    c1 = _candidate("ecomm-order-crashloop")
    c2 = _candidate("ecomm-order-memory-leak")
    a1 = _assessment(c1.doc_id, telemetry="PARTIAL")
    a2 = _assessment(c2.doc_id, telemetry="FAIL")
    result = finalize_runbook_match("ecomm-order", [c1, c2], _llm_output(a1, a2))
    assert result.runbook_available is True
    assert result.selected_doc_id == "ecomm-order-crashloop"


def test_finalize_success_loads_runbook_from_disk():
    candidate = _candidate("ecomm-order-crashloop")
    assessment = _assessment(candidate.doc_id)
    result = finalize_runbook_match("ecomm-order", [candidate], _llm_output(assessment))
    assert result.runbook_available is True
    assert result.selected_doc_id == "ecomm-order-crashloop"
    assert result.relevant_runbook
    assert "勿用手段" in result.relevant_runbook


def test_attach_llm_assessments_enforces_service_mismatch():
    candidate = _candidate("ecomm-manager-rate-limit", service="ecomm-manager")
    assessment = _assessment(candidate.doc_id)
    enriched = attach_llm_assessments(
        "ecomm-order",
        [candidate],
        _llm_output(assessment),
    )
    assert enriched[0].match_assessment.service_scope.rating == "FAIL"  # type: ignore[union-attr]


def test_resolve_selected_runbook():
    text = resolve_selected_runbook("ecomm-manager-rate-limit")
    assert text and "patch_config" in text


def test_build_match_gate_reason_low_match():
    candidate = _candidate("ecomm-order-crashloop")
    candidate = candidate.model_copy(
        update={"match_assessment": _assessment(candidate.doc_id, symptom="FAIL")},
    )
    text = build_match_gate_reason(NOVEL_LOW_MATCH, ranked=[candidate])
    assert "not selectable" in text
    assert "symptom_match" in text


def test_candidate_from_retrieval_dict():
    c = candidate_from_retrieval_dict({
        "doc_id": "ecomm-manager-rate-limit",
        "service": "ecomm-manager",
        "title": "# title",
        "content": "body",
        "chunk_type": "parent",
        "rerank_score": 0.77,
    })
    assert c.doc_id == "ecomm-manager-rate-limit"
    assert c.retrieval_scores.rerank_score == 0.77
