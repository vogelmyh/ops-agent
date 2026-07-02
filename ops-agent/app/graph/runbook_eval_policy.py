"""Runbook coverage policy: rubric enforcement, thresholds, and finalize (relevance-only)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.graph.eval_schemas import (
    RunbookCandidate,
    RunbookEvalLLMOutput,
    RunbookEvalResult,
    RunbookPerDocRubric,
    RunbookRelevanceRubric,
    RetrievalScores,
)
from app.rag.parent import load_runbook_by_stem

RELEVANCE_THRESHOLD = 0.55

_RUNBOOK_SCOPE_RE = re.compile(r"仅适用于服务\s*`([^`]+)`")

NOVEL_NO_RETRIEVAL = "no_retrieval"
NOVEL_SERVICE_MISMATCH = "service_mismatch"
NOVEL_LOW_RELEVANCE = "low_relevance"
NOVEL_INVALID_SELECTION = "invalid_selection"


@dataclass(frozen=True)
class RunbookEvalThresholds:
    relevance: float = RELEVANCE_THRESHOLD


def thresholds_from_settings(settings=None) -> RunbookEvalThresholds:
    from app.config import get_settings

    settings = settings or get_settings()
    return RunbookEvalThresholds(
        relevance=settings.runbook_relevance_threshold,
    )


def runbook_declared_service(content: str) -> str | None:
    """Parse ``## 适用范围`` service constraint from runbook markdown."""
    match = _RUNBOOK_SCOPE_RE.search(content)
    return match.group(1).strip() if match else None


def candidate_from_retrieval_dict(chunk: dict) -> RunbookCandidate:
    """Convert legacy retrieve_runbooks dict into :class:`RunbookCandidate`."""
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


def zero_relevance_rubric(doc_id: str, reason: str) -> RunbookRelevanceRubric:
    """Service mismatch or hard reject — all relevance dimensions zero."""
    return RunbookRelevanceRubric(
        doc_id=doc_id,
        service_scope_match=0.0,
        symptom_match=0.0,
        telemetry_match=0.0,
        exclusion_clear=0.0,
        conflict_signals=[reason],
    )


def enforce_service_scope_on_rubric(
    incident_service: str,
    candidate: RunbookCandidate,
    rubric: RunbookRelevanceRubric,
) -> RunbookRelevanceRubric:
    """If runbook service scope does not match incident service, force relevance to 0."""
    declared = runbook_declared_service(candidate.content)
    meta_service = (candidate.service or "").strip()

    if meta_service and meta_service != incident_service:
        return zero_relevance_rubric(
            rubric.doc_id,
            f"metadata service {meta_service!r} != incident {incident_service!r}",
        )
    if declared and declared != incident_service:
        return zero_relevance_rubric(
            rubric.doc_id,
            f"runbook scope {declared!r} != incident {incident_service!r}",
        )
    return rubric


def compute_match_score(rubric: RunbookRelevanceRubric) -> float:
    """Sum relevance rubric dimensions; service_scope_match=0 ⇒ total 0."""
    return rubric.relevance_score


# Backward-compatible alias used in tests and coverage module.
compute_relevance_score = compute_match_score


def rank_candidates_by_relevance(
    candidates: list[RunbookCandidate],
) -> list[RunbookCandidate]:
    """Return candidates sorted by match_score descending."""

    def _score(c: RunbookCandidate) -> float:
        if c.relevance is None:
            return 0.0
        return compute_match_score(c.relevance)

    return sorted(candidates, key=_score, reverse=True)


def resolve_selected_runbook(doc_id: str | None) -> str | None:
    if not doc_id:
        return None
    return load_runbook_by_stem(doc_id)


def attach_llm_rubrics(
    incident_service: str,
    candidates: list[RunbookCandidate],
    llm_output: RunbookEvalLLMOutput,
) -> list[RunbookCandidate]:
    """Merge LLM per-doc rubrics onto candidates and enforce service-scope rule."""
    rubric_by_id = {r.doc_id: r for r in llm_output.rubrics}
    enriched: list[RunbookCandidate] = []
    for candidate in candidates:
        per_doc = rubric_by_id.get(candidate.doc_id)
        if per_doc is None:
            per_doc = RunbookPerDocRubric(doc_id=candidate.doc_id)
        relevance = enforce_service_scope_on_rubric(
            incident_service,
            candidate,
            per_doc.to_relevance(),
        )
        enriched.append(
            candidate.model_copy(update={"relevance": relevance}),
        )
    return enriched


def _signal_snippet(signals: list[str], limit: int = 3) -> str:
    if not signals:
        return ""
    return "; ".join(signals[:limit])


