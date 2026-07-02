#!/usr/bin/env python3
"""Map changed paths to docs + make test targets; optional pre-commit test runner."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# path fragment → (docs, make targets); first match wins per category but all matches merge targets
RULES: list[tuple[str, list[str], list[str]]] = [
    ("ops-agent/app/rag/", ["ops-agent/docs/rag-architecture-and-tests.md §5"], ["test-rag"]),
    ("ops-agent/app/graph/nodes/retrieve_runbooks", ["ops-agent/docs/rag-architecture-and-tests.md §5.2"], ["test-rag", "test-graph"]),
    ("ops-agent/app/graph/runbook_coverage", ["ops-agent/docs/rag-architecture-and-tests.md §5.5–5.6"], ["test-rag-coverage"]),
    ("ops-agent/app/graph/diagnose_runbook_step", ["ops-agent/docs/rag-architecture-and-tests.md §5.5–5.6"], ["test-rag-coverage"]),
    ("ops-agent/app/graph/nodes/eval_runbook", ["ops-agent/docs/rag-architecture-and-tests.md §5.5–5.6"], ["test-rag-coverage"]),
    ("ops-agent/app/graph/nodes/diagnose", ["ops-agent/docs/graph-agent-architecture.md", "ops-agent/docs/test-scenario-trajectories.md"], ["test-graph", "test-api"]),
    ("ops-agent/app/graph/diagnose_spec", ["ops-agent/docs/graph-agent-architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/runbook_eval_policy", ["ops-agent/docs/rag-architecture-and-tests.md §5.6"], ["test-rag"]),
    ("ops-agent/app/graph/eval_schemas", ["ops-agent/docs/rag-architecture-and-tests.md §5.5"], ["test-rag"]),
    ("ops-agent/app/rag/eval_harness", ["ops-agent/docs/rag-architecture-and-tests.md §5.8"], ["test-rag"]),
    ("ops-agent/tests/rag_eval/", ["ops-agent/docs/rag-architecture-and-tests.md §5.8"], ["test-rag"]),
    ("ops-agent/tests/test_rag", ["ops-agent/docs/rag-architecture-and-tests.md"], ["test-rag"]),
    ("ops-agent/tests/test_hybrid_retrieval", ["ops-agent/docs/rag-architecture-and-tests.md"], ["test-rag"]),
    ("ops-agent/tests/test_runbook_eval_policy", ["ops-agent/docs/rag-architecture-and-tests.md §5.6"], ["test-rag"]),
    ("ops-agent/data/runbooks/", ["ops-agent/docs/rag-architecture-and-tests.md §5.4"], ["test-rag"]),
    ("ops-agent/app/graph/builder", ["ops-agent/docs/graph-agent-architecture.md", "ops-agent/docs/architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/runner", ["ops-agent/docs/graph-agent-architecture.md", "ops-agent/docs/architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/collection", ["ops-agent/docs/graph-agent-architecture.md", "ops-agent/docs/rag-architecture-and-tests.md §5.1"], ["test-graph", "test-rag"]),
    ("ops-agent/app/graph/state", ["ops-agent/docs/graph-agent-architecture.md", "ops-agent/docs/api-runtime-architecture.md"], ["test-graph"]),
    ("ops-agent/tests/graph_paths/", ["ops-agent/docs/graph-agent-architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/decide", ["ops-agent/docs/decide-remediation-architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/decide_spec", ["ops-agent/docs/decide-remediation-architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/nodes/decide", ["ops-agent/docs/decide-remediation-architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/nodes/verify_remediation", ["ops-agent/docs/decide-remediation-architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/nodes/eval_remediation", ["ops-agent/docs/decide-remediation-architecture.md"], ["test-graph"]),
    ("ops-agent/app/graph/nodes/approve", ["ops-agent/docs/decide-remediation-architecture.md"], ["test-graph"]),
    ("ops-agent/app/tools/", ["ops-agent/docs/decide-remediation-architecture.md"], ["test-graph"]),
    ("ops-agent/app/adapters/", ["ops-agent/docs/backend-adapters-architecture.md"], ["test-graph"]),
    ("ops-backend-simulator/", ["ops-backend-simulator/README.md"], ["test-simulator"]),
    ("ops-agent/app/main.py", ["ops-agent/docs/api-runtime-architecture.md"], ["test-api"]),
    ("ops-agent/app/config.py", ["ops-agent/docs/api-runtime-architecture.md"], ["test-api", "test-rag"]),
    ("ops-agent/app/llm/", ["ops-agent/docs/api-runtime-architecture.md"], ["test-api"]),
    ("ops-agent/app/memory/", ["ops-agent/docs/api-runtime-architecture.md"], ["test-graph"]),
    ("ops-agent/app/observability/", ["ops-agent/docs/api-runtime-architecture.md"], ["test-api"]),
    ("ops-agent/tests/test_tracing", ["ops-agent/docs/api-runtime-architecture.md"], ["test-api"]),
    ("ops-agent/tests/test_eval", ["ops-agent/docs/api-runtime-architecture.md"], ["test-api"]),
    ("ops-agent/scripts/run_scenarios.py", ["ops-agent/docs/test-scenario-trajectories.md"], ["test-api"]),
    ("ops-agent/app/graph/nodes/", ["ops-agent/docs/graph-agent-architecture.md"], ["test-graph"]),
    ("ops-backend/", ["ops-backend/README.md"], []),
    ("deploy/", ["ops-agent/docs/architecture.md §4"], []),
]

GENERIC_DOCS = ["docs/change-workflow.md", "AGENTS.md"]

# If every staged path matches one of these prefixes/suffixes, skip automated tests.
DOC_ONLY_PREFIXES = (
    "docs/",
    ".cursor/",
    "AGENTS.md",
    "README.md",
    "交接说明.md",
)
DOC_ONLY_SUFFIXES = (".md", ".mdc")

TARGET_ORDER = ["test-rag", "test-rag-retrieval", "test-rag-coverage", "test-graph", "test-simulator", "test-api", "test"]


@dataclass
class Impact:
    paths: list[str] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    doc_only: bool = False


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def is_doc_only_path(path: str) -> bool:
    p = _normalize(path)
    if p.startswith(DOC_ONLY_PREFIXES):
        return True
    if p.endswith(DOC_ONLY_SUFFIXES):
        return True
    if p == "Makefile" and "scripts/" not in p:
        # Makefile-only tweak: still run impact but allow doc workflow
        return True
    return False


def analyze(paths: list[str]) -> Impact:
    impact = Impact(paths=list(paths))
    if not paths:
        return impact

    impact.doc_only = all(is_doc_only_path(p) for p in paths)

    docs: list[str] = []
    targets: list[str] = []
    for path in paths:
        norm = _normalize(path)
        for fragment, doc_list, test_list in RULES:
            if fragment in norm:
                for d in doc_list:
                    if d not in docs:
                        docs.append(d)
                for t in test_list:
                    if t not in targets:
                        targets.append(t)
    impact.docs = docs
    impact.targets = dedupe_targets(targets)
    return impact


def dedupe_targets(targets: list[str]) -> list[str]:
    chosen = set(targets)
    if "test" in chosen and len(chosen) > 1:
        chosen.discard("test")
    return [t for t in TARGET_ORDER if t in chosen]


def git_paths(*, staged: bool) -> list[str]:
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


def run_make_targets(targets: list[str]) -> int:
    if not targets:
        return 0
    for target in targets:
        print(f"\n>>> make {target}", flush=True)
        result = subprocess.run(
            ["make", target],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            print(f"\npre-commit: `make {target}` failed (exit {result.returncode})", file=sys.stderr)
            return result.returncode
    return 0


def print_report(impact: Impact) -> None:
    print("Changed paths:")
    for p in impact.paths:
        print(f"  - {p}")

    print("\nAlways review:")
    for g in GENERIC_DOCS:
        print(f"  - {g}")

    if impact.doc_only:
        print("\nDoc-only change: skipping automated tests.")
        print("Reminder: check version notes / 变更记录 in component docs.")
        return

    print("\nSuggested docs:")
    if impact.docs:
        for d in impact.docs:
            print(f"  - {d}")
    else:
        print("  - ops-agent/docs/architecture.md（未命中规则，请手动分类）")

    print("\nTest targets:")
    if impact.targets:
        for t in impact.targets:
            print(f"  make {t}")
    else:
        print("  (none — consider `make test` before push)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Use staged diff (pre-commit)")
    parser.add_argument("--run", action="store_true", help="Run suggested make targets")
    parser.add_argument("--quiet", action="store_true", help="Less output when running tests")
    parser.add_argument("paths", nargs="*", help="Override paths")
    args = parser.parse_args()

    if os_skip_hooks():
        print("SKIP_HOOKS=1 — skipping change_impact checks")
        return 0

    paths = args.paths or git_paths(staged=args.staged)
    impact = analyze(paths)

    if not args.quiet or not args.run:
        print_report(impact)

    if not args.run:
        if not impact.doc_only and not impact.targets and impact.paths:
            print("\nNo test rule matched; run `make test` before push if you changed code.")
        print("\nThen complete docs/change-workflow.md checklist before commit.")
        return 0

    if impact.doc_only:
        return 0
    if not impact.targets:
        return 0
    return run_make_targets(impact.targets)


def os_skip_hooks() -> bool:
    import os

    return os.environ.get("SKIP_HOOKS", "").strip() in {"1", "true", "yes"}


if __name__ == "__main__":
    sys.exit(main())
