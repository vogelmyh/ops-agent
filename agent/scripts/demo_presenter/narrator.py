"""Per-node stream narration for the interactive demo."""

from __future__ import annotations

from typing import Any

from demo_presenter import breakpoints

NODE_STAGE: dict[str, str] = {
    "triage": "[采集]",
    "retrieve_runbooks": "[RAG·检索]",
    "diagnose": "[诊断]",
    "decide": "[决策]",
    "approve": "[人审]",
    "write_tools": "[执行]",
    "verify_remediation": "[验收]",
    "summarize": "[总结]",
    "request_runbook_notes": "[KB·采集]",
    "draft_runbook": "[KB·草稿]",
    "review_runbook": "[KB·评审]",
    "ingest_runbook": "[KB·入库]",
}


def _short(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


class StreamNarrator:
    def __init__(self, *, interactive: bool = True) -> None:
        self.interactive = interactive
        self.visited: list[str] = []

    def on_node(self, node_name: str, update: dict[str, Any]) -> None:
        self.visited.append(node_name)
        stage = NODE_STAGE.get(node_name, f"[{node_name}]")
        print(f"\n{stage} 节点完成 · {node_name}")
        if node_name == "retrieve_runbooks":
            q = update.get("symptom_query")
            if q:
                print(f"       symptom_query: {_short(q)}")
            candidates = update.get("runbook_candidates") or []
            if candidates:
                ids = [c.get("doc_id") or c.get("id") for c in candidates[:3]]
                print(f"       top candidates: {ids}")
        elif node_name == "diagnose":
            if update.get("selected_runbook_id"):
                print(f"       selected_runbook: {update.get('selected_runbook_id')}")
            if update.get("root_cause"):
                print(f"       root_cause: {_short(update.get('root_cause'))}")
            if update.get("novel_scenario") is not None:
                print(f"       novel_scenario: {update.get('novel_scenario')}")
        elif node_name == "decide":
            if update.get("decide_outcome"):
                print(f"       decide_outcome: {update.get('decide_outcome')}")
        elif node_name == "write_tools":
            msgs = update.get("messages") or []
            for m in msgs[-2:]:
                content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "")
                if content:
                    print(f"       { _short(str(content), 100) }")
        elif node_name == "verify_remediation":
            if update.get("incident_resolved") is not None:
                print(f"       incident_resolved: {update.get('incident_resolved')}")
        elif node_name == "summarize":
            if update.get("summary"):
                print(f"       summary: {_short(update.get('summary'))}")

        if self.interactive and breakpoints.should_pause_after(node_name):
            breakpoints.pause_after_node(node_name)
