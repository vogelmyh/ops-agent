#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load .env before script defaults
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass

os.environ.setdefault("BACKEND_MODE", "mock")
os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("CHECKPOINTER", "memory")

from app.graph.runner import resume_approval, start_diagnosis
from app.schemas import IncidentInput
from eval.judges import action_match, root_cause_match


def main() -> None:
    dataset = Path(__file__).parent / "dataset.jsonl"
    total = 0
    passed = 0
    for line in dataset.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        total += 1
        _, resp, meta = start_diagnosis(
            IncidentInput(service=row["service"], description=row["description"])
        )
        if meta.get("pending_interrupt"):
            resp = resume_approval(resp.thread_id, approved=True)
        ok = root_cause_match(row["expected_root_cause"], resp.root_cause) and action_match(
            row["expected_action"], resp.pending_tool_calls
        )
        passed += int(ok)
    accuracy = passed / total if total else 0
    print(f"eval accuracy: {passed}/{total} = {accuracy:.1%}")
    report = Path(__file__).parent / "report.json"
    report.write_text(
        json.dumps({"passed": passed, "total": total, "accuracy": accuracy}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
