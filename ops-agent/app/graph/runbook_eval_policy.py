"""Deprecated shim — use app.graph.runbook_match_policy."""

from app.graph.runbook_match_policy import (  # noqa: F401
    NOVEL_INVALID_SELECTION,
    NOVEL_LOW_MATCH,
    NOVEL_LOW_RELEVANCE,
    NOVEL_NO_RETRIEVAL,
    NOVEL_SERVICE_MISMATCH,
    attach_llm_assessments,
    build_match_gate_reason,
    candidate_from_retrieval_dict,
    candidates_from_retrieval_dicts,
    enforce_service_scope_on_assessment,
    finalize_runbook_coverage,
    finalize_runbook_eval,
    finalize_runbook_match,
    is_candidate_selectable,
    policy_from_settings,
    resolve_selected_runbook,
    runbook_declared_service,
)

# Backward-compatible names for older tests/imports.
attach_llm_rubrics = attach_llm_assessments
build_eval_reasoning = build_match_gate_reason
rank_candidates_by_relevance = lambda candidates: candidates  # noqa: E731

__all__ = [
    "NOVEL_INVALID_SELECTION",
    "NOVEL_LOW_MATCH",
    "NOVEL_LOW_RELEVANCE",
    "NOVEL_NO_RETRIEVAL",
    "NOVEL_SERVICE_MISMATCH",
    "attach_llm_assessments",
    "attach_llm_rubrics",
    "build_eval_reasoning",
    "build_match_gate_reason",
    "candidate_from_retrieval_dict",
    "candidates_from_retrieval_dicts",
    "enforce_service_scope_on_assessment",
    "finalize_runbook_coverage",
    "finalize_runbook_eval",
    "finalize_runbook_match",
    "is_candidate_selectable",
    "policy_from_settings",
    "rank_candidates_by_relevance",
    "resolve_selected_runbook",
    "runbook_declared_service",
]
