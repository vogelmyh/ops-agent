"""Compact RAG / eval_runbook snapshots for logging, run_scenarios, and LangSmith."""

from __future__ import annotations

from typing import Any


def _relevance_score_from_dict(relevance: dict[str, Any]) -> float | None:
    if not relevance:
        return None
    if relevance.get("relevance_score") is not None:
        return relevance["relevance_score"]
    if relevance.get("service_scope_match", 0) <= 0:
        return 0.0
    total = (
        relevance.get("service_scope_match", 0)
        + relevance.get("symptom_match", 0)
        + relevance.get("telemetry_match", 0)
        + relevance.get("exclusion_clear", 0)
    )
    return min(1.0, float(total))


def _coverage_score_from_dict(coverage: dict[str, Any]) -> float | None:
    if not coverage:
        return None
    if coverage.get("coverage_confidence") is not None:
        return coverage["coverage_confidence"]
    total = (
        coverage.get("root_cause_fit", 0)
        + coverage.get("remediation_fit", 0)
        + coverage.get("forbidden_clear", 0)
        + coverage.get("verification_fit", 0)
    )
    return min(1.0, float(total))


def compact_runbook_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Shrink one :class:`RunbookCandidate` dict for traces (omit full content)."""
    relevance = candidate.get("relevance") or {}
    coverage = candidate.get("coverage") or {}
    scores = candidate.get("retrieval_scores") or {}
    return {
        "doc_id": candidate.get("doc_id"),
        "service": candidate.get("service"),
        "retrieval": {
            "vector_score": scores.get("vector_score"),
            "bm25_score": scores.get("bm25_score"),
            "rerank_score": scores.get("rerank_score"),
        },
        "relevance_score": _relevance_score_from_dict(relevance),
        "coverage_confidence": _coverage_score_from_dict(coverage),
        "match_signals": (relevance.get("match_signals") or [])[:5],
        "conflict_signals": (relevance.get("conflict_signals") or [])[:5],
    }


def compact_runbook_candidates(candidates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not candidates:
        return []
    return [compact_runbook_candidate(c) for c in candidates[:5]]


def rag_snapshot_from_state(state: dict[str, Any] | None) -> dict[str, Any]:
    """Extract eval_runbook + retrieval observability from graph state."""
    if not state:
        return {}
    relevant = state.get("relevant_runbook") or ""
    return {
        "symptom_query": state.get("symptom_query"),
        "novel_scenario": state.get("novel_scenario"),
        "novel_reason": state.get("novel_reason"),
        "selected_runbook_id": state.get("selected_runbook_id"),
        "coverage_confidence": state.get("coverage_confidence"),
        "runbook_eval_reasoning": state.get("runbook_eval_reasoning"),
        "relevant_runbook_title": _title_from_runbook(relevant),
        "relevant_runbook_chars": len(relevant) if relevant else 0,
        "runbook_candidates": compact_runbook_candidates(state.get("runbook_candidates")),
    }


def _title_from_runbook(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def merge_rag_into_response(
    response: dict[str, Any],
    rag: dict[str, Any],
) -> dict[str, Any]:
    """Overlay RAG snapshot onto a response dict (response wins for overlapping keys)."""
    merged = dict(rag)
    merged.update(response)
    return merged
