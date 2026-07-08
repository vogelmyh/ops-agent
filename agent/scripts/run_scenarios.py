#!/usr/bin/env python3
"""Scenario characterization — step-by-step JSON vs docs/test-scenario-trajectories.md.

LLM mode by scenario:
- KB-01 / KB-02: always mock LLM + mock backend (isolated smoke; see KB section in trajectories doc).
- DEC-01, LOOP-02, LOOP-03, DEC-02: use process LLM_MODE (default real) + simulator backend.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "ops-backend-simulator"))

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"), override=True)
os.environ.setdefault("LLM_MODE", "real")
os.environ.setdefault("CHECKPOINTER", "memory")

from app.adapters.mock_data import set_mock_scenario
from app.config import get_settings
from app.graph.builder import build_graph
from app.graph.rag_observability import (
    compact_runbook_candidates,
    rag_snapshot_from_state,
)
from app.graph.runner import (
    resume_approval,
    resume_runbook_notes,
    resume_runbook_review,
    start_diagnosis,
)
from app.schemas import IncidentInput

import scenario_runtime as rt

STATE_KEYS = (
    "status",
    "symptom_query",
    "runbook_available",
    "runbook_unavailable_reason",
    "match_gate_reason",
    "selected_runbook_id",
    "runbook_candidates",
    "runbook_match_rubrics",
    "relevant_runbook",
    "root_cause",
    "confidence_rubric",
    "confidence_gate_reason",
    "confidence_sufficient",
    "decide_outcome",
    "decision_class",
    "escalation_hint",
    "recommendations",
    "knowledge_gaps",
    "needs_approval",
    "incident_resolved",
    "remediation_attempt",
    "runbook_draft",
    "runbook_saved_path",
    "summary",
    "remediation_history",
)

SIM_PORT = rt.SIM_PORT
SCENARIO_REPORT_DIR = Path(ROOT) / "data" / "scenario_runs"
_ISOLATED_ENV_KEYS = (
    "LLM_MODE",
    "EMBEDDINGS_PROVIDER",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING_V2",
    "BACKEND_MODE",
)


def _apply_ci_mock_env() -> None:
    """Deterministic CI smoke: mock LLM, local embeddings, no LangSmith."""
    os.environ["LLM_MODE"] = "mock"
    os.environ["EMBEDDINGS_PROVIDER"] = "local-hash"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"


@contextmanager
def _isolated_mock_backend_env():
    """Apply mock LLM/backend for KB runners without polluting later scenarios."""
    saved = {key: os.environ.get(key) for key in _ISOLATED_ENV_KEYS}
    _apply_ci_mock_env()
    os.environ["BACKEND_MODE"] = "mock"
    _reset_caches()
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        _reset_caches()


def _reset_caches() -> None:
    rt.reset_scenario_caches()


def _pending_meta(thread_id: str) -> dict[str, Any]:
    return rt.pending_meta(thread_id)


def _response_dict(resp) -> dict[str, Any]:
    return rt.response_dict(resp)


def _prepare_sim(
    simulator_scenario_id: str,
    *,
    mock_service: str,
    mock_scenario: str,
) -> httpx.Client:
    return rt.prepare_simulator(
        simulator_scenario_id,
        mock_service=mock_service,
        mock_scenario=mock_scenario,
    )


def _graph_state(thread_id: str) -> dict[str, Any]:
    graph = build_graph()
    snap = graph.get_state({"configurable": {"thread_id": thread_id}})
    values = dict(snap.values or {})
    out = {k: values.get(k) for k in STATE_KEYS if k in values}
    if out.get("relevant_runbook"):
        out["relevant_runbook"] = (out["relevant_runbook"] or "")[:500]
    if out.get("runbook_candidates"):
        out["runbook_candidates"] = compact_runbook_candidates(out["runbook_candidates"])
    return out


def _step(name: str, resp, meta: dict, thread_id: str, extra: dict | None = None) -> dict[str, Any]:
    graph = build_graph()
    snap = graph.get_state({"configurable": {"thread_id": thread_id}})
    values = dict(snap.values or {})
    row = {
        "step": name,
        "thread_id": thread_id,
        "pending_interrupt": meta.get("pending_interrupt"),
        "pending_node": meta.get("pending_node"),
        "response": _response_dict(resp),
        "graph_state": _graph_state(thread_id),
        "rag": rag_snapshot_from_state(values),
    }
    if extra:
        row["extra"] = extra
    return row


def _result(
    scenario_id: str,
    label: str,
    *,
    passed: bool,
    steps: list[dict],
    t0: float,
    backend: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "label": label,
        "backend": backend,
        "llm": get_settings().llm_mode,
        "embeddings": get_settings().embeddings_provider,
        "langsmith": get_settings().langsmith_enabled,
        "thread_id": steps[0]["thread_id"] if steps else None,
        "elapsed_s": round(time.time() - t0, 1),
        "passed": passed,
        "steps": steps,
        **extra,
    }


def _scenario_summary_row(result: dict[str, Any]) -> dict[str, Any]:
    """Compact per-scenario row for stdout (no step payloads)."""
    last = result["steps"][-1]["response"] if result.get("steps") else {}
    row: dict[str, Any] = {
        "scenario_id": result["scenario_id"],
        "label": result.get("label"),
        "passed": result["passed"],
        "backend": result.get("backend"),
        "llm": result.get("llm"),
        "elapsed_s": result.get("elapsed_s"),
        "thread_id": result.get("thread_id"),
        "status": last.get("status"),
        "decide_outcome": last.get("decide_outcome"),
        "incident_resolved": last.get("incident_resolved"),
        "remediation_attempt": last.get("remediation_attempt"),
    }
    for key in ("tools_sequence", "simulator_final"):
        if key in result:
            row[key] = result[key]
    return row


def _default_report_path() -> Path:
    SCENARIO_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return SCENARIO_REPORT_DIR / f"run_scenarios_{stamp}.json"


def _write_report(results: list[dict[str, Any]], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _stdout_summary(results: list[dict[str, Any]], report_path: Path) -> dict[str, Any]:
    return {
        "all_passed": all(r["passed"] for r in results),
        "report_path": str(report_path.resolve()),
        "scenario_count": len(results),
        "scenarios": [_scenario_summary_row(r) for r in results],
    }


def run_kb_01() -> dict[str, Any]:
    """KB-01: no runbook + low-confidence ecomm-search → skipped_low_confidence → runbook HITL writeback.

    Always runs under mock LLM + mock backend (not real LLM characterization).
    """
    with _isolated_mock_backend_env():
        t0 = time.time()
        steps: list[dict] = []

        incident = IncidentInput(
            service="ecomm-search",
            description="【P1】ecomm-search 商品搜索 P99 延迟超 5s，索引重建任务失败，持续 20 分钟",
        )
        thread_id, resp, meta = start_diagnosis(incident)
        steps.append(_step("1_start_diagnosis", resp, meta, thread_id))

        if meta.get("pending_node") == "request_runbook_notes":
            resp = resume_runbook_notes(
                thread_id,
                "Identified stale search index under /data/search-index; rebuilt from backup.",
            )
            steps.append(_step("2_resume_runbook_notes", resp, _pending_meta(thread_id), thread_id))

        if resp.status == "awaiting_runbook_review":
            resp = resume_runbook_review(thread_id, approved=True)
            steps.append(_step("3_resume_runbook_review", resp, _pending_meta(thread_id), thread_id))

        passed = bool(
            steps[0]["response"]["runbook_available"] is False
            and steps[0]["response"]["decide_outcome"] == "skipped_low_confidence"
            and steps[-1]["graph_state"].get("runbook_saved_path")
        )
        return _result("KB-01", "explore ambiguous runbook writeback", passed=passed, steps=steps, t0=t0, backend="mock")


def run_kb_02() -> dict[str, Any]:
    """KB-02: no runbook + clear OOM pattern ecomm-cache → approve → fix → runbook writeback.

    Always runs under mock LLM + mock backend (not real LLM characterization).
    """
    with _isolated_mock_backend_env():
        t0 = time.time()
        steps: list[dict] = []

        incident = IncidentInput(
            service="ecomm-cache",
            description="【P1】ecomm-cache Redis 缓存连接失败，读延迟飙升，Pod 频繁重启",
        )
        thread_id, resp, meta = start_diagnosis(incident)
        steps.append(_step("1_start_diagnosis", resp, meta, thread_id))

        if meta.get("pending_node") == "approve":
            resp = resume_approval(thread_id, approved=True)
            steps.append(_step("2_resume_approval", resp, _pending_meta(thread_id), thread_id))

        if resp.status == "awaiting_runbook_notes":
            resp = resume_runbook_notes(
                thread_id,
                "OOMKilled pod; rolling restart recovered cache connections.",
            )
            steps.append(_step("3_resume_runbook_notes", resp, _pending_meta(thread_id), thread_id))

        if resp.status == "awaiting_runbook_review":
            resp = resume_runbook_review(thread_id, approved=True)
            steps.append(_step("4_resume_runbook_review", resp, _pending_meta(thread_id), thread_id))

        resolved = any(s["response"].get("incident_resolved") for s in steps)
        passed = bool(
            steps[0]["response"]["runbook_available"] is False
            and steps[0]["response"]["decide_outcome"] == "actionable"
            and resolved
            and steps[-1]["graph_state"].get("runbook_saved_path")
        )
        return _result("KB-02", "explore actionable then runbook writeback", passed=passed, steps=steps, t0=t0, backend="mock")


def check_dec_01_passed(
    resp,
    meta: dict[str, Any],
    *,
    sim_before: dict[str, Any],
    sim_after: dict[str, Any],
) -> bool:
    """DEC-01 pass criteria aligned with graph routing (builder._route_after_summarize).

    Core: discount-bug → decide out_of_scope, no writes, simulator stays BROKEN.
    Terminal status depends on runbook_available:
    - runbook_available=false → summarize then request_runbook_notes (awaiting_runbook_notes)
    - runbook_available=true  → summarize then END (completed)
    """
    core = (
        resp.decide_outcome == "out_of_scope"
        and not resp.execution_results
        and sim_before.get("phase") == "BROKEN"
        and sim_after.get("recovered") is False
    )
    if not core:
        return False
    if not resp.runbook_available:
        return (
            resp.status == "awaiting_runbook_notes"
            and meta.get("pending_node") == "request_runbook_notes"
            and meta.get("pending_interrupt") is True
        )
    return resp.status == "completed"


def run_dec_01() -> dict[str, Any]:
    """DEC-01: static out_of_scope (discount-bug)."""
    client = _prepare_sim(
        "ecomm-manager-discount-bug",
        mock_service="ecomm-manager",
        mock_scenario="discount-bug",
    )
    sim_before = client.get("/admin/state").json()

    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家反馈订单金额异常，后台 5xx 与金额校验告警增多",
    )
    t0 = time.time()
    thread_id, resp, meta = start_diagnosis(incident)
    sim_after = client.get("/admin/state").json()
    steps = [_step("1_start_diagnosis", resp, meta, thread_id, {"simulator_after": sim_after})]

    passed = check_dec_01_passed(
        resp, meta, sim_before=sim_before, sim_after=sim_after,
    )
    return _result("DEC-01", "static out_of_scope", passed=passed, steps=steps, t0=t0, backend="simulator")


def run_loop_02() -> dict[str, Any]:
    """LOOP-02: chaos-morph recoverable react loop (real LLM characterization)."""
    client = _prepare_sim(
        "ecomm-manager-chaos-morph",
        mock_service="ecomm-manager",
        mock_scenario="chaos-morph",
    )

    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降超 80%，持续 15 分钟",
    )
    t0 = time.time()
    thread_id, resp, meta = start_diagnosis(incident)
    steps = [_step("1_start", resp, meta, thread_id, client.get("/admin/state").json())]

    guard = 0
    while resp.status == "awaiting_approval" and guard < 6:
        resp = resume_approval(thread_id, approved=True)
        steps.append(_step(f"approve_{guard+1}", resp, _pending_meta(thread_id), thread_id))
        guard += 1

    sim_final = client.get("/admin/state").json()
    history = steps[-1]["graph_state"].get("remediation_history") or []
    tools = [t for h in history for t in (h.get("tools_attempted") or [])]
    passed = bool(
        steps[0]["response"]["runbook_available"] is True
        and "patch_config" in tools
        and resp.incident_resolved is True
        and sim_final.get("phase") == "RECOVERED"
    )
    return _result(
        "LOOP-02",
        "chaos-morph recoverable",
        passed=passed,
        steps=steps,
        t0=t0,
        backend="simulator",
        tools_sequence=tools,
        simulator_final=sim_final,
    )


def run_loop_03() -> dict[str, Any]:
    """LOOP-03: cascade-exhaust — layered faults, never recovers."""
    client = _prepare_sim(
        "ecomm-manager-cascade-exhaust",
        mock_service="ecomm-manager",
        mock_scenario="cascade-exhaust",
    )

    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降超 80%，持续 15 分钟",
    )
    t0 = time.time()
    thread_id, resp, meta = start_diagnosis(incident)
    steps = [_step("1_start", resp, meta, thread_id)]

    while resp.status == "awaiting_approval":
        resp = resume_approval(thread_id, approved=True)
        steps.append(_step(f"approve_{len(steps)}", resp, _pending_meta(thread_id), thread_id))

    sim_after = client.get("/admin/state").json()
    passed = bool(
        resp.status == "completed"
        and resp.incident_resolved is False
        and resp.remediation_attempt == get_settings().max_remediation_attempts
        and sim_after.get("phase") == "BROKEN"
        and sim_after.get("details", {}).get("fault_layer") == "CONN_LEAK"
    )
    return _result("LOOP-03", "cascade-exhaust", passed=passed, steps=steps, t0=t0, backend="simulator")


def run_dec_02() -> dict[str, Any]:
    """DEC-02: chaos-oos early out_of_scope."""
    client = _prepare_sim(
        "ecomm-manager-chaos-oos",
        mock_service="ecomm-manager",
        mock_scenario="chaos-oos",
    )

    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家后台 QPS 下降，修复后订单金额校验告警增多",
    )
    t0 = time.time()
    thread_id, resp, meta = start_diagnosis(incident)
    sim_after = client.get("/admin/state").json()
    steps = [_step("1_start", resp, meta, thread_id, sim_after)]

    passed = bool(
        resp.status == "completed"
        and resp.decide_outcome == "out_of_scope"
        and resp.incident_resolved is False
        and len(resp.execution_results or []) == 1
        and sim_after["details"].get("fault_phase") == "REVEALED_LOGIC"
    )
    return _result("DEC-02", "chaos-oos early OOS", passed=passed, steps=steps, t0=t0, backend="simulator")


SCENARIO_RUNNERS: dict[str, Callable[[], dict[str, Any]]] = {
    "KB-01": run_kb_01,
    "KB-02": run_kb_02,
    "DEC-01": run_dec_01,
    "LOOP-02": run_loop_02,
    "LOOP-03": run_loop_03,
    "DEC-02": run_dec_02,
}

SIMULATOR_SCENARIO_IDS = frozenset({"DEC-01", "LOOP-02", "LOOP-03", "DEC-02"})

DEFAULT_SCENARIOS = ("KB-01", "DEC-01")


_RUN_SCENARIOS_EPILOG = """\
Examples:
  # KB mock smoke only (writes data/runbooks/ — check git status after)
  python scripts/run_scenarios.py --scenarios KB-01 KB-02

  # Real LLM + simulator (DEC / LOOP; KB excluded from real characterization)
  LLM_MODE=real BACKEND_MODE=real python scripts/run_scenarios.py \\
    --scenarios DEC-01 LOOP-02 LOOP-03 DEC-02

  # CI-friendly mock for all runners (KB still uses isolated mock env)
  python scripts/run_scenarios.py --mock-llm --scenarios all

