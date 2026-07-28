"""ASCII path graphs for demo catalog and recap."""

from __future__ import annotations

from typing import Iterable

# Canonical remediation path nodes (main graph).
PATH_NODES = (
    "triage",
    "retrieve_runbooks",
    "diagnose",
    "decide",
    "approve",
    "write_tools",
    "verify_remediation",
    "summarize",
)

NODE_SHORT = {
    "triage": "采集",
    "retrieve_runbooks": "RAG",
    "diagnose": "诊断",
    "decide": "决策",
    "approve": "人审",
    "write_tools": "执行",
    "verify_remediation": "验收",
    "summarize": "总结",
}

EXPECTED_PATHS: dict[str, list[str]] = {
    "DEMO-01": [
        "triage",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "write_tools",
        "verify_remediation",
        "summarize",
    ],
    "DEMO-02": [
        "triage",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "approve",
        "write_tools",
        "verify_remediation",
        "summarize",
    ],
    "DEMO-03": [
        # LOOP-02：首轮 write 后 morph；二轮 diagnose→decide 直接 summarize（无二次 write）
        "triage",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "write_tools",
        "verify_remediation",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "summarize",
    ],
    "DEMO-04": [
        # DEC-01：confidence 足够时必经 decide，再 out_of_scope → summarize
        "triage",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "summarize",
    ],
    "DEMO-05": [
        # DEC-02：首轮 write 暴露逻辑缺陷；二轮 decide out_of_scope → summarize
        "triage",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "write_tools",
        "verify_remediation",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "summarize",
    ],
    "DEMO-H1": [
        "triage",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "write_tools",
        "verify_remediation",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "write_tools",
        "verify_remediation",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "write_tools",
        "verify_remediation",
        "summarize",
    ],
    "DEMO-H2a": [
        "triage",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "write_tools",
        "verify_remediation",
        "summarize",
    ],
}


def _label(node: str) -> str:
    return NODE_SHORT.get(node, node)


def render_path(nodes: Iterable[str], *, width: int = 50) -> str:
    seq = list(nodes)
    if not seq:
        return "(empty)"
    parts = [_label(n) for n in seq]
    line = " → ".join(parts)
    if len(line) > width:
        # Wrap long morph loops into two lines.
        mid = len(parts) // 2
        line = " → ".join(parts[:mid]) + "\n      → " + " → ".join(parts[mid:])
    return line


def render_compare(expected: list[str], actual: list[str]) -> str:
    exp_line = render_path(expected)
    act_line = render_path(actual)
    match = "✓" if actual == expected or _collapse_loops(actual) == tuple(expected) else "≈"
    return (
        f"  预期路径 {match}\n"
        f"    {exp_line}\n"
        f"  实际路径\n"
        f"    {act_line}"
    )


def _collapse_loops(visited: list[str]) -> tuple[str, ...]:
    """Compare path shape ignoring repeat counts beyond 2."""
    out: list[str] = []
    for node in visited:
        if len(out) >= 2 and out[-1] == node and out[-2] == node:
            continue
        out.append(node)
    return tuple(out)
