"""Unit tests for runbook_eval_policy (PR1 — no eval_runbook behavior change)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("BACKEND_MODE", "mock")

pytestmark = pytest.mark.rag_coverage

from app.graph.eval_schemas import (
    RunbookCandidate,
    RunbookCoverageRubric,
    RunbookEvalLLMOutput,
    RunbookPerDocRubric,
    RunbookRelevanceRubric,
)
from app.graph.runbook_eval_policy import (
    NOVEL_AMBIGUOUS,
    NOVEL_LOW_COVERAGE,
    NOVEL_LOW_RELEVANCE,
    NOVEL_NO_RETRIEVAL,
    NOVEL_SERVICE_MISMATCH,
    attach_llm_rubrics,
    build_eval_reasoning,
    candidate_from_retrieval_dict,
    check_disambiguation,
    compute_coverage_score,
    compute_relevance_score,
    enforce_service_scope_on_rubric,
    finalize_runbook_eval,
    rank_candidates_by_relevance,
    resolve_selected_runbook,
    runbook_declared_service,
    zero_relevance_rubric,
)
from app.rag.parent import load_runbook_by_stem


def _full_rubric(doc_id: str, total: float = 1.0) -> RunbookRelevanceRubric:
    """Build a rubric that sums to *total* (service_scope must be > 0)."""
    if total <= 0:
        return zero_relevance_rubric(doc_id, "test zero")
    per = total / 4
    return RunbookRelevanceRubric(
        doc_id=doc_id,
        service_scope_match=per,
        symptom_match=per,
        telemetry_match=per,
        exclusion_clear=per,
    )


def _full_coverage(doc_id: str, total: float = 1.0) -> RunbookCoverageRubric:
    per = total / 4
    return RunbookCoverageRubric(
        doc_id=doc_id,
        root_cause_fit=per,
        remediation_fit=per,
        forbidden_clear=per,
        verification_fit=per,
    )


def _llm_output(
  *pairs: tuple[RunbookRelevanceRubric, RunbookCoverageRubric | None],
) -> RunbookEvalLLMOutput:
    rubrics = [
        RunbookPerDocRubric.from_relevance_coverage(rel, cov)
        for rel, cov in pairs
    ]
    return RunbookEvalLLMOutput(rubrics=rubrics)


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


# ---------------------------------------------------------------------------
# Service scope parsing & mismatch → 0
# ---------------------------------------------------------------------------

def test_runbook_declared_service_parses_scope_line():
    text = load_runbook_by_stem("ecomm-order-crashloop")
    assert runbook_declared_service(text or "") == "ecomm-order"


def test_service_mismatch_zeros_all_relevance_dimensions():
    candidate = _candidate("ecomm-order-crashloop", service="ecomm-manager")
    rubric = _full_rubric("ecomm-order-crashloop", total=1.0)
    enforced = enforce_service_scope_on_rubric("ecomm-manager", candidate, rubric)
    assert enforced.service_scope_match == 0.0
    assert enforced.symptom_match == 0.0
    assert enforced.telemetry_match == 0.0
    assert enforced.exclusion_clear == 0.0
    assert compute_relevance_score(enforced) == 0.0
    assert enforced.conflict_signals


def test_wrong_runbook_scope_in_content_zeros_rubric():
    content = "# Test\n\n## 适用范围\n- **仅适用于服务 `ecomm-manager`**。\n"
    candidate = RunbookCandidate(
        doc_id="fake",
        service="ecomm-order",
        content=content,
    )
    rubric = _full_rubric("fake", total=0.8)
    enforced = enforce_service_scope_on_rubric("ecomm-order", candidate, rubric)
    assert compute_relevance_score(enforced) == 0.0


def test_matching_service_keeps_rubric():
    candidate = _candidate("ecomm-order-crashloop")
    rubric = _full_rubric("ecomm-order-crashloop", total=0.8)
    enforced = enforce_service_scope_on_rubric("ecomm-order", candidate, rubric)
    assert compute_relevance_score(enforced) == pytest.approx(0.8)


def test_service_scope_match_zero_forces_total_zero_even_if_other_dims_set():
    rubric = RunbookRelevanceRubric(
        doc_id="x",
        service_scope_match=0.0,
        symptom_match=0.25,
        telemetry_match=0.25,
        exclusion_clear=0.25,
    )
    assert compute_relevance_score(rubric) == 0.0


# ---------------------------------------------------------------------------
# Coverage capped by relevance
# ---------------------------------------------------------------------------

def test_coverage_capped_by_relevance():
    cov = _full_coverage("ecomm-order-crashloop", total=1.0)
    assert compute_coverage_score(cov, relevance_score=0.6) == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# Ranking & disambiguation
# ---------------------------------------------------------------------------

def test_rank_candidates_by_relevance():
    c_low = _candidate("ecomm-order-stream-paused")
    c_low = c_low.model_copy(update={"relevance": _full_rubric(c_low.doc_id, 0.4)})
    c_high = _candidate("ecomm-order-crashloop")
    c_high = c_high.model_copy(update={"relevance": _full_rubric(c_high.doc_id, 0.9)})
    ranked = rank_candidates_by_relevance([c_low, c_high])
    assert ranked[0].doc_id == "ecomm-order-crashloop"


def test_check_disambiguation_when_close_and_below_cap():
    assert check_disambiguation(0.70, 0.62) is True


def test_check_disambiguation_clear_winner():
    assert check_disambiguation(0.85, 0.40) is False


# ---------------------------------------------------------------------------
# Candidate conversion
# ---------------------------------------------------------------------------

def test_candidate_from_retrieval_dict():
    c = candidate_from_retrieval_dict({
        "doc_id": "ecomm-manager-rate-limit",
        "service": "ecomm-manager",
        "title": "# title",
        "content": "body",
        "chunk_type": "parent",
        "vector_score": 0.55,
        "bm25_score": 3.2,
        "rerank_score": 0.77,
    })
    assert c.doc_id == "ecomm-manager-rate-limit"
    assert c.retrieval_scores.vector_score == 0.55
    assert c.retrieval_scores.bm25_score == 3.2
    assert c.retrieval_scores.rerank_score == 0.77


# ---------------------------------------------------------------------------
# finalize_runbook_eval
# ---------------------------------------------------------------------------

def test_finalize_no_candidates():
    result = finalize_runbook_eval("ecomm-order", [])
    assert result.novel_scenario is True
    assert result.novel_reason == NOVEL_NO_RETRIEVAL


def test_finalize_all_service_mismatch():
    wrong = _candidate("ecomm-manager-rate-limit", service="ecomm-manager")
    wrong = wrong.model_copy(update={"relevance": _full_rubric(wrong.doc_id, 0.9)})
    result = finalize_runbook_eval(
        "ecomm-order",
        [wrong],
        _llm_output(
            (wrong.relevance, _full_coverage(wrong.doc_id)),  # type: ignore[arg-type]
        ),
    )
    assert result.novel_scenario is True
    assert result.novel_reason == NOVEL_SERVICE_MISMATCH


def test_finalize_low_relevance():
    candidate = _candidate("ecomm-order-crashloop")
    rubric = _full_rubric(candidate.doc_id, total=0.4)
    llm = _llm_output((rubric, _full_coverage(candidate.doc_id)))
    result = finalize_runbook_eval("ecomm-order", [candidate], llm)
    assert result.novel_scenario is True
    assert result.novel_reason == NOVEL_LOW_RELEVANCE


def test_finalize_low_coverage():
    candidate = _candidate("ecomm-order-crashloop")
    rubric = _full_rubric(candidate.doc_id, total=0.8)
    coverage = _full_coverage(candidate.doc_id, total=0.5)
    llm = _llm_output((rubric, coverage))
    result = finalize_runbook_eval("ecomm-order", [candidate], llm)
    assert result.novel_scenario is True
    assert result.novel_reason == NOVEL_LOW_COVERAGE


def test_finalize_ambiguous_candidates():
    c1 = _candidate("ecomm-order-crashloop")
    c2 = _candidate("ecomm-order-memory-leak")
    r1 = _full_rubric(c1.doc_id, total=0.70)
    r2 = _full_rubric(c2.doc_id, total=0.65)
    llm = _llm_output(
        (r1, _full_coverage(c1.doc_id)),
        (r2, _full_coverage(c2.doc_id)),
    )
    result = finalize_runbook_eval("ecomm-order", [c1, c2], llm)
    assert result.novel_scenario is True
    assert result.novel_reason == NOVEL_AMBIGUOUS


def test_finalize_success_loads_runbook_from_disk():
    candidate = _candidate("ecomm-order-crashloop")
    rubric = _full_rubric(candidate.doc_id, total=0.85)
    coverage = _full_coverage(candidate.doc_id, total=0.80)
    llm = _llm_output((rubric, coverage))
    result = finalize_runbook_eval("ecomm-order", [candidate], llm)
    assert result.novel_scenario is False
    assert result.selected_doc_id == "ecomm-order-crashloop"
    assert result.relevant_runbook
    assert "勿用手段" in result.relevant_runbook
    assert result.coverage_confidence == pytest.approx(0.80)
    assert "ecomm-order-crashloop" in result.reasoning


def test_attach_llm_rubrics_enforces_service_mismatch():
    candidate = _candidate("ecomm-manager-rate-limit", service="ecomm-manager")
    rubric = _full_rubric(candidate.doc_id, total=0.9)
    llm = _llm_output((rubric, None))
    enriched = attach_llm_rubrics("ecomm-order", [candidate], llm)
    assert compute_relevance_score(enriched[0].relevance) == 0.0  # type: ignore[arg-type]


def test_resolve_selected_runbook():
    text = resolve_selected_runbook("ecomm-manager-rate-limit")
    assert text and "patch_config" in text


def test_build_eval_reasoning_success_mentions_doc_and_scores():
    candidate = _candidate("ecomm-order-crashloop")
    rubric = _full_rubric(candidate.doc_id, total=0.85)
    coverage = _full_coverage(candidate.doc_id, total=0.80)
    candidate = candidate.model_copy(update={"relevance": rubric, "coverage": coverage})
    text = build_eval_reasoning(
        None,
        ranked=[candidate],
        selected=candidate,
        selected_rel=0.85,
        coverage_score=0.80,
    )
    assert "ecomm-order-crashloop" in text
    assert "0.85" in text
    assert "0.80" in text


def test_build_eval_reasoning_low_relevance_mentions_threshold():
    candidate = _candidate("ecomm-order-crashloop")
    rubric = _full_rubric(candidate.doc_id, total=0.4)
    candidate = candidate.model_copy(update={"relevance": rubric})
    text = build_eval_reasoning(
        NOVEL_LOW_RELEVANCE,
        ranked=[candidate],
        selected_rel=0.4,
    )
    assert "below threshold" in text
    assert "ecomm-order-crashloop" in text
