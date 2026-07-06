"""Format prior remediation attempts for LLM prompts on retry rounds."""

from __future__ import annotations

from typing import Any

RCA_RETRY_GUIDANCE = (
    "Re-diagnosis after failed remediation: if symptoms persist, explain whether the prior "
    "root cause still holds or should be revised. Do not assume the prior diagnosis was "
    "wrong solely because remediation failed — cite fresh evidence."
)

# Deprecated alias
EVAL_DIAGNOSIS_RETRY_GUIDANCE = RCA_RETRY_GUIDANCE

DECIDE_RETRY_GUIDANCE = (
    "Prior remediation did not resolve the incident. Do NOT repeat the same write tool with "
    "the same arguments that already failed verification. Prefer a different tool, different "
    "parameters, or classify as uncertain with actionable recommendations."
)


def _failed_tool_names(history: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for entry in history:
        if entry.get("resolved"):
            continue
        for name in entry.get("tools_attempted") or []:
            if name and name not in names:
                names.append(name)
    return names


def format_remediation_context(
    state: dict,
    *,
    prior_root_cause: str | None = None,
    extra_guidance: str | None = None,
) -> str:
    """Return a prompt section for retry rounds; empty on the first remediation pass."""
    attempt = state.get("remediation_attempt", 0)
    history = list(state.get("remediation_history") or [])
    if attempt < 1 and not history:
        return ""

    lines = [
        "## Prior remediation attempts (incident not yet resolved)",
        f"Remediation verification rounds completed: {attempt}",
    ]

    if prior_root_cause:
        lines.append(f"Previous diagnosis (before this re-diagnosis): {prior_root_cause}")

    for entry in history:
        tools = entry.get("tools_attempted") or []
        tools_text = ", ".join(tools) if tools else "(unknown)"
        residual = entry.get("residual_symptoms") or []
        residual_text = ", ".join(residual) if residual else "(none listed)"
        lines.append(
            f"\n### Attempt {entry.get('attempt', '?')}\n"
            f"- Diagnosis at time of action: {entry.get('root_cause', '(unknown)')}\n"
            f"- Tools attempted: {tools_text}\n"
            f"- Execution results: {entry.get('exec_results', [])}\n"
            f"- Verified resolved: {entry.get('resolved')}\n"
            f"- Verification reasoning: {entry.get('reasoning', '')}\n"
            f"- Residual symptoms: {residual_text}"
        )

    failed_tools = _failed_tool_names(history)
    if failed_tools:
        lines.append(f"\nTools that failed verification: {', '.join(failed_tools)}")

    latest_reasoning = state.get("remediation_verify_reasoning")
    if latest_reasoning:
        lines.append(f"Latest verification note: {latest_reasoning}")

    if extra_guidance:
        lines.append(f"\n{extra_guidance}")

    return "\n".join(lines)
