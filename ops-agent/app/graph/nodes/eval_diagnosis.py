from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.eval_schemas import DiagnosisEvalAssessment
from app.graph.remediation_context import EVAL_DIAGNOSIS_RETRY_GUIDANCE, format_remediation_context
from app.graph.state import AgentState
from app.llm.provider import get_chat_model, invoke_structured

DIAGNOSIS_EVAL_SYSTEM_PROMPT = """\
You are the self-evaluation module of an ops agent.
Given raw evidence, diagnosed root cause, and reference runbook (if any), decide whether \
the diagnosis is reliable enough for unsupervised follow-up actions.

Set needs_human_review=true when evidence is insufficient, the conclusion is ambiguous, \
or it clearly contradicts the runbook.

novel_scenario=true only means no runbook in KB — it does NOT automatically require human review. \
Judge whether the diagnosed root cause is grounded in the evidence. A clear, converged diagnosis \
on a novel service can proceed without review.
"""

_NOVEL_CONFIDENT_SERVICES = frozenset({"ecomm-cache"})
_NOVEL_AMBIGUOUS_SERVICES = frozenset({"ecomm-search", "ecomm-catalog"})


def _evidence_summary(state: AgentState) -> str:
    lines = [f"- [{ev.source}] {ev.snippet}" for ev in state.get("evidence", [])]
    return "\n".join(lines) or "(none)"


def _mock_eval_diagnosis(state: AgentState) -> DiagnosisEvalAssessment:
    novel = state.get("novel_scenario", False)
    service = state.get("service", "")
    root_cause = state.get("root_cause", "")

    if not novel:
        return DiagnosisEvalAssessment(
            needs_human_review=False,
            reasoning="Diagnosis aligns with evidence and runbook; low-risk auto-execution is acceptable.",
        )
    if service in _NOVEL_CONFIDENT_SERVICES:
        return DiagnosisEvalAssessment(
            needs_human_review=False,
            reasoning=(
                "Novel service but diagnosis is converged (OOM/restart pattern); "
                "evidence supports standard ops remediation."
            ),
        )
    if service in _NOVEL_AMBIGUOUS_SERVICES or root_cause.startswith("Unknown root cause"):
        return DiagnosisEvalAssessment(
            needs_human_review=True,
            reasoning=(
                "Novel scenario with ambiguous or unconverged diagnosis; "
                "human should confirm before execution."
            ),
        )
    return DiagnosisEvalAssessment(
        needs_human_review=True,
        reasoning="Novel scenario; default to human review when diagnosis confidence is unclear.",
    )


def eval_diagnosis_node(state: AgentState) -> dict:
    settings = get_settings()
    root_cause = state.get("root_cause", "")
    relevant_runbook = state.get("relevant_runbook")
    evidence_text = _evidence_summary(state)

    if settings.llm_is_mock:
        assessment = _mock_eval_diagnosis(state)
    else:
        runbook_section = relevant_runbook or "(no reference runbook)"
        remediation_block = format_remediation_context(
            state,
            extra_guidance=(
                EVAL_DIAGNOSIS_RETRY_GUIDANCE
                if state.get("remediation_attempt", 0) >= 1
                else None
            ),
        )
        remediation_section = f"\n\n{remediation_block}" if remediation_block else ""
        assessment = invoke_structured(
            get_chat_model(settings=settings),
            DiagnosisEvalAssessment,
            [
                SystemMessage(content=DIAGNOSIS_EVAL_SYSTEM_PROMPT),
                HumanMessage(content=(
                    f"Evidence:\n{evidence_text}\n\n"
                    f"Diagnosed root cause:\n{root_cause}\n\n"
                    f"Reference runbook:\n{runbook_section[:1200]}"
                    f"{remediation_section}"
                )),
            ],
            settings=settings,
        )

    return {
        "needs_human_review": assessment.needs_human_review,
        "diagnosis_eval_reasoning": assessment.reasoning,
        "status": "diagnosis_evaluated",
    }
