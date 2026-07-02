"""Decide-node spec: structured assessment prompts, tool-select prompts, and mock matrix."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.adapters.mock_data import get_mock_scenario


class DecideOutcome(str, Enum):
    ACTIONABLE = "actionable"
    UNCERTAIN = "uncertain"
    OUT_OF_SCOPE = "out_of_scope"


_OUTCOME_ALIASES = ("classification", "decision", "outcome_type", "handleability")
_OUTCOME_VALUE_MAP = {
    "out-of-scope": "out_of_scope",
    "out of scope": "out_of_scope",
    "outofscope": "out_of_scope",
    "action-able": "actionable",
    "not_actionable": "uncertain",
}


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _normalize_outcome_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    return _OUTCOME_VALUE_MAP.get(key, key)


def coerce_decide_assessment(data: Any) -> Any:
    """Normalize LLM JSON drift into flat DecideAssessment fields."""
    if not isinstance(data, dict):
        return data

    out = dict(data)
    if "outcome" not in out:
        for alias in _OUTCOME_ALIASES:
            if alias in out:
                out["outcome"] = out.pop(alias)
                break
    if "outcome" in out:
        out["outcome"] = _normalize_outcome_value(out["outcome"])

    for key in ("recommendations", "knowledge_gaps"):
        if key in out:
            out[key] = _as_str_list(out[key])

    if not out.get("reasoning"):
        for alias in ("explanation", "summary", "rationale", "reason"):
            if alias in out and out[alias]:
                out["reasoning"] = str(out[alias])
                break
        else:
            out.setdefault("reasoning", "")

    hint = out.get("escalation_hint")
    if isinstance(hint, str) and hint.strip().lower() in {"", "null", "none"}:
        out["escalation_hint"] = None

    return out


class DecideAssessment(BaseModel):
    """Handleability assessment structured output — no tool_calls."""

    outcome: DecideOutcome
    reasoning: str = Field(description="One or two sentences explaining the classification")
    recommendations: list[str] = Field(
        default_factory=list,
        description="Operator-facing advice when outcome is not actionable",
    )
    knowledge_gaps: list[str] = Field(
        default_factory=list,
        description="Missing evidence or runbook gaps; mainly for uncertain",
    )
    escalation_hint: str | None = Field(
        default=None,
        description="Suggested handoff team for out_of_scope, e.g. dev team / DBA / hardware ops",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_assessment_shape(cls, data: Any) -> Any:
        return coerce_decide_assessment(data)


ASSESSMENT_SYSTEM_PROMPT = """\
You are the handleability assessment module of a cloud ops agent.

The upstream diagnose step has already adopted the root cause. Your sole task: given that root cause, \
evidence, optional validated runbook, and the **authoritative write-tool catalog**, decide whether \
catalog tools can remediate this incident.

Do NOT select or invoke any tools in this step — output structured assessment only.
Do NOT re-judge diagnosis confidence, evidence sufficiency, or novel_scenario.

## Outcomes (pick exactly one)

### actionable
Root cause is accepted AND at least one catalog tool clearly applies with safely inferable parameters.

### out_of_scope
Root cause is accepted but **none** of the catalog tools can address it (e.g. code bug, DBA, hardware).

Provide recommendations and escalation_hint for out_of_scope.

Do NOT output uncertain — if parameters are unsafe, still choose out_of_scope with guidance.
"""

ASSESSMENT_HUMAN_TEMPLATE = """\
Service: {service}
Root cause: {root_cause}
novel_scenario: {novel_scenario}
Relevant runbook:
{relevant_runbook}

Evidence:
{evidence}

{remediation_context}

Available write tools (authoritative catalog for capability assessment — do NOT invoke here):
{write_tools_catalog}
"""

TOOL_SELECT_SYSTEM_PROMPT = """\
You are the remediation execution module of a cloud ops agent.

The previous step classified this incident as actionable. You MUST invoke exactly one \
appropriate write tool with complete arguments.
- Pick from the bound tools only
- Do NOT output risk_level (computed by policy from tool name)
- Do NOT re-run handleability assessment
- If you cannot safely pick a tool, reply in plain text with the reason and produce NO tool_calls \
(the system will downgrade to uncertain)
"""

TOOL_SELECT_HUMAN_TEMPLATE = """\
Service: {service}
Root cause: {root_cause}
Assessment reasoning: {assessment_reasoning}
Relevant runbook:
{relevant_runbook}

