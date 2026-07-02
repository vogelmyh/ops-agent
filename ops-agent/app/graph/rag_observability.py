"""Compact retrieval + coverage snapshots for logging, run_scenarios, and LangSmith."""

from __future__ import annotations

from typing import Any


def _ratings_from_candidate(candidate: dict[str, Any]) -> dict[str, str] | None:
    assessment = candidate.get("match_assessment") or {}
    if assessment.get("service_scope") is not None:
        return {
            "service_scope": assessment.get("service_scope", {}).get("rating"),
            "symptom_match": assessment.get("symptom_match", {}).get("rating"),
            "telemetry_match": assessment.get("telemetry_match", {}).get("rating"),
            "exclusion_clear": assessment.get("exclusion_clear", {}).get("rating"),
        }
    return None


def compact_runbook_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Shrink one RunbookCandidate dict for traces (omit full content)."""
    scores = candidate.get("retrieval_scores") or {}
    return {
        "doc_id": candidate.get("doc_id"),
        "service": candidate.get("service"),
        "retrieval": {
            "vector_score": scores.get("vector_score"),
            "bm25_score": scores.get("bm25_score"),
            "rerank_score": scores.get("rerank_score"),
        },
        "ratings": _ratings_from_candidate(candidate),
    }


def compact_runbook_candidates(candidates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not candidates:
        return []
    return [compact_runbook_candidate(c) for c in candidates[:5]]


def rag_snapshot_from_state(state: dict[str, Any] | None) -> dict[str, Any]:
    """Extract retrieval + coverage observability from graph state."""
    if not state:
        return {}
    relevant = state.get("relevant_runbook") or ""
    return {
        "symptom_query": state.get("symptom_query"),
        "novel_scenario": state.get("novel_scenario"),
        "novel_reason": state.get("novel_reason"),
        "selected_runbook_id": state.get("selected_runbook_id"),
        "match_gate_reason": state.get("match_gate_reason"),
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
