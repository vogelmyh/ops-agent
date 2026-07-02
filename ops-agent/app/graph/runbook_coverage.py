"""Runbook coverage — per-runbook LLM rubric scoring and code finalize (diagnose coverage phase)."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.collection import extract_symptoms
from app.graph.eval_schemas import (
    RunbookCandidate,
    RunbookEvalLLMOutput,
    RunbookPerDocRubric,
)
from app.graph.runbook_eval_policy import (
    compute_coverage_score,
    compute_relevance_score,
    finalize_runbook_eval,
    thresholds_from_settings,
)

RUNBOOK_RUBRIC_SYSTEM_PROMPT = """\
You are the runbook coverage evaluation module of an ops agent.
Score **every** retrieved runbook candidate using the rubrics below.
Do NOT copy runbook full text into your output — only doc_id, numeric scores, signals, and coverage_notes.

Output a single list `rubrics`: one entry per candidate doc_id provided (no other top-level fields).

## relevance (per doc_id)
Score each dimension 0, 0.15, or 0.25 (service_scope_match: only 0 or 0.25):
- service_scope_match: runbook 适用范围 matches incident service
  **If service does not match, set service_scope_match=0 and all other relevance dims=0.**
- symptom_match: 症状 section aligns with symptom summary
- telemetry_match: logs/k8s/metrics/operation signals align with 诊断 section
- exclusion_clear: runbook 不适用于 list does not conflict with evidence

List concrete tokens in match_signals / conflict_signals.

## fit (per doc_id, score all candidates)
Score each dimension 0, 0.15, or 0.25:
- root_cause_fit: 根因 converges with evidence
- remediation_fit: 处置 tools exist in catalog and args are inferable
- forbidden_clear: no conflict with 勿用手段
- verification_fit: 验证 criteria are observable

Optional short coverage_notes per candidate.

