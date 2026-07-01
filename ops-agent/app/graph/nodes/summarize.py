from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.state import AgentState
from app.llm.provider import get_chat_model
from app.memory.long_term import save_incident_memory
from app.tools.policy import pending_tool_calls, risk_for_tool, tool_execution_results

SUMMARIZE_SYSTEM_PROMPT = """\
Write a concise incident summary in Chinese (at most 150 characters).
Cover: root cause, remediation actions taken, execution results, and whether the incident \
was verified as resolved after remediation.
"""


def summarize_node(state: AgentState) -> dict:
    root = state.get("root_cause", "")
    evidence = state.get("evidence", [])
    messages = state.get("messages", [])
    tool_calls = pending_tool_calls(messages)
    exec_results = tool_execution_results(messages)
    settings = get_settings()

    refs = ", ".join(e.ref for e in evidence[:4])
    resolved = state.get("incident_resolved")
    remediation_reasoning = state.get("remediation_eval_reasoning", "")
    attempt = state.get("remediation_attempt", 0)

    if settings.llm_is_mock:
        if state.get("decide_outcome") == "skipped_low_confidence":
            summary = (
                f"{root} (evidence: {refs}; diagnosis confidence insufficient — "
                "remediation skipped)"
            )
        elif exec_results:
            exec_msg = exec_results[-1].get("message", "")
            resolved_note = (
                "verified resolved"
                if resolved
                else f"not resolved after {attempt} attempt(s)"
            )
            summary = f"{root} (evidence: {refs}; executed: {exec_msg}; {resolved_note})"
        else:
            summary = f"{root} (evidence: {refs})"
    else:
        llm = get_chat_model(settings=settings)

        actions_text = (
            "\n".join(
                f"- {tc.get('name')} args={tc.get('args')} (risk={risk_for_tool(tc.get('name', '')).value})"
                for tc in tool_calls
            )
            if tool_calls
            else "(none)"
        )
        exec_text = (
            "\n".join(str(r) for r in exec_results)
            if exec_results
            else "not executed or rejected"
        )
        resolved_text = (
            f"resolved={resolved}; verification: {remediation_reasoning}"
            if resolved is not None
            else "no write remediation performed"
        )

        response = llm.invoke([
            SystemMessage(content=SUMMARIZE_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Root cause: {root}\n"
                f"Evidence refs: {refs}\n"
                f"Remediation actions:\n{actions_text}\n"
                f"Execution results:\n{exec_text}\n"
                f"Post-remediation verification:\n{resolved_text}\n"
                f"Remediation attempts: {attempt}"
            )),
        ])
        summary = response.content.strip()

    save_incident_memory(state.get("service", ""), root, summary)
    return {"summary": summary, "status": "completed"}
