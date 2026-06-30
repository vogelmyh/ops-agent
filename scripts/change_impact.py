#!/usr/bin/env python3
"""Suggest docs and test commands from git changed paths (monorepo root)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = "ops-agent"

# path fragment → (docs to read, make targets)
RULES: list[tuple[str, list[str], list[str]]] = [
    ("ops-agent/app/rag/", ["ops-agent/docs/rag-architecture-and-tests.md §5"], ["test-rag"]),
    ("ops-agent/app/graph/nodes/eval_runbook", ["ops-agent/docs/rag-architecture-and-tests.md §5.5–5.6"], ["test-rag"]),
    ("ops-agent/app/graph/runbook_eval_policy", ["ops-agent/docs/rag-architecture-and-tests.md §5.6"], ["test-rag"]),
    ("ops-agent/app/graph/eval_schemas", ["ops-agent/docs/rag-architecture-and-tests.md §5.5"], ["test-rag"]),
    ("ops-agent/tests/rag_eval/", ["ops-agent/docs/rag-architecture-and-tests.md §5.8", "ops-agent/docs/rag-eval-corpus.md"], ["test-rag"]),
    ("ops-agent/app/graph/builder", ["ops-agent/docs/graph-agent-architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/runner", ["ops-agent/docs/graph-agent-architecture.md", "ops-agent/docs/api-runtime-architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/nodes/", ["ops-agent/docs/graph-agent-architecture.md（核对是否 RAG/decide 节点）"], ["test-graph", "test-rag"]),
    ("ops-agent/app/graph/decide", ["ops-agent/docs/decide-remediation-architecture.md"], ["test-graph"]),
    ("ops-agent/app/tools/", ["ops-agent/docs/decide-remediation-architecture.md"], ["test-graph"]),
    ("ops-agent/app/adapters/", ["ops-agent/docs/backend-adapters-architecture.md"], ["test-graph"]),
    ("ops-backend-simulator/", ["ops-backend-simulator/README.md", "ops-agent/docs/backend-adapters-architecture.md §5"], ["test-graph"]),
    ("ops-agent/app/main.py", ["ops-agent/docs/api-runtime-architecture.md"], ["test"]),
    ("ops-agent/app/config.py", ["ops-agent/docs/api-runtime-architecture.md", "ops-agent/docs/rag-architecture-and-tests.md §2.5"], ["test-rag", "test"]),
    ("ops-agent/data/runbooks/", ["ops-agent/docs/rag-architecture-and-tests.md §5.4", "ops-agent/docs/rag-eval-corpus.md"], ["test-rag"]),
    ("ops-agent/docs/test-scenario-trajectories", ["（场景目录）确认未重复组件实现细节"], []),
]

GENERIC = [
    "docs/change-workflow.md",
    "AGENTS.md",
]


def _git_paths(staged: bool) -> list[str]:
    cmd = ["git", "diff", "--name-only"]
    if staged:
        cmd.append("--cached")
    else:
        cmd.append("HEAD")
    try:
        out = subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def analyze(paths: list[str]) -> tuple[list[str], list[str]]:
    docs: list[str] = []
    tests: list[str] = []
    if not paths:
        return docs, tests
    for path in paths:
        for fragment, doc_list, test_list in RULES:
            if fragment in path.replace("\\", "/"):
                for d in doc_list:
                    if d not in docs:
                        docs.append(d)
                for t in test_list:
                    if t not in tests:
                        tests.append(t)
    return docs, tests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Use staged diff only")
    parser.add_argument("paths", nargs="*", help="Override paths (default: git diff)")
    args = parser.parse_args()

    paths = args.paths or _git_paths(args.staged)
    print("Changed paths:")
    if paths:
        for p in paths:
            print(f"  - {p}")
    else:
        print("  (none — working tree clean or not a git repo)")

    print("\nAlways review:")
    for g in GENERIC:
        print(f"  - {g}")

    docs, tests = analyze(paths)
    print("\nSuggested docs:")
    if docs:
        for d in docs:
            print(f"  - {d}")
    else:
        print("  - ops-agent/docs/architecture.md（未命中规则，请手动分类）")

    print("\nSuggested commands:")
    if tests:
        for t in tests:
            print(f"  make {t}")
    else:
        print("  make test")
    print("\nThen complete docs/change-workflow.md checklist before commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