Do NOT output selected_doc_id, suggested_novel, novel_scenario, or reasoning — code applies thresholds after your rubric scores.
"""

_EVAL_DISPLAY_CHARS_PER_DOC = 4000

_NOVEL_SERVICES = frozenset({"ecomm-search", "ecomm-catalog", "ecomm-cache"})


def _mock_select_doc_id(service: str, candidates: list[RunbookCandidate]) -> str | None:
    from app.adapters.mock_data import get_mock_scenario

    if not candidates:
        return None
    scenario = get_mock_scenario(service)
    expected = f"{service}-{scenario}"
    for candidate in candidates:
        if candidate.doc_id == expected:
            return candidate.doc_id
    return candidates[0].doc_id


def _high_match_rubric(doc_id: str, *, notes: str = "") -> RunbookPerDocRubric:
    return RunbookPerDocRubric(
        doc_id=doc_id,
        service_scope_match=0.25,
        symptom_match=0.25,
        telemetry_match=0.25,
        exclusion_clear=0.15,
        match_signals=[f"strong match for {doc_id}"],
        root_cause_fit=0.25,
        remediation_fit=0.25,
        forbidden_clear=0.20,
        verification_fit=0.20,
        coverage_notes=notes,
    )


def _low_match_rubric(doc_id: str, *, notes: str = "") -> RunbookPerDocRubric:
    return RunbookPerDocRubric(
        doc_id=doc_id,
        service_scope_match=0.25,
        symptom_match=0.10,
        telemetry_match=0.05,
        exclusion_clear=0.05,
        conflict_signals=[f"weak match for {doc_id}"],
        root_cause_fit=0.10,
        remediation_fit=0.10,
        forbidden_clear=0.10,
        verification_fit=0.10,
        coverage_notes=notes,
    )


def mock_llm_output_oracle(
    *,
    expected_doc_id: str | None,
    expected_novel: bool,
    candidates: list[RunbookCandidate],
) -> RunbookEvalLLMOutput:
    if expected_novel:
        return RunbookEvalLLMOutput(
            rubrics=[
                _low_match_rubric(c.doc_id, notes="oracle: KB does not cover this incident")
                for c in candidates
            ],
        )
    if not expected_doc_id:
        return RunbookEvalLLMOutput(
            rubrics=[_low_match_rubric(c.doc_id) for c in candidates],
        )

    candidate_ids = [c.doc_id for c in candidates]
    if expected_doc_id not in candidate_ids:
        return RunbookEvalLLMOutput(
            rubrics=[_low_match_rubric(c.doc_id) for c in candidates],
        )

    rubrics = []
    for candidate in candidates:
        if candidate.doc_id == expected_doc_id:
            rubrics.append(_high_match_rubric(
                candidate.doc_id,
                notes="oracle: full coverage",
            ))
        else:
            rubrics.append(_low_match_rubric(candidate.doc_id))
    return RunbookEvalLLMOutput(rubrics=rubrics)


def mock_llm_output(service: str, candidates: list[RunbookCandidate]) -> RunbookEvalLLMOutput:
    if not candidates:
        return RunbookEvalLLMOutput(rubrics=[])

    if service in _NOVEL_SERVICES:
        return RunbookEvalLLMOutput(
            rubrics=[
                _low_match_rubric(c.doc_id, notes="mock: no reliable KB coverage")
                for c in candidates
            ],
        )

    from app.graph.collection import KNOWN_SERVICES

    if service not in KNOWN_SERVICES:
        return RunbookEvalLLMOutput(rubrics=[])

    doc_id = _mock_select_doc_id(service, candidates)
    if not doc_id:
        return RunbookEvalLLMOutput(rubrics=[])

    rubrics = []
    for candidate in candidates:
        if candidate.doc_id == doc_id:
            rubrics.append(_high_match_rubric(
                candidate.doc_id,
                notes="mock: runbook guides remediation",
            ))
        else:
            rubrics.append(_low_match_rubric(candidate.doc_id))
    return RunbookEvalLLMOutput(rubrics=rubrics)


def _symptoms_summary(service: str, data: dict, incident_description: str = "") -> str:
    return (
        extract_symptoms(service, data, incident_description=incident_description).strip()
        or "no clear symptoms"
    )


def _format_candidates_for_eval(candidates: list[RunbookCandidate]) -> str:
    if not candidates:
        return "(no retrieval results)"
    blocks = []
    for candidate in candidates[:3]:
        header = f"doc_id: {candidate.doc_id}"
        content = candidate.content[:_EVAL_DISPLAY_CHARS_PER_DOC]
        blocks.append(f"[{header}]\n{content}")
    return "\n\n---\n\n".join(blocks)


def runbook_support_score(
    *,
    novel_scenario: bool,
    selected: RunbookCandidate | None,
    coverage_threshold: float,
) -> float:
    """Code-owned runbook support component for confidence (max 0.25)."""
    if novel_scenario or selected is None or selected.coverage is None:
        return 0.0
    rel = compute_relevance_score(selected.relevance) if selected.relevance else 0.0
    cov = compute_coverage_score(selected.coverage, rel)
    if coverage_threshold <= 0:
        return 0.0
    return min(0.25, 0.25 * (cov / coverage_threshold))


def coverage_result_to_state(result, candidates: list[RunbookCandidate]) -> dict:
    rubrics = []
    for candidate in result.candidates:
        if candidate.relevance is not None:
            rubrics.append({
                "doc_id": candidate.doc_id,
                "relevance_score": compute_relevance_score(candidate.relevance),
                "coverage_score": (
                    compute_coverage_score(candidate.coverage, compute_relevance_score(candidate.relevance))
                    if candidate.coverage is not None
                    else None
                ),
            })
    return {
        "novel_scenario": result.novel_scenario,
        "novel_reason": result.novel_reason,
        "relevant_runbook": result.relevant_runbook,
        "selected_runbook_id": result.selected_doc_id,
        "coverage_confidence": result.coverage_confidence,
        "runbook_rubrics": rubrics,
        "runbook_eval_reasoning": result.reasoning,
        "runbook_candidates": [c.model_dump() for c in result.candidates],
    }


def evaluate_runbook_coverage(
    service: str,
    incident_description: str,
    *,
    collected_data: dict,
    candidates: list[RunbookCandidate],
    settings=None,
    golden_oracle: bool = False,
    oracle_expected_doc_id: str | None = None,
    oracle_expected_novel: bool = False,
) -> dict:
    """Score runbook candidates and finalize selection / novel flags."""
    settings = settings or get_settings()
    data = dict(collected_data)

    symptoms = _symptoms_summary(service, data, incident_description)
    candidate_ids = [c.doc_id for c in candidates]
    runbook_text = _format_candidates_for_eval(candidates)
    thresholds = thresholds_from_settings(settings)

    if settings.llm_is_mock and golden_oracle:
        llm_output = mock_llm_output_oracle(
            expected_doc_id=oracle_expected_doc_id,
            expected_novel=oracle_expected_novel,
            candidates=candidates,
        )
    elif settings.llm_is_mock:
        llm_output = mock_llm_output(service, candidates)
    else:
        llm_output = invoke_structured(
            get_chat_model(settings=settings),
            RunbookEvalLLMOutput,
            [
                SystemMessage(content=RUNBOOK_RUBRIC_SYSTEM_PROMPT),
                HumanMessage(content=(
                    f"Service: {service}\n"
                    f"Symptom summary: {symptoms}\n"
                    f"Candidate doc_ids: {candidate_ids}\n\n"
                    f"Retrieved runbooks:\n{runbook_text}"
                )),
            ],
            settings=settings,
        )

    result = finalize_runbook_eval(
        service,
        candidates,
        llm_output,
        thresholds=thresholds,
    )
    return coverage_result_to_state(result, candidates)


# Deprecated aliases (remove after one release)
run_diagnose_step1 = evaluate_runbook_coverage
step1_result_to_state = coverage_result_to_state
