"""Runbook match — CoT categorical rubric + deterministic finalize."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.graph.categorical_rubric import DimensionAssessment, Rating
from app.graph.eval_schemas import (
    RunbookCandidate,
    RunbookEvalLLMOutput,
    RunbookEvalResult,
    RunbookMatchAssessment,
    RetrievalScores,
)
from app.rag.parent import load_runbook_by_stem

_RUNBOOK_SCOPE_RE = re.compile(r"仅适用于服务\s*`([^`]+)`")

NOVEL_NO_RETRIEVAL = "no_retrieval"
NOVEL_SERVICE_MISMATCH = "service_mismatch"
NOVEL_LOW_MATCH = "low_match"
NOVEL_INVALID_SELECTION = "invalid_selection"

# Backward-compatible alias (deprecated).
NOVEL_LOW_RELEVANCE = NOVEL_LOW_MATCH

MATCH_DIMS = (
    "service_scope",
    "symptom_match",
    "telemetry_match",
    "exclusion_clear",
)


@dataclass(frozen=True)
class RunbookMatchPolicy:
    require_pass: frozenset[str] = frozenset({"symptom_match"})
    hard_fail_dims: frozenset[str] = frozenset({"service_scope", "exclusion_clear"})
    max_partial: int = 1
    min_pass_count: int = 2


def policy_from_settings(settings=None) -> RunbookMatchPolicy:
    from app.config import get_settings

    settings = settings or get_settings()
    return RunbookMatchPolicy(
        max_partial=settings.runbook_match_max_partial,
        min_pass_count=settings.runbook_match_min_pass_count,
    )


def runbook_declared_service(content: str) -> str | None:
    match = _RUNBOOK_SCOPE_RE.search(content)
    return match.group(1).strip() if match else None


def candidate_from_retrieval_dict(chunk: dict) -> RunbookCandidate:
    return RunbookCandidate(
        doc_id=chunk.get("doc_id", ""),
        service=chunk.get("service", ""),
        title=chunk.get("title", ""),
        content=chunk.get("content", ""),
        chunk_type=chunk.get("chunk_type", "parent"),
        retrieval_scores=RetrievalScores(
            vector_score=chunk.get("vector_score"),
            bm25_score=chunk.get("bm25_score"),
            rerank_score=chunk.get("rerank_score") or chunk.get("score"),
        ),
    )


def candidates_from_retrieval_dicts(chunks: list[dict]) -> list[RunbookCandidate]:
    return [candidate_from_retrieval_dict(c) for c in chunks]


def _fail_dim(reason: str) -> DimensionAssessment:
    return DimensionAssessment(reasoning=reason, rating="FAIL")


def _forced_service_mismatch_assessment(doc_id: str, reason: str) -> RunbookMatchAssessment:
    fail = _fail_dim(reason)
    return RunbookMatchAssessment(
        doc_id=doc_id,
        service_scope=fail,
        symptom_match=fail,
        telemetry_match=fail,
        exclusion_clear=fail,
    )


def enforce_service_scope_on_assessment(
    incident_service: str,
    candidate: RunbookCandidate,
    assessment: RunbookMatchAssessment,
) -> RunbookMatchAssessment:
    declared = runbook_declared_service(candidate.content)
    meta_service = (candidate.service or "").strip()

    if meta_service and meta_service != incident_service:
        return _forced_service_mismatch_assessment(
            assessment.doc_id,
            f"code: metadata service {meta_service!r} != incident {incident_service!r}",
        )
    if declared and declared != incident_service:
        return _forced_service_mismatch_assessment(
            assessment.doc_id,
            f"code: runbook scope {declared!r} != incident {incident_service!r}",
        )
    return assessment


def dimension_ratings(assessment: RunbookMatchAssessment) -> dict[str, Rating]:
    return {
        "service_scope": assessment.service_scope.rating,
        "symptom_match": assessment.symptom_match.rating,
        "telemetry_match": assessment.telemetry_match.rating,
        "exclusion_clear": assessment.exclusion_clear.rating,
    }


def is_candidate_selectable(
    assessment: RunbookMatchAssessment,
    *,
    policy: RunbookMatchPolicy | None = None,
) -> bool:
    policy = policy or RunbookMatchPolicy()
    ratings = dimension_ratings(assessment)

    for dim in policy.hard_fail_dims:
        if ratings.get(dim) == "FAIL":
            return False
    if ratings.get("symptom_match") == "FAIL" or ratings.get("telemetry_match") == "FAIL":
        return False
    for dim in policy.require_pass:
        if ratings.get(dim) != "PASS":
            return False

    all_ratings = list(ratings.values())
    if all_ratings.count("PARTIAL") > policy.max_partial:
        return False
    if all_ratings.count("PASS") < policy.min_pass_count:
        return False
    return True


def selectable_failure_reason(
    assessment: RunbookMatchAssessment,
    *,
    policy: RunbookMatchPolicy | None = None,
) -> str:
    policy = policy or RunbookMatchPolicy()
    ratings = dimension_ratings(assessment)
    parts: list[str] = []
    for dim in policy.hard_fail_dims:
        if ratings.get(dim) == "FAIL":
            dim_obj = getattr(assessment, dim)
            parts.append(f"{dim}=FAIL ({dim_obj.reasoning[:120]})")
    for dim in ("symptom_match", "telemetry_match"):
        if ratings.get(dim) == "FAIL":
            dim_obj = getattr(assessment, dim)
            parts.append(f"{dim}=FAIL ({dim_obj.reasoning[:120]})")
    for dim in policy.require_pass:
        if ratings.get(dim) != "PASS":
            dim_obj = getattr(assessment, dim)
            parts.append(f"{dim}={ratings.get(dim)} (required PASS; {dim_obj.reasoning[:80]})")
    partial_count = list(ratings.values()).count("PARTIAL")
    if partial_count > policy.max_partial:
        parts.append(f"PARTIAL count {partial_count} > max {policy.max_partial}")
    pass_count = list(ratings.values()).count("PASS")
    if pass_count < policy.min_pass_count:
        parts.append(f"PASS count {pass_count} < min {policy.min_pass_count}")
    return "; ".join(parts) if parts else "selectable gate failed"


def rank_key(candidate: RunbookCandidate, assessment: RunbookMatchAssessment) -> tuple:
    ratings = list(dimension_ratings(assessment).values())
    rerank = candidate.retrieval_scores.rerank_score or 0.0
    return (ratings.count("PASS"), -ratings.count("PARTIAL"), rerank)


def rank_selectable_candidates(
    candidates: list[RunbookCandidate],
) -> list[RunbookCandidate]:
    def _key(c: RunbookCandidate) -> tuple:
        if c.match_assessment is None:
            return (0, 0, 0.0)
        return rank_key(c, c.match_assessment)

    return sorted(candidates, key=_key, reverse=True)


def attach_llm_assessments(
    incident_service: str,
    candidates: list[RunbookCandidate],
    llm_output: RunbookEvalLLMOutput,
) -> list[RunbookCandidate]:
    by_id = {r.doc_id: r for r in llm_output.rubrics}
    enriched: list[RunbookCandidate] = []
    for candidate in candidates:
        assessment = by_id.get(candidate.doc_id)
        if assessment is None:
            assessment = RunbookMatchAssessment(doc_id=candidate.doc_id)
        assessment = enforce_service_scope_on_assessment(
            incident_service,
            candidate,
            assessment,
        )
        enriched.append(candidate.model_copy(update={"match_assessment": assessment}))
    return enriched


def resolve_selected_runbook(doc_id: str | None) -> str | None:
    if not doc_id:
        return None
    return load_runbook_by_stem(doc_id)


def build_match_gate_reason(
    novel_reason: str | None,
    *,
    ranked: list[RunbookCandidate],
    selected: RunbookCandidate | None = None,
    policy: RunbookMatchPolicy | None = None,
) -> str:
    policy = policy or RunbookMatchPolicy()

    if novel_reason == NOVEL_NO_RETRIEVAL:
        return "No runbook candidates retrieved from knowledge base."

    if novel_reason == NOVEL_SERVICE_MISMATCH:
        return "All candidates rejected: service scope does not match incident service."

    top1 = ranked[0] if ranked else None
    top1_id = top1.doc_id if top1 else "unknown"

    if novel_reason == NOVEL_LOW_MATCH:
        if top1 and top1.match_assessment:
            why = selectable_failure_reason(top1.match_assessment, policy=policy)
            return f"Top candidate {top1_id!r} not selectable: {why}"
        return f"Top candidate {top1_id!r} not selectable under match policy."

    if novel_reason == NOVEL_INVALID_SELECTION:
        doc_id = selected.doc_id if selected else top1_id
        return f"Could not load runbook file for selected candidate {doc_id!r}."

    if selected is None or selected.match_assessment is None:
        return "Runbook match evaluation completed."

    ratings = dimension_ratings(selected.match_assessment)
    summary = ", ".join(f"{k}={v}" for k, v in ratings.items())
    return f"Selected {selected.doc_id!r}: {summary}."


def finalize_runbook_match(
    incident_service: str,
    candidates: list[RunbookCandidate],
    llm_output: RunbookEvalLLMOutput | None = None,
    *,
    policy: RunbookMatchPolicy | None = None,
) -> RunbookEvalResult:
    policy = policy or RunbookMatchPolicy()

    if not candidates:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_NO_RETRIEVAL,
            reasoning=build_match_gate_reason(NOVEL_NO_RETRIEVAL, ranked=[]),
        )

    if llm_output is not None:
        candidates = attach_llm_assessments(incident_service, candidates, llm_output)
    else:
        candidates = [
            c.model_copy(
                update={
                    "match_assessment": enforce_service_scope_on_assessment(
                        incident_service,
                        c,
                        c.match_assessment or RunbookMatchAssessment(doc_id=c.doc_id),
                    ),
                },
            )
            for c in candidates
        ]

    all_scope_fail = all(
        c.match_assessment is not None
        and c.match_assessment.service_scope.rating == "FAIL"
        for c in candidates
    )
    if all_scope_fail:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_SERVICE_MISMATCH,
            candidates=candidates,
            reasoning=build_match_gate_reason(
                NOVEL_SERVICE_MISMATCH,
                ranked=candidates,
                policy=policy,
            ),
        )

    selectable = [c for c in candidates if c.match_assessment and is_candidate_selectable(
        c.match_assessment, policy=policy,
    )]
    ranked = rank_selectable_candidates(selectable) if selectable else rank_selectable_candidates(candidates)

    if not selectable:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_LOW_MATCH,
            candidates=ranked,
            reasoning=build_match_gate_reason(
                NOVEL_LOW_MATCH,
                ranked=ranked,
                policy=policy,
            ),
        )

    top1 = ranked[0]
    selected_id = top1.doc_id
    full_text = resolve_selected_runbook(selected_id)
    if not full_text:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_INVALID_SELECTION,
            selected_doc_id=selected_id,
            candidates=ranked,
            reasoning=build_match_gate_reason(
                NOVEL_INVALID_SELECTION,
                ranked=ranked,
                selected=top1,
                policy=policy,
            ),
        )

    return RunbookEvalResult(
        novel_scenario=False,
        selected_doc_id=selected_id,
        relevant_runbook=full_text,
        candidates=ranked,
        reasoning=build_match_gate_reason(
            None,
            ranked=ranked,
            selected=top1,
            policy=policy,
        ),
    )


# Preferred aliases for coverage phase.
finalize_runbook_eval = finalize_runbook_match
finalize_runbook_coverage = finalize_runbook_match
