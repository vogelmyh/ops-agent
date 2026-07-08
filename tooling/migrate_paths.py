#!/usr/bin/env python3
"""One-off path migration: ops-agent/ → agent/, docs layout, scripts/ → tooling/."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "target", ".pytest_cache", "chroma"}
TEXT_SUFFIXES = {
    ".md", ".mdc", ".py", ".yml", ".yaml", ".toml", ".xml", ".sh", ".env.example",
    "Makefile", ".gitignore",
}

# Order matters: longer / more specific first.
REPLACEMENTS: list[tuple[str, str]] = [
    ("../../docs/agent/", "../../docs/agent/"),
    ("../docs/agent/", "../docs/agent/"),
    ("docs/agent/", "docs/agent/"),
    ("docs/workflow/change-workflow.md", "docs/workflow/change-workflow.md"),
    ("python3 tooling/change_impact.py", "python3 tooling/change_impact.py"),
    ("python tooling/change_impact.py", "python tooling/change_impact.py"),
    ("tooling/change_impact.py", "tooling/change_impact.py"),
    ("../agent/.venv", "../agent/.venv"),
    ("agent/.venv", "agent/.venv"),
    ("context: ../agent", "context: ../agent"),
    ("cd agent &&", "cd agent &&"),
    ("cd agent ", "cd agent "),
    ("| [`agent/`](agent/)", "| [`agent/`](agent/)"),
    ("| `agent/`", "| `agent/`"),
    ('("agent/', '("agent/'),
    ("agent/tests/", "agent/tests/"),
    ("agent/scripts/", "agent/scripts/"),
    ("agent/data/", "agent/data/"),
    ("agent/app/", "agent/app/"),
    ("agent/eval/", "agent/eval/"),
    ("../agent/", "../agent/"),
    ("agent/README.md", "agent/README.md"),
    # Product / path references in prose (after path-specific rules)
    ("agent test ID", "agent test ID"),
    ("Point agent at", "Point agent at"),
    ("agent 视角", "agent 视角"),
    ("# 文档索引", "# 文档索引"),
    ("本目录是 **agent** 工程的架构", "本目录是 **agent** 工程的架构"),
    ("（`docs/agent/`）", "（`docs/agent/`）"),
    ("`docs/agent/`", "`docs/agent/`"),
    ("主文档（`docs/agent/`）", "主文档（`docs/agent/`）"),
    ("架构见根 `docs/agent/`", "架构见根 `docs/agent/`"),
    ("# Python Agent（在 agent/ 下已有 .venv 时）", "# Python Agent（在 agent/ 下已有 .venv 时）"),
    ("agent/data/runbooks", "agent/data/runbooks"),
    ("agent/data/", "agent/data/"),
    ("agent/scripts/", "agent/scripts/"),
    ("agent/tests/", "agent/tests/"),
]

# Paths that must NOT get blanket ops-agent → agent (handled by rules above).
SKIP_SUBSTR = ("ops_agent_", "ops-agent-secret", "ops-agent-service", "ops-agent-deployment",
               "ops-agent-configmap", "ops-agent-hpa", "name: ops-agent", "service: ops-agent",
               "container: ops-agent", "app: ops-agent")


def should_process(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    if path.suffix in TEXT_SUFFIXES:
        return True
    if path.name in TEXT_SUFFIXES:
        return True
    return False


def migrate_content(text: str, filepath: str) -> str:
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    # .gitignore: ops-agent/ at line start
    if filepath.endswith(".gitignore"):
        text = re.sub(r"(?m)^ops-agent/", "agent/", text)
        text = re.sub(r"# Python \(ops-agent/ops-agent\)", "# Python (agent/)", text)
    return text


def main() -> None:
    changed = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or not should_process(path):
            continue
        rel = str(path.relative_to(ROOT))
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        updated = migrate_content(original, rel)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            print(f"updated: {rel}")
    print(f"done: {changed} files")


if __name__ == "__main__":
    main()
