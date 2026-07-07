from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.decide_spec import (
    ASSESSMENT_EXPLORE_HUMAN_TEMPLATE,
    ASSESSMENT_EXPLORE_SYSTEM_PROMPT,
    ASSESSMENT_RUNBOOK_HUMAN_TEMPLATE,
    ASSESSMENT_RUNBOOK_SYSTEM_PROMPT,
    DecideAssessment,
    DecideOutcome,
    TOOL_SELECT_EXPLORE_HUMAN_TEMPLATE,
    TOOL_SELECT_EXPLORE_SYSTEM_PROMPT,
    TOOL_SELECT_RUNBOOK_HUMAN_TEMPLATE,
    TOOL_SELECT_RUNBOOK_SYSTEM_PROMPT,
    build_tool_call,
    mock_row_for_state,
)
from app.graph.remediation_context import DECIDE_RETRY_GUIDANCE, format_remediation_context
from app.graph.runbook_excerpt import excerpt_runbook
from app.graph.state import AgentState
from app.llm.provider import get_chat_model, invoke_structured
from app.schemas import DecisionClass
from app.tools import WRITE_TOOLS
from app.tools.policy import compute_needs_approval, pending_tool_calls
from app.tools.write_tool_catalog import format_write_tools_catalog


def _evidence_text(state: AgentState) -> str:
    lines = [f"- [{e.source}] {e.snippet}" for e in state.get("evidence", [])]
    return "\n".join(lines) or "(none)"


def _remediation_context_for_decide(state: AgentState) -> str:
    block = format_remediation_context(
        state,
        extra_guidance=(
            DECIDE_RETRY_GUIDANCE if state.get("remediation_attempt", 0) >= 1 else None
        ),
    )
    return block or "(none)"


def _runbook_excerpt_for_prompt(state: AgentState) -> str:
    raw = state.get("relevant_runbook")
    if not raw:
        return "(none)"
    return excerpt_runbook(raw)[:800]


def _run_assessment(state: AgentState, settings) -> DecideAssessment:
    service = state["service"]
    if settings.llm_is_mock:
        row = mock_row_for_state(state)
        return DecideAssessment(
            outcome=row.outcome,
            reasoning=row.reasoning,
            recommendations=list(row.recommendations),
            knowledge_gaps=list(row.knowledge_gaps),
            escalation_hint=row.escalation_hint,
        )

    runbook_available = bool(state.get("runbook_available"))
    if runbook_available:
        system_prompt = ASSESSMENT_RUNBOOK_SYSTEM_PROMPT
        human = ASSESSMENT_RUNBOOK_HUMAN_TEMPLATE.format(
            service=service,
            root_cause=state.get("root_cause", ""),
            relevant_runbook=_runbook_excerpt_for_prompt(state),
            evidence=_evidence_text(state),
            remediation_context=_remediation_context_for_decide(state),
            write_tools_catalog=format_write_tools_catalog(WRITE_TOOLS),
        )
    else:
        system_prompt = ASSESSMENT_EXPLORE_SYSTEM_PROMPT
        human = ASSESSMENT_EXPLORE_HUMAN_TEMPLATE.format(
            service=service,
            root_cause=state.get("root_cause", ""),
            evidence=_evidence_text(state),
            remediation_context=_remediation_context_for_decide(state),
            write_tools_catalog=format_write_tools_catalog(WRITE_TOOLS),
        )

    return invoke_structured(
        get_chat_model(settings=settings),
        DecideAssessment,
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human),
        ],
        settings=settings,
    )


