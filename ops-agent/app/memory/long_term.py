import json
from pathlib import Path

MEMORY_PATH = Path("./data/incident_memory.jsonl")


def save_incident_memory(service: str, root_cause: str, summary: str) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"service": service, "root_cause": root_cause, "summary": summary}
    with MEMORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def search_similar_incidents(service: str, limit: int = 3) -> list[dict]:
    if not MEMORY_PATH.exists():
        return []
    matches: list[dict] = []
    for line in MEMORY_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("service") == service:
            matches.append(item)
    return matches[-limit:]
