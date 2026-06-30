"""Tool risk policy — risk levels are defined on tools, not by the LLM."""

from langchain_core.messages import AIMessage, ToolMessage

from app.schemas import RiskLevel

# Authoritative risk map: tool name → risk level
TOOL_RISK: dict[str, RiskLevel] = {
    "rollback_deployment": RiskLevel.HIGH,
    "scale_replicas": RiskLevel.HIGH,
    "restart_pods": RiskLevel.MEDIUM,
    "enable_circuit_breaker": RiskLevel.MEDIUM,
    "flush_cache": RiskLevel.MEDIUM,
    "purge_dead_letter_queue": RiskLevel.MEDIUM,
    "patch_config": RiskLevel.LOW,
    "toggle_feature_flag": RiskLevel.LOW,
    "resume_event_stream": RiskLevel.LOW,
    "cleanup_storage": RiskLevel.LOW,
}


def risk_for_tool(name: str) -> RiskLevel:
    return TOOL_RISK.get(name, RiskLevel.MEDIUM)


def pending_tool_calls(messages: list) -> list[dict]:
    """Return tool_calls from the most recent AIMessage that requested tools."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            return list(msg.tool_calls)
    return []


def tool_execution_results(messages: list) -> list[dict]:
    """Collect ToolMessage payloads written by ToolNode after execution."""
    results: list[dict] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = msg.content
            if isinstance(content, dict):
                results.append(content)
            elif isinstance(content, str):
                try:
                    import json
                    results.append(json.loads(content))
                except json.JSONDecodeError:
                    results.append({"message": content})
            else:
                results.append({"message": str(content)})
    return results


def enrich_tool_calls(tool_calls: list[dict]) -> list[dict]:
    """Attach policy-derived risk_level to each tool call for HITL display."""
    return [
        {**tc, "risk_level": risk_for_tool(tc.get("name", "")).value}
        for tc in tool_calls
    ]


def compute_needs_approval(state: dict, tool_calls: list[dict]) -> bool:
    """Whether tool execution requires human approval before ToolNode runs."""
    if not tool_calls:
        return False
    if state.get("remediation_attempt", 0) >= 1 and not state.get("incident_resolved"):
        return True
    if any(risk_for_tool(tc.get("name", "")) == RiskLevel.HIGH for tc in tool_calls):
        return True
    return bool(state.get("needs_human_review"))
