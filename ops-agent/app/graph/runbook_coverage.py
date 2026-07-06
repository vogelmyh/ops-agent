"""Runbook coverage — per-runbook CoT categorical rubric and code finalize."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.collection import extract_symptoms
from app.graph.categorical_rubric import DimensionAssessment
from app.graph.eval_schemas import (
    RunbookCandidate,
    RunbookEvalLLMOutput,
    RunbookMatchAssessment,
)
from app.graph.runbook_match_policy import (
    finalize_runbook_match,
    policy_from_settings,
)
from app.llm.provider import get_chat_model, invoke_structured

RUNBOOK_RUBRIC_SYSTEM_PROMPT = """\
You are the runbook coverage evaluation module of an ops agent.
Evaluate **every** retrieved runbook candidate. Do NOT copy full runbook text into output.

Output a single list `rubrics`: one entry per candidate doc_id (no other top-level fields).

For EACH dimension on EACH candidate you MUST:
1. Write reasoning first — cite concrete tokens from symptom summary, telemetry, and runbook sections.
2. Then assign rating — exactly one of: PASS, PARTIAL, FAIL.

[service_scope]
- PASS: runbook 适用范围 matches incident service.
- PARTIAL: (do not use — scope is binary; use FAIL if mismatch)
- FAIL: service scope does not match incident.

[symptom_match]
- PASS: 症状 section clearly aligns with symptom summary keywords.
- PARTIAL: related but missing discriminating symptom tokens.
- FAIL: symptom section describes a different failure mode.

[telemetry_match]
- PASS: logs/k8s/metrics/operation signals align with runbook 诊断 section.
- PARTIAL: partial overlap or missing one key signal.
- FAIL: telemetry contradicts runbook diagnosis path.

[exclusion_clear]
- PASS: runbook 不适用于 list does not conflict with evidence.
- PARTIAL: minor tension but not disqualifying.
- FAIL: evidence matches an explicit exclusion in the runbook.

Do NOT output selected_doc_id, novel_scenario, or final selection — code applies policy after your rubrics.
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


def _dim(reasoning: str, rating: str) -> DimensionAssessment:
    return DimensionAssessment(reasoning=reasoning, rating=rating)  # type: ignore[arg-type]


def _all_pass_assessment(doc_id: str, *, notes: str = "") -> RunbookMatchAssessment:
    reason = notes or f"oracle: strong match for {doc_id}"
    pass_dim = _dim(reason, "PASS")
    return RunbookMatchAssessment(
        doc_id=doc_id,
        service_scope=pass_dim,
        symptom_match=pass_dim,
        telemetry_match=pass_dim,
        exclusion_clear=pass_dim,
    )


def _weak_match_assessment(doc_id: str, *, notes: str = "") -> RunbookMatchAssessment:
    reason = notes or f"oracle: weak match for {doc_id}"
    return RunbookMatchAssessment(
        doc_id=doc_id,
        service_scope=_dim("Service scope matches.", "PASS"),
        symptom_match=_dim(reason, "FAIL"),
        telemetry_match=_dim("Telemetry does not align with this runbook.", "FAIL"),
        exclusion_clear=_dim("Exclusion not satisfied.", "PARTIAL"),
    )


def mock_llm_output_oracle(
    *,
    expected_doc_id: str | None,
    expected_novel: bool,
    candidates: list[RunbookCandidate],
) -> RunbookEvalLLMOutput:
    if expected_novel or not expected_doc_id:
        return RunbookEvalLLMOutput(
            rubrics=[_weak_match_assessment(c.doc_id) for c in candidates],
        )

    candidate_ids = [c.doc_id for c in candidates]
    if expected_doc_id not in candidate_ids:
        return RunbookEvalLLMOutput(
            rubrics=[_weak_match_assessment(c.doc_id) for c in candidates],
        )

    rubrics = []
    for candidate in candidates:
        if candidate.doc_id == expected_doc_id:
            rubrics.append(_all_pass_assessment(candidate.doc_id))
        else:
            rubrics.append(_weak_match_assessment(candidate.doc_id))
    return RunbookEvalLLMOutput(rubrics=rubrics)


def mock_llm_output(service: str, candidates: list[RunbookCandidate]) -> RunbookEvalLLMOutput:
    if not candidates:
        return RunbookEvalLLMOutput(rubrics=[])

    if service in _NOVEL_SERVICES:
        return RunbookEvalLLMOutput(
            rubrics=[_weak_match_assessment(c.doc_id) for c in candidates],
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
            rubrics.append(_all_pass_assessment(candidate.doc_id, notes="mock: runbook guides remediation"))
        else:
            rubrics.append(_weak_match_assessment(candidate.doc_id))
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


def coverage_result_to_state(result, candidates: list[RunbookCandidate]) -> dict:
    rubrics = []
    for candidate in result.candidates:
        if candidate.match_assessment is not None:
            assessment = candidate.match_assessment
            rubrics.append({
                "doc_id": candidate.doc_id,
                "ratings": assessment.model_dump_ratings(),
                "dimensions": assessment.model_dump(),
            })
    return {
        "novel_scenario": result.novel_scenario,
        "novel_reason": result.novel_reason,
        "relevant_runbook": result.relevant_runbook,
        "selected_runbook_id": result.selected_doc_id,
        "runbook_match_rubrics": rubrics,
        "match_gate_reason": result.reasoning,
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
    """Evaluate runbook candidates and finalize selection / novel flags."""
    settings = settings or get_settings()
    data = dict(collected_data)

    symptoms = _symptoms_summary(service, data, incident_description)
    candidate_ids = [c.doc_id for c in candidates]
    runbook_text = _format_candidates_for_eval(candidates)
    policy = policy_from_settings(settings)

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

    result = finalize_runbook_match(
        service,
        candidates,
        llm_output,
        policy=policy,
    )
    return coverage_result_to_state(result, candidates)


run_diagnose_step1 = evaluate_runbook_coverage
step1_result_to_state = coverage_result_to_state