def _run_tool_select(
    state: AgentState,
    assessment: DecideAssessment,
    settings,
) -> AIMessage:
    service = state["service"]
    if settings.llm_is_mock:
        row = mock_row_for_state(state)
        if row.outcome != DecideOutcome.ACTIONABLE or not row.tool_name:
            return AIMessage(content=assessment.reasoning)
        return AIMessage(
            content=row.tool_content,
            tool_calls=[build_tool_call(row, service, f"call_mock_{row.tool_name}")],
        )

    runbook_available = bool(state.get("runbook_available"))
    if runbook_available:
        system_prompt = TOOL_SELECT_RUNBOOK_SYSTEM_PROMPT
        human = TOOL_SELECT_RUNBOOK_HUMAN_TEMPLATE.format(
            service=service,
            root_cause=state.get("root_cause", ""),
            assessment_reasoning=assessment.reasoning,
            relevant_runbook=_runbook_excerpt_for_prompt(state),
            evidence=_evidence_text(state),
            remediation_context=_remediation_context_for_decide(state),
        )
    else:
        system_prompt = TOOL_SELECT_EXPLORE_SYSTEM_PROMPT
        human = TOOL_SELECT_EXPLORE_HUMAN_TEMPLATE.format(
            service=service,
            root_cause=state.get("root_cause", ""),
            assessment_reasoning=assessment.reasoning,
            evidence=_evidence_text(state),
            remediation_context=_remediation_context_for_decide(state),
        )

    llm = get_chat_model(settings=settings).bind_tools(WRITE_TOOLS)
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human),
    ])
    if isinstance(response, AIMessage):
        return response
    return AIMessage(content=str(getattr(response, "content", response)))


def _outcome_to_decision_class(outcome: DecideOutcome, needs_approval: bool) -> str:
    if outcome == DecideOutcome.UNCERTAIN:
        return DecisionClass.UNCERTAIN.value
    if outcome == DecideOutcome.OUT_OF_SCOPE:
        return DecisionClass.OUT_OF_SCOPE.value
    return DecisionClass.APPROVE.value if needs_approval else DecisionClass.EXECUTE.value


def _downgrade_uncertain(assessment: DecideAssessment, reason: str) -> DecideAssessment:
    gaps = list(assessment.knowledge_gaps)
    if reason not in gaps:
        gaps.append(reason)
    recs = list(assessment.recommendations)
    if not recs:
        recs.append("Insufficient basis to select a write tool; manual review required.")
    return DecideAssessment(
        outcome=DecideOutcome.UNCERTAIN,
        reasoning=reason,
        recommendations=recs,
        knowledge_gaps=gaps,
        escalation_hint=None,
    )


def decide_node(state: AgentState) -> dict:
    settings = get_settings()
    assessment = _run_assessment(state, settings)

    if assessment.outcome != DecideOutcome.ACTIONABLE:
        return {
            "decide_outcome": assessment.outcome.value,
            "decision_class": _outcome_to_decision_class(assessment.outcome, False),
            "recommendations": assessment.recommendations,
            "knowledge_gaps": assessment.knowledge_gaps,
            "escalation_hint": assessment.escalation_hint,
            "needs_approval": False,
            "status": "decided",
        }

    ai_message = _run_tool_select(state, assessment, settings)
    tool_calls = pending_tool_calls([ai_message])

    if not tool_calls:
        assessment = _downgrade_uncertain(
            assessment,
            "Assessment was actionable but no write tool could be selected safely.",
        )
        return {
            "decide_outcome": assessment.outcome.value,
            "decision_class": DecisionClass.UNCERTAIN.value,
            "recommendations": assessment.recommendations,
            "knowledge_gaps": assessment.knowledge_gaps,
            "escalation_hint": None,
            "needs_approval": False,
            "status": "decided",
        }

    needs_approval = compute_needs_approval(state, tool_calls)

    return {
        "messages": [ai_message],
        "decide_outcome": DecideOutcome.ACTIONABLE.value,
        "decision_class": _outcome_to_decision_class(DecideOutcome.ACTIONABLE, needs_approval),
        "recommendations": [],
        "knowledge_gaps": [],
        "escalation_hint": None,
        "needs_approval": needs_approval,
        "status": "decided",
    }