See docs/agent/test-scenario-trajectories.md (KB · run_scenarios 定位).
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run scenario runners with step JSON. "
            "KB-01/KB-02 are fixed mock smoke; DEC/LOOP use LLM_MODE (default real) + simulator."
        ),
        epilog=_RUN_SCENARIOS_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scenarios",
        nargs="*",
        choices=[*SCENARIO_RUNNERS.keys(), "all"],
        default=list(DEFAULT_SCENARIOS),
        help="Scenario IDs (docs/test-scenario-trajectories.md). KB=* mock smoke; DEC/LOOP=real LLM when LLM_MODE=real",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Force LLM_MODE=mock for DEC/LOOP runners (KB runners always mock regardless)",
    )
    parser.add_argument(
        "--full-json",
        action="store_true",
        help="Print full step JSON to stdout (default: compact summary + report file)",
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        default=None,
        help=f"Write full step JSON to PATH (default: {SCENARIO_REPORT_DIR}/run_scenarios_<utc>.json)",
    )
    args = parser.parse_args()
    if args.mock_llm:
        _apply_ci_mock_env()
        get_settings.cache_clear()
        build_graph.cache_clear()
    selected = list(SCENARIO_RUNNERS.keys()) if "all" in args.scenarios else args.scenarios

    def _run_all() -> list[dict[str, Any]]:
        return [SCENARIO_RUNNERS[sid]() for sid in selected]

    if any(sid in SIMULATOR_SCENARIO_IDS for sid in selected):
        with rt.SimulatorSession():
            results = _run_all()
    else:
        results = _run_all()
    report_path = Path(args.report) if args.report else _default_report_path()
    _write_report(results, report_path)
    if args.full_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(_stdout_summary(results, report_path), ensure_ascii=False, indent=2))
    if not all(r["passed"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
