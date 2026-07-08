"""Breakpoint policy for interactive demo pacing."""

from __future__ import annotations

from demo_presenter import console

# Pause after these graph nodes (Enter to continue).
PAUSE_AFTER_NODES = frozenset(
    {
        "triage",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "write_tools",
        "verify_remediation",
        "summarize",
    }
)


def should_pause_after(node_name: str) -> bool:
    return node_name in PAUSE_AFTER_NODES


def pause_after_node(node_name: str) -> None:
    console.pause_enter(f"{node_name} 完成，按 Enter 继续…")


def confirm_alert(description: str) -> bool:
    console.heading("告警确认")
    print(f"  {description}")
    return console.prompt_yes_no("是否以此告警启动 Agent 诊断？", default=True)


def confirm_hitl(tool_name: str) -> bool:
    console.heading("人工审批 (HITL)")
    print(f"  待执行工具: {tool_name}")
    return console.prompt_yes_no("是否批准执行？", default=True)
