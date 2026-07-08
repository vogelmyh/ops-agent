from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt

from app.config import get_settings
from app.graph.state import AgentState
from app.llm.provider import get_chat_model
from app.tools import READ_TOOLS


def investigate_agent_node(state: AgentState) -> dict:
    """Tool-calling agent for collaborative investigation (READ tools only)."""
    settings = get_settings()
    service = state.get("service", "")
    system = SystemMessage(content=(
        f"You are an ops investigation assistant collaborating with a human on service '{service}'. "
        "You may call read-only tools to query logs, metrics, and status. "
        "Keep each reply concise: state findings and what information is still needed. "
        "Do NOT perform write operations."
    ))

    if settings.llm_is_mock:
        content = (
            "Investigation found /var/log at 85% usage; app logs report No space left on device. "
            "Suggest confirming whether logs older than 7 days can be cleaned."
        )
        return {"messages": [AIMessage(content=content)]}

    llm = get_chat_model(settings=settings).bind_tools(READ_TOOLS)
    history = [system] + list(state.get("messages", []))
    response = llm.invoke(history)
    return {"messages": [response]}


def investigate_human_node(state: AgentState) -> dict:
    payload = {
        "message": "Collaborative investigation: add clues or set done=true to finish.",
        "last_assistant_message": _last_ai_content(state),
    }
    decision = interrupt(payload)
    message = str(decision.get("message", "")).strip()
    done = bool(decision.get("done", False))
    updates: dict = {"status": "investigating"}
    if message:
        updates["messages"] = [HumanMessage(content=message)]
    if done:
        updates["investigation_done"] = True
    return updates


def investigate_finalize_node(state: AgentState) -> dict:
    """Summarize investigation and re-enter decide with richer context."""
    settings = get_settings()

    if settings.llm_is_mock:
        summary = (
            "Human confirmed logs under /var/log older than 7 days can be cleaned; "
            "root cause is disk full blocking writes."
        )
    else:
        llm = get_chat_model(settings=settings)
        msgs = state.get("messages", [])
        text = "\n".join(
            f"{getattr(m, 'type', 'msg')}: {getattr(m, 'content', '')}" for m in msgs[-10:]
        )
        response = llm.invoke([
            SystemMessage(content=(
                "Summarize the collaborative investigation transcript in 2-3 concise sentences. "
                "Write the summary in Chinese for operator display."
            )),
            HumanMessage(content=text),
        ])
        summary = response.content.strip()

    return {
        "investigation_summary": summary,
        "investigation_done": True,
        "status": "investigation_complete",
    }


def _last_ai_content(state: AgentState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage) or getattr(msg, "type", "") == "ai":
            return str(getattr(msg, "content", ""))
    return ""
