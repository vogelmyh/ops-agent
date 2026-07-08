import re
from pathlib import Path

from app.graph.state import AgentState
from app.rag.ingest import reindex
from app.rag.store import DATA_DIR


def _slug_from_draft(draft: str, service: str) -> str:
    for line in draft.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title.lower())
            slug = re.sub(r"-+", "-", slug).strip("-")
            if slug:
                return f"{service}-{slug[:40]}"
    return f"{service}-novel-scenario"


def ingest_runbook_node(state: AgentState) -> dict:
    if not state.get("runbook_approved"):
        return {"status": "completed"}

    draft = state.get("runbook_draft", "")
    service = state.get("service", "unknown")
    if not draft.strip():
        return {"status": "completed"}

    stem = _slug_from_draft(draft, service)
    path = DATA_DIR / "runbooks" / f"{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(draft.strip() + "\n", encoding="utf-8")
    reindex()

    return {
        "status": "completed",
        "runbook_saved_path": str(path),
    }
