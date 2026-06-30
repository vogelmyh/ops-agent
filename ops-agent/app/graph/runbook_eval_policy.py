"""Runbook coverage policy: rubric enforcement, thresholds, and finalize (PR1 — retrieval-agnostic)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.graph.eval_schemas import (
    RunbookCandidate,
    RunbookCoverageRubric,
    RunbookEvalLLMOutput,
    RunbookEvalResult,
    RunbookPerDocRubric,
    RunbookRelevanceRubric,
    RetrievalScores,
)
from app.rag.parent import load_runbook_by_stem

# Thresholds — configurable via Settings; tuned in test_runbook_eval_policy / test_rag_integration.
RELEVANCE_THRESHOLD = 0.55
COVERAGE_THRESHOLD = 0.70
DISAMBIGUATION_GAP = 0.12
DISAMBIGUATION_TOP1_CAP = 0.75

_RUNBOOK_SCOPE_RE = re.compile(r"仅适用于服务\s*`([^`]+)`")

NOVEL_NO_RETRIEVAL = "no_retrieval"
NOVEL_SERVICE_MISMATCH = "service_mismatch"
NOVEL_LOW_RELEVANCE = "low_relevance"
NOVEL_LOW_COVERAGE = "low_coverage"
NOVEL_AMBIGUOUS = "ambiguous_candidates"
NOVEL_INVALID_SELECTION = "invalid_selection"


@dataclass(frozen=True)
class RunbookEvalThresholds:
    relevance: float = RELEVANCE_THRESHOLD
    coverage: float = COVERAGE_THRESHOLD
    disambiguation_gap: float = DISAMBIGUATION_GAP
    disambiguation_top1_cap: float = DISAMBIGUATION_TOP1_CAP


def thresholds_from_settings(settings=None) -> RunbookEvalThresholds:
    from app.config import get_settings

    settings = settings or get_settings()
    return RunbookEvalThresholds(
        relevance=settings.runbook_relevance_threshold,
        coverage=settings.runbook_coverage_threshold,
        disambiguation_gap=settings.runbook_disambiguation_gap,
        disambiguation_top1_cap=settings.runbook_disambiguation_top1_cap,
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


def compute_relevance_score(rubric: RunbookRelevanceRubric) -> float:
    """Sum rubric dimensions; service_scope_match=0 ⇒ total 0."""
    return rubric.relevance_score


def compute_coverage_score(
    coverage: RunbookCoverageRubric,
    relevance_score: float,
) -> float:
    """Coverage cannot exceed relevance."""
    return min(coverage.coverage_confidence, relevance_score)


def rank_candidates_by_relevance(
    candidates: list[RunbookCandidate],
) -> list[RunbookCandidate]:
    """Return candidates sorted by relevance_score descending."""

    def _score(c: RunbookCandidate) -> float:
        if c.relevance is None:
            return 0.0
        return compute_relevance_score(c.relevance)

    return sorted(candidates, key=_score, reverse=True)


def check_disambiguation(
    top1_score: float,
    top2_score: float | None,
    thresholds: RunbookEvalThresholds | None = None,
) -> bool:
    """True when top two candidates are too close to auto-select."""
    th = thresholds or RunbookEvalThresholds()
    if top2_score is None:
        return False
    gap = top1_score - top2_score
    return gap < th.disambiguation_gap and top1_score < th.disambiguation_top1_cap


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
        coverage = per_doc.to_coverage()
        enriched.append(
            candidate.model_copy(update={"relevance": relevance, "coverage": coverage}),
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
    selected_rel: float = 0.0,
    top2_rel: float | None = None,
    coverage_score: float | None = None,
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
            f"Top candidate {top1_id!r} relevance {selected_rel:.2f} "
            f"below threshold {th.relevance:.2f}."
        )
        if signals:
            msg += f" Match signals: {signals}."
        if conflicts:
            msg += f" Conflicts: {conflicts}."
        return msg

    if novel_reason == NOVEL_AMBIGUOUS:
        top2_id = ranked[1].doc_id if len(ranked) > 1 else "unknown"
        gap = selected_rel - (top2_rel or 0.0)
        return (
            f"Cannot disambiguate: {top1_id!r} ({selected_rel:.2f}) vs "
            f"{top2_id!r} ({top2_rel:.2f}); gap {gap:.2f} < {th.disambiguation_gap} "
            f"and top relevance < {th.disambiguation_top1_cap:.2f}."
        )

    if novel_reason == NOVEL_LOW_COVERAGE:
        doc_id = selected.doc_id if selected else top1_id
        cov = selected.coverage if selected else (top1.coverage if top1 else None)
        notes = (cov.coverage_notes or "").strip() if cov else ""
        score = coverage_score if coverage_score is not None else 0.0
        msg = (
            f"Candidate {doc_id!r} coverage {score:.2f} "
            f"below threshold {th.coverage:.2f} (relevance {selected_rel:.2f})."
        )
        if notes:
            msg += f" Notes: {notes}."
        return msg

    if novel_reason == NOVEL_INVALID_SELECTION:
        doc_id = selected.doc_id if selected else top1_id
        return f"Could not load runbook file for selected candidate {doc_id!r}."

    if selected is None:
        return "Runbook coverage evaluation completed."

    rel = selected.relevance
    cov = selected.coverage
    signals = _signal_snippet(rel.match_signals if rel else [])
    notes = (cov.coverage_notes or "").strip() if cov else ""
    cov_display = coverage_score if coverage_score is not None else 0.0
    msg = (
        f"Selected {selected.doc_id!r}: relevance {selected_rel:.2f}, "
        f"coverage {cov_display:.2f}."
    )
    if signals:
        msg += f" Match signals: {signals}."
    if notes:
        msg += f" {notes}"
    return msg


def finalize_runbook_eval(
    incident_service: str,
    candidates: list[RunbookCandidate],
    llm_output: RunbookEvalLLMOutput | None = None,
    *,
    thresholds: RunbookEvalThresholds | None = None,
) -> RunbookEvalResult:
    """Apply thresholds and rules to produce novel_scenario and selected runbook.

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
        compute_relevance_score(c.relevance)  # type: ignore[arg-type]
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
    top1_rel = compute_relevance_score(top1.relevance)  # type: ignore[arg-type]
    top2_rel = (
        compute_relevance_score(ranked[1].relevance)  # type: ignore[arg-type]
        if len(ranked) > 1 and ranked[1].relevance is not None
        else None
    )

    if top1_rel < th.relevance:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_LOW_RELEVANCE,
            candidates=ranked,
            reasoning=build_eval_reasoning(
                NOVEL_LOW_RELEVANCE,
                ranked=ranked,
                selected_rel=top1_rel,
                thresholds=th,
            ),
        )

    if check_disambiguation(top1_rel, top2_rel, th):
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_AMBIGUOUS,
            candidates=ranked,
            reasoning=build_eval_reasoning(
                NOVEL_AMBIGUOUS,
                ranked=ranked,
                selected_rel=top1_rel,
                top2_rel=top2_rel,
                thresholds=th,
            ),
        )

    selected_id = top1.doc_id
    selected = top1
    selected_rel = top1_rel

    coverage_rubric = selected.coverage
    if coverage_rubric is None:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_LOW_COVERAGE,
            candidates=ranked,
            reasoning=build_eval_reasoning(
                NOVEL_LOW_COVERAGE,
                ranked=ranked,
                selected=selected,
                selected_rel=selected_rel,
                thresholds=th,
            ),
        )

    coverage_score = compute_coverage_score(coverage_rubric, selected_rel)
    if coverage_score < th.coverage:
        return RunbookEvalResult(
            novel_scenario=True,
            novel_reason=NOVEL_LOW_COVERAGE,
            selected_doc_id=selected_id,
            coverage_confidence=coverage_score,
            candidates=ranked,
            reasoning=build_eval_reasoning(
                NOVEL_LOW_COVERAGE,
                ranked=ranked,
                selected=selected,
                selected_rel=selected_rel,
                coverage_score=coverage_score,
                thresholds=th,
            ),
        )

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
        coverage_confidence=coverage_score,
        candidates=ranked,
        reasoning=build_eval_reasoning(
            None,
            ranked=ranked,
            selected=selected,
            selected_rel=selected_rel,
            coverage_score=coverage_score,
            thresholds=th,
        ),
    )