Evidence:
{evidence}

{remediation_context}
"""


class MockDecideRow(BaseModel):
    outcome: DecideOutcome
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    tool_content: str = ""
    reasoning: str = ""
    recommendations: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    escalation_hint: str | None = None
    expected_needs_approval: bool | None = None
    expected_route: str = ""


SCENARIO_DECIDE_ROWS: dict[tuple[str, str], MockDecideRow] = {
    ("ecomm-manager", "rate-limit"): MockDecideRow(
        outcome=DecideOutcome.ACTIONABLE,
        tool_name="patch_config",
        tool_args={"config_key": "rate-limit.max-qps", "config_value": "5000"},
        tool_content="Admin API rate-limit misconfiguration; invoking patch_config.",
        reasoning="Root cause is max-qps threshold misconfiguration; runbook supports config patch.",
        expected_needs_approval=False,
        expected_route="write_tools",
    ),
    ("ecomm-manager", "feature-flag"): MockDecideRow(
        outcome=DecideOutcome.ACTIONABLE,
        tool_name="toggle_feature_flag",
        tool_args={"flag_name": "promotion-v2", "enabled": False},
        tool_content="Gray feature flag causing NPE; disabling promotion-v2.",
        reasoning="Root cause is unstable promotion-v2 flag; runbook recommends disable.",
        expected_needs_approval=False,
        expected_route="write_tools",
    ),
    ("ecomm-manager", "crashloop"): MockDecideRow(
        outcome=DecideOutcome.ACTIONABLE,
        tool_name="rollback_deployment",
        tool_args={"target_version": "ecomm-manager:2.0.8-stable"},
        tool_content="Bad image CrashLoop; rolling back to stable version.",
        reasoning="App logs and K8s events point to bad image; rollback is standard ops remediation.",
        expected_needs_approval=True,
        expected_route="approve",
    ),
    ("ecomm-manager", "discount-bug"): MockDecideRow(
        outcome=DecideOutcome.OUT_OF_SCOPE,
        reasoning="Root cause is discount calculation logic bug; requires dev team code fix.",
        recommendations=["Engage development team to fix DiscountEngine logic"],
        escalation_hint="development team",
        expected_route="summarize",
    ),
    ("ecomm-manager", "disk-full"): MockDecideRow(
        outcome=DecideOutcome.ACTIONABLE,
        tool_name="cleanup_storage",
        tool_args={"path": "/var/log/ecomm-manager", "retention_days": 7},
        tool_content="Audit log volume full; cleaning old logs under /var/log/ecomm-manager.",
        reasoning="Disk full on audit log path; runbook supports cleanup_storage.",
        expected_needs_approval=False,
        expected_route="write_tools",
    ),
    ("ecomm-order", "crashloop"): MockDecideRow(
        outcome=DecideOutcome.ACTIONABLE,
        tool_name="rollback_deployment",
        tool_args={"target_version": "ecomm-order:3.2.1-stable"},
        tool_content="Bad image CrashLoop; rolling back order service.",
        reasoning="K8s BackOff after bad release; rollback_deployment per runbook.",
        expected_needs_approval=True,
        expected_route="approve",
    ),
    ("ecomm-order", "stream-paused"): MockDecideRow(
        outcome=DecideOutcome.ACTIONABLE,
        tool_name="resume_event_stream",
        tool_args={"stream_id": "order-events"},
        tool_content="Order event stream PAUSED; resuming stream.",
        reasoning="Stream order-events is PAUSED; runbook recommends resume.",
        expected_needs_approval=False,
        expected_route="write_tools",
    ),
    ("ecomm-order", "memory-leak"): MockDecideRow(
        outcome=DecideOutcome.ACTIONABLE,
        tool_name="restart_pods",
        tool_args={"strategy": "rolling"},
        tool_content="OOM on stable image; rolling restart to recover connections.",
        reasoning="Memory leak on unchanged image; restart_pods per runbook.",
        expected_needs_approval=False,
        expected_route="write_tools",
    ),
    ("ecomm-order", "payment-circuit"): MockDecideRow(
        outcome=DecideOutcome.ACTIONABLE,
        tool_name="enable_circuit_breaker",
        tool_args={"upstream": "payment-gw", "state": "open"},
        tool_content="Payment gateway upstream failing; opening circuit breaker.",
        reasoning="Upstream payment-gw timeout storm; open circuit per runbook.",
        expected_needs_approval=False,
        expected_route="write_tools",
    ),
    ("ecomm-order", "rds-timeout"): MockDecideRow(
        outcome=DecideOutcome.OUT_OF_SCOPE,
        reasoning="Root cause is managed RDS timeout; requires DBA / cloud RDS on-call.",
        recommendations=["Escalate to DBA to inspect RDS connections and latency"],
        escalation_hint="DBA / cloud RDS on-call",
        expected_route="summarize",
    ),
}

MOCK_MATRIX_EXTRAS: dict[str, MockDecideRow] = {
    "ecomm-search": MockDecideRow(
        outcome=DecideOutcome.UNCERTAIN,
        reasoning=(
            "Index rebuild failure with generic latency symptoms; "
            "root cause not converged — cannot safely pick a write tool."
        ),
        recommendations=["Gather OOM events or expand index rebuild logs before remediation"],
        knowledge_gaps=["Ambiguous root cause", "No runbook coverage"],
        expected_route="summarize",
    ),
    "ecomm-catalog": MockDecideRow(
        outcome=DecideOutcome.UNCERTAIN,
        reasoning=(
            "Catalog API errors with insufficient evidence to distinguish index vs upstream failure; "
            "write-tool parameters are not safe to infer."
        ),
        recommendations=["Escalate to senior ops or gather more catalog/index telemetry"],
        knowledge_gaps=["Ambiguous root cause", "No runbook coverage"],
        expected_route="summarize",
    ),
    "ecomm-cache": MockDecideRow(
        outcome=DecideOutcome.ACTIONABLE,
        tool_name="restart_pods",
        tool_args={"strategy": "rolling"},
        tool_content="Redis cache pod OOMKilled; rolling restart per standard ops pattern.",
        reasoning=(
            "OOMKilled pod with high restarts; restart_pods is standard recovery "
            "even without runbook coverage."
        ),
        expected_needs_approval=False,
        expected_route="write_tools",
    ),
    "unknown-service": MockDecideRow(
        outcome=DecideOutcome.UNCERTAIN,
        reasoning="Root cause not converged; cannot safely select write tool or parameters.",
        recommendations=["Escalate to senior ops or add runbook before automated remediation"],
        knowledge_gaps=["Ambiguous root cause", "Insufficient evidence for automated write"],
        expected_route="summarize",
    ),
}


def mock_row_for_service(service: str) -> MockDecideRow:
    scenario = get_mock_scenario(service)
    key = (service, scenario)
    if key in SCENARIO_DECIDE_ROWS:
        return SCENARIO_DECIDE_ROWS[key]
    if service in MOCK_MATRIX_EXTRAS:
        return MOCK_MATRIX_EXTRAS[service]
    return MOCK_MATRIX_EXTRAS["unknown-service"]


def mock_row_for_state(state: dict) -> MockDecideRow:
    """Mock decide matrix; chaos scenarios switch tool/outcome after failed remediation round."""
    service = state["service"]
    scenario = get_mock_scenario(service)
    attempt = state.get("remediation_attempt", 0)
    if service == "ecomm-manager" and scenario in ("chaos-morph", "chaos-exhaust"):
        if attempt >= 1:
            return SCENARIO_DECIDE_ROWS[("ecomm-manager", "feature-flag")]
        return SCENARIO_DECIDE_ROWS[("ecomm-manager", "rate-limit")]
    if service == "ecomm-manager" and scenario == "chaos-oos":
        if attempt >= 1:
            return SCENARIO_DECIDE_ROWS[("ecomm-manager", "discount-bug")]
        return SCENARIO_DECIDE_ROWS[("ecomm-manager", "rate-limit")]
    return mock_row_for_service(service)


def build_tool_call(row: MockDecideRow, service: str, call_id: str) -> dict[str, Any]:
    if not row.tool_name:
        raise ValueError("Mock row has no tool_name")
    args = dict(row.tool_args)
    if row.tool_name in (
        "rollback_deployment",
        "scale_replicas",
        "restart_pods",
        "enable_circuit_breaker",
        "flush_cache",
        "purge_dead_letter_queue",
        "patch_config",
        "toggle_feature_flag",
        "resume_event_stream",
        "cleanup_storage",
    ):
        args.setdefault("service", service)
    return {
        "name": row.tool_name,
        "args": args,
        "id": call_id,
        "type": "tool_call",
    }
