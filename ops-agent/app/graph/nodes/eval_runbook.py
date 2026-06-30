from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.collection import (
    KNOWN_SERVICES,
    collect,
    extract_symptoms,
    retrieve_runbook_candidates,
    serialize_collected,
)
from app.graph.eval_schemas import (
    RunbookCandidate,
    RunbookEvalLLMOutput,
    RunbookPerDocRubric,
)
from app.graph.runbook_eval_policy import (
    finalize_runbook_eval,
    thresholds_from_settings,
)
from app.graph.state import AgentState
from app.llm.provider import get_chat_model

RUNBOOK_EVAL_SYSTEM_PROMPT = """\
You are the runbook coverage evaluation module of an ops agent.
Score **every** retrieved runbook candidate using the rubrics below.
Do NOT copy runbook full text into your output — only doc_id, numeric scores, signals, and coverage_notes.

Output a single list `rubrics`: one entry per candidate doc_id provided (no other top-level fields).

## Stage A — relevance (per doc_id)
Score each dimension 0, 0.15, or 0.25 (service_scope_match: only 0 or 0.25):
- service_scope_match: runbook 适用范围 matches incident service
  **If service does not match, set service_scope_match=0 and all other relevance dims=0.**
- symptom_match: 症状 section aligns with symptom summary
- telemetry_match: logs/k8s/metrics/operation signals align with 诊断 section
- exclusion_clear: runbook 不适用于 list does not conflict with evidence

List concrete tokens in match_signals / conflict_signals.

## Stage B — coverage (per doc_id, score all candidates)
Score each dimension 0, 0.15, or 0.25:
- root_cause_fit: 根因 converges with evidence
- remediation_fit: 处置 tools exist in catalog and args are inferable
- forbidden_clear: no conflict with 勿用手段
- verification_fit: 验证 criteria are observable

Optional short coverage_notes per candidate.

Do NOT output selected_doc_id, suggested_novel, novel_scenario, or reasoning — code applies thresholds after your rubric scores.
"""

_EVAL_DISPLAY_CHARS_PER_DOC = 4000


def _mock_fallback_candidates(service: str) -> list[RunbookCandidate]:
    """Mock-only: load on-disk runbook when retrieval returns nothing."""
    from app.graph.runbook_eval_policy import candidate_from_retrieval_dict
    from app.rag.ingest import extract_h1
    from app.rag.store import DATA_DIR

    paths = sorted((DATA_DIR / "runbooks").glob(f"{service}-*.md"))
    if not paths:
        return []
    path = paths[0]
    text = path.read_text(encoding="utf-8")
    return [candidate_from_retrieval_dict({
        "doc_id": path.stem,
        "title": extract_h1(text) or path.stem,
        "service": service,
        "chunk_type": "parent",
        "content": text,
        "rerank_score": 1.0,
    })]


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


def _mock_llm_output_oracle(
    *,
    expected_doc_id: str | None,
    expected_novel: bool,
    candidates: list[RunbookCandidate],
) -> RunbookEvalLLMOutput:
    """Golden-set oracle: perfect rubric labels for offline coverage eval (mock LLM only)."""
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


def _mock_llm_output(service: str, candidates: list[RunbookCandidate]) -> RunbookEvalLLMOutput:
    if not candidates or service not in KNOWN_SERVICES:
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


def _result_to_state(result) -> dict:
    return {
        "novel_scenario": result.novel_scenario,
        "novel_reason": result.novel_reason,
        "relevant_runbook": result.relevant_runbook,
        "selected_runbook_id": result.selected_doc_id,
        "coverage_confidence": result.coverage_confidence,
        "runbook_candidates": [c.model_dump() for c in result.candidates],
        "runbook_eval_reasoning": result.reasoning,
    }


def run_runbook_eval(
    service: str,
    incident_description: str,
    *,
    collected_data: dict | None = None,
    settings=None,
    golden_oracle: bool = False,
    oracle_expected_doc_id: str | None = None,
    oracle_expected_novel: bool = False,
) -> dict:
    """Run retrieve → LLM rubric → finalize. Optional telemetry override and golden oracle (mock LLM)."""
    settings = settings or get_settings()
    data = dict(collected_data) if collected_data is not None else collect(service)

    symptom_query = extract_symptoms(
        service,
        data,
        incident_description=incident_description,
    )
    candidates = retrieve_runbook_candidates(service, symptom_query, settings)
    if (
        settings.llm_is_mock
        and not candidates
        and service in KNOWN_SERVICES
        and not golden_oracle
    ):
        candidates = _mock_fallback_candidates(service)
    data["runbooks"] = [c.model_dump() for c in candidates]

    symptoms = _symptoms_summary(service, data, incident_description)
    candidate_ids = [c.doc_id for c in candidates]
    runbook_text = _format_candidates_for_eval(candidates)
    thresholds = thresholds_from_settings(settings)

    if settings.llm_is_mock and golden_oracle:
        llm_output = _mock_llm_output_oracle(
            expected_doc_id=oracle_expected_doc_id,
            expected_novel=oracle_expected_novel,
            candidates=candidates,
        )
    elif settings.llm_is_mock:
        llm_output = _mock_llm_output(service, candidates)
    else:
        llm = get_chat_model(settings=settings).with_structured_output(RunbookEvalLLMOutput)
        llm_output = llm.invoke([
            SystemMessage(content=RUNBOOK_EVAL_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Service: {service}\n"
                f"Symptom summary: {symptoms}\n"
                f"Candidate doc_ids: {candidate_ids}\n\n"
                f"Retrieved runbooks:\n{runbook_text}"
            )),
        ])

    result = finalize_runbook_eval(
        service,
        candidates,
        llm_output,
        thresholds=thresholds,
    )

    return {
        "collected_data": serialize_collected(data),
        "symptom_query": symptom_query,
        "status": "runbook_evaluated",
        **_result_to_state(result),
    }


def eval_runbook_node(state: AgentState) -> dict:
    service = state["service"]
    incident = state["incident"]
    return run_runbook_eval(
        service,
        incident.description,
        settings=get_settings(),
    )
