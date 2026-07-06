from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.config import get_settings
from app.graph.decide_spec import DecideOutcome
from app.graph.nodes.approve import approve_node
from app.graph.nodes.decide import decide_node
from app.graph.nodes.diagnose import SKIPPED_LOW_CONFIDENCE, diagnose_node
from app.graph.nodes.draft_runbook import draft_runbook_node
from app.graph.nodes.verify_remediation import verify_remediation_node
from app.graph.nodes.ingest_runbook import ingest_runbook_node
from app.graph.nodes.request_runbook_notes import request_runbook_notes_node
from app.graph.nodes.retrieve_runbooks import retrieve_runbooks_node
from app.graph.nodes.review_runbook import review_runbook_node
from app.graph.nodes.summarize import summarize_node
from app.graph.nodes.triage import triage_node
from app.graph.state import AgentState
from app.memory.short_term import get_checkpointer
from app.tools import WRITE_TOOLS
from app.tools.policy import pending_tool_calls

write_tools_node = ToolNode(WRITE_TOOLS)


def _route_after_diagnose(state: AgentState) -> str:
    if not state.get("confidence_sufficient", True):
        return "summarize"
    if state.get("decide_outcome") == SKIPPED_LOW_CONFIDENCE:
        return "summarize"
    return "decide"


def _route_after_decide(state: AgentState) -> str:
    outcome = state.get("decide_outcome")
    if outcome in (DecideOutcome.UNCERTAIN.value, DecideOutcome.OUT_OF_SCOPE.value):
        return "summarize"
    tool_calls = pending_tool_calls(state.get("messages", []))
    if not tool_calls:
        return "summarize"
    if state.get("needs_approval"):
        return "approve"
    return "write_tools"


def _route_after_approve(state: AgentState) -> str:
    approval = state.get("approval") or {}
    if approval.get("approved"):
        return "write_tools"
    return "summarize"


def _route_after_verify_remediation(state: AgentState) -> str:
    if state.get("incident_resolved"):
        return "summarize"
    settings = get_settings()
    if state.get("remediation_attempt", 0) < settings.max_remediation_attempts:
        return "retrieve_runbooks"
    return "summarize"


def _route_after_summarize(state: AgentState) -> str:
    if state.get("novel_scenario"):
        return "request_runbook_notes"
    return END


def _route_after_review(state: AgentState) -> str:
    if state.get("runbook_approved"):
        return "ingest_runbook"
    return END


@lru_cache(maxsize=1)
def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("triage", triage_node)
    graph.add_node("retrieve_runbooks", retrieve_runbooks_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("decide", decide_node)
    graph.add_node("approve", approve_node)
    graph.add_node("write_tools", write_tools_node)
    graph.add_node("verify_remediation", verify_remediation_node)
    graph.add_node("summarize", summarize_node)
    graph.add_node("request_runbook_notes", request_runbook_notes_node)
    graph.add_node("draft_runbook", draft_runbook_node)
    graph.add_node("review_runbook", review_runbook_node)
    graph.add_node("ingest_runbook", ingest_runbook_node)

    graph.add_edge(START, "triage")
    graph.add_edge("triage", "retrieve_runbooks")
    graph.add_edge("retrieve_runbooks", "diagnose")
    graph.add_conditional_edges(
        "diagnose",
        _route_after_diagnose,
        {"summarize": "summarize", "decide": "decide"},
    )
    graph.add_conditional_edges(
        "decide",
        _route_after_decide,
        {
            "approve": "approve",
            "write_tools": "write_tools",
            "summarize": "summarize",
        },
    )
    graph.add_conditional_edges(
        "approve",
        _route_after_approve,
        {"write_tools": "write_tools", "summarize": "summarize"},
    )
    graph.add_edge("write_tools", "verify_remediation")
    graph.add_conditional_edges(
        "verify_remediation",
        _route_after_verify_remediation,
        {"summarize": "summarize", "retrieve_runbooks": "retrieve_runbooks"},
    )
    graph.add_conditional_edges(
        "summarize",
        _route_after_summarize,
        {"request_runbook_notes": "request_runbook_notes", END: END},
    )
    graph.add_edge("request_runbook_notes", "draft_runbook")
    graph.add_edge("draft_runbook", "review_runbook")
    graph.add_conditional_edges(
        "review_runbook",
        _route_after_review,
        {"ingest_runbook": "ingest_runbook", END: END},
    )
    graph.add_edge("ingest_runbook", END)

    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)