def build_eval_reasoning(
    novel_reason: str | None,
    *,
    ranked: list[RunbookCandidate],
    selected: RunbookCandidate | None = None,
    selected_score: float = 0.0,
    thresholds: RunbookEvalThresholds | None = None,
) -> str:
    """Synthesize human-readable runbook_eval_reasoning from policy outcome and rubric signals."""
    th = thresholds or RunbookEvalThresholds()

    if novel_reason == NOVEL_NO_RETRIEVAL:
        return "No runbook candidates retrieved from knowledge base."

    if novel_reason == NOVEL_SERVICE_MISMATCH:
        conflicts = []
        for candidate in ranked[:3]:
            if candidate.relevance and candidate.relevance.conflict_signals:
                conflicts.extend(candidate.relevance.conflict_signals[:2])
        msg = "All candidates rejected: service scope does not match incident service."
        snippet = _signal_snippet(conflicts)
        return f"{msg} {snippet}" if snippet else msg

    top1 = ranked[0] if ranked else None
    top1_id = top1.doc_id if top1 else "unknown"

    if novel_reason == NOVEL_LOW_RELEVANCE:
        rel = top1.relevance if top1 else None
        signals = _signal_snippet(rel.match_signals if rel else [])
        conflicts = _signal_snippet(rel.conflict_signals if rel else [])
        msg = (
            f"Top candidate {top1_id!r} match_score {selected_score:.2f} "
            f"below threshold {th.relevance:.2f}."
        )
        if signals:
            msg += f" Match signals: {signals}."
        if conflicts:
            msg += f" Conflicts: {conflicts}."
        return msg

    if novel_reason == NOVEL_INVALID_SELECTION:
        doc_id = selected.doc_id if selected else top1_id
        return f"Could not load runbook file for selected candidate {doc_id!r}."

    if selected is None:
        return "Runbook coverage evaluation completed."

    rel = selected.relevance
    signals = _signal_snippet(rel.match_signals if rel else [])
    msg = f"Selected {selected.doc_id!r}: match_score {selected_score:.2f}."
    if signals:
        msg += f" Match signals: {signals}."
    return msg


def finalize_runbook_eval(
    incident_service: str,
    candidates: list[RunbookCandidate],
    llm_output: RunbookEvalLLMOutput | None = None,
    *,
    thresholds: RunbookEvalThresholds | None = None,
) -> RunbookEvalResult:
    """Apply thresholds: rank by match_score, top1 wins if above threshold.

    Selection and reasoning are code-owned; LLM supplies per-doc rubric scores only.
    """
    th = thresholds or RunbookEvalThresholds()

    if not candidates:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_NO_RETRIEVAL,
            reasoning=build_eval_reasoning(
                NOVEL_NO_RETRIEVAL,
                ranked=[],
                thresholds=th,
            ),
        )

    if llm_output is not None:
        candidates = attach_llm_rubrics(incident_service, candidates, llm_output)
    else:
        candidates = [
            c.model_copy(
                update={
                    "relevance": enforce_service_scope_on_rubric(
                        incident_service,
                        c,
                        c.relevance or RunbookRelevanceRubric(doc_id=c.doc_id),
                    ),
                },
            )
            for c in candidates
        ]

    ranked = rank_candidates_by_relevance(candidates)
    scores = [
        compute_match_score(c.relevance)  # type: ignore[arg-type]
        for c in ranked
        if c.relevance is not None
    ]
    if not scores or max(scores) <= 0:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_SERVICE_MISMATCH,
            candidates=ranked,
            reasoning=build_eval_reasoning(
                NOVEL_SERVICE_MISMATCH,
                ranked=ranked,
                thresholds=th,
            ),
        )

    top1 = ranked[0]
    top1_score = compute_match_score(top1.relevance)  # type: ignore[arg-type]

    if top1_score < th.relevance:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_LOW_RELEVANCE,
            candidates=ranked,
            reasoning=build_eval_reasoning(
                NOVEL_LOW_RELEVANCE,
                ranked=ranked,
                selected_score=top1_score,
                thresholds=th,
            ),
        )

    selected_id = top1.doc_id
    selected = top1

    full_text = resolve_selected_runbook(selected_id)
    if not full_text:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_INVALID_SELECTION,
            selected_doc_id=selected_id,
            candidates=ranked,
            reasoning=build_eval_reasoning(
                NOVEL_INVALID_SELECTION,
                ranked=ranked,
                selected=selected,
                thresholds=th,
            ),
        )

    return RunbookEvalResult(
        novel_scenario=False,
        selected_doc_id=selected_id,
        relevant_runbook=full_text,
        match_score=top1_score,
        candidates=ranked,
        reasoning=build_eval_reasoning(
            None,
            ranked=ranked,
            selected=selected,
            selected_score=top1_score,
            thresholds=th,
        ),
    )


# Preferred name for coverage finalize (alias).
finalize_runbook_coverage = finalize_runbook_eval
