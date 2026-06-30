#!/usr/bin/env python3
"""Scenario characterization runs — real LLM, step-by-step capture vs docs/test-scenario-trajectories.md."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from typing import Any, Callable

import httpx
import uvicorn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "ops-backend-simulator"))

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"), override=True)
os.environ.setdefault("LLM_MODE", "real")
os.environ.setdefault("CHECKPOINTER", "memory")

from app.adapters.backend_client import get_backend_client
from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario
from app.adapters.mock_remediation import clear_remediated
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
from simulator.app import app as sim_app

STATE_KEYS = (
    "status",
    "symptom_query",
    "novel_scenario",
    "novel_reason",
    "coverage_confidence",
    "selected_runbook_id",
    "runbook_candidates",
    "runbook_eval_reasoning",
    "relevant_runbook",
    "root_cause",
    "needs_human_review",
    "diagnosis_eval_reasoning",
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

SIM_PORT = 8081


def _apply_ci_mock_env() -> None:
    """Deterministic CI smoke: mock LLM, local embeddings, no LangSmith."""
    os.environ["LLM_MODE"] = "mock"
    os.environ["EMBEDDINGS_PROVIDER"] = "local-hash"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"


def _reset_caches() -> None:
    clear_remediated()
    reset_mock_scenarios()
    get_settings.cache_clear()
    build_graph.cache_clear()
    get_backend_client.cache_clear()


def _start_simulator() -> None:
    threading.Thread(
        target=lambda: uvicorn.run(sim_app, host="127.0.0.1", port=SIM_PORT, log_level="error"),
        daemon=True,
    ).start()
    for _ in range(40):
        try:
            if httpx.get(f"http://127.0.0.1:{SIM_PORT}/actuator/health", timeout=1).status_code == 200:
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("simulator failed to start")


def _pending_meta(thread_id: str) -> dict[str, Any]:
    graph = build_graph()
    snap = graph.get_state({"configurable": {"thread_id": thread_id}})
    if snap and snap.next:
        return {"pending_interrupt": True, "pending_node": snap.next[0]}
    return {"pending_interrupt": False, "pending_node": None}


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


def _response_dict(resp) -> dict[str, Any]:
    return {
        "status": resp.status,
        "novel_scenario": resp.novel_scenario,
        "symptom_query": resp.symptom_query,
        "novel_reason": resp.novel_reason,
        "selected_runbook_id": resp.selected_runbook_id,
        "coverage_confidence": resp.coverage_confidence,
        "runbook_eval_reasoning": resp.runbook_eval_reasoning,
        "root_cause": resp.root_cause,
        "decide_outcome": resp.decide_outcome,
        "decision_class": resp.decision_class,
        "escalation_hint": resp.escalation_hint,
        "recommendations": resp.recommendations,
        "knowledge_gaps": resp.knowledge_gaps,
        "pending_tool_calls": resp.pending_tool_calls,
        "execution_results": resp.execution_results,
        "needs_approval": resp.needs_approval,
        "incident_resolved": resp.incident_resolved,
        "remediation_attempt": resp.remediation_attempt,
        "summary": resp.summary,
        "runbook_draft": (resp.runbook_draft or "")[:500] if resp.runbook_draft else None,
        "evidence_refs": [e.ref for e in resp.evidence],
    }


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


def run_kb_01() -> dict[str, Any]:
    """KB-01: novel + ambiguous ecomm-search → uncertain → runbook HITL writeback."""
    _apply_ci_mock_env()
    os.environ["BACKEND_MODE"] = "mock"
    _reset_caches()
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
        steps[0]["response"]["novel_scenario"] is True
        and steps[0]["response"]["decide_outcome"] == "uncertain"
        and steps[-1]["graph_state"].get("runbook_saved_path")
    )
    return _result("KB-01", "novel ambiguous runbook writeback", passed=passed, steps=steps, t0=t0, backend="mock")


def run_kb_02() -> dict[str, Any]:
    """KB-02: novel + clear OOM pattern ecomm-cache → actionable fix → runbook writeback."""
    _apply_ci_mock_env()
    os.environ["BACKEND_MODE"] = "mock"
    _reset_caches()
    t0 = time.time()
    steps: list[dict] = []

    incident = IncidentInput(
        service="ecomm-cache",
        description="【P1】ecomm-cache Redis 缓存连接失败，读延迟飙升，Pod 频繁重启",
    )
    thread_id, resp, meta = start_diagnosis(incident)
    steps.append(_step("1_start_diagnosis", resp, meta, thread_id))

    if meta.get("pending_node") == "request_runbook_notes":
        resp = resume_runbook_notes(
            thread_id,
            "OOMKilled pod; rolling restart recovered cache connections.",
        )
        steps.append(_step("2_resume_runbook_notes", resp, _pending_meta(thread_id), thread_id))

    if resp.status == "awaiting_runbook_review":
        resp = resume_runbook_review(thread_id, approved=True)
        steps.append(_step("3_resume_runbook_review", resp, _pending_meta(thread_id), thread_id))

    passed = bool(
        steps[0]["response"]["novel_scenario"] is True
        and steps[0]["response"]["decide_outcome"] == "actionable"
        and steps[0]["response"].get("incident_resolved") is True
        and steps[-1]["graph_state"].get("runbook_saved_path")
    )
    return _result("KB-02", "novel actionable then runbook writeback", passed=passed, steps=steps, t0=t0, backend="mock")


def run_dec_01() -> dict[str, Any]:
    """DEC-01: static out_of_scope (discount-bug)."""
    _start_simulator()
    os.environ["BACKEND_MODE"] = "real"
    os.environ["BACKEND_BASE_URL"] = f"http://127.0.0.1:{SIM_PORT}"
    _reset_caches()

    client = httpx.Client(base_url=f"http://127.0.0.1:{SIM_PORT}", timeout=120.0)
    client.post("/admin/scenario/ecomm-manager-discount-bug").raise_for_status()
    client.post("/admin/reset").raise_for_status()
    sim_before = client.get("/admin/state").json()

    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家反馈订单金额异常，后台 5xx 与金额校验告警增多",
    )
    t0 = time.time()
    thread_id, resp, meta = start_diagnosis(incident)
    sim_after = client.get("/admin/state").json()
    steps = [_step("1_start_diagnosis", resp, meta, thread_id, {"simulator_after": sim_after})]

    passed = bool(
        resp.decide_outcome == "out_of_scope"
        and not resp.execution_results
        and resp.status == "completed"
        and sim_before.get("phase") == "BROKEN"
        and sim_after.get("recovered") is False
    )
    return _result("DEC-01", "static out_of_scope", passed=passed, steps=steps, t0=t0, backend="simulator")


def run_loop_02() -> dict[str, Any]:
    """LOOP-02: chaos-morph recoverable react loop (real LLM characterization)."""
    _start_simulator()
    os.environ["BACKEND_MODE"] = "real"
    os.environ["BACKEND_BASE_URL"] = f"http://127.0.0.1:{SIM_PORT}"
    set_mock_scenario("ecomm-manager", "chaos-morph")
    _reset_caches()

    client = httpx.Client(base_url=f"http://127.0.0.1:{SIM_PORT}", timeout=120.0)
    client.post("/admin/scenario/ecomm-manager-chaos-morph").raise_for_status()
    client.post("/admin/reset").raise_for_status()

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
        steps[0]["response"]["novel_scenario"] is False
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
    """LOOP-03: chaos-exhaust — never recovers."""
    _start_simulator()
    os.environ["BACKEND_MODE"] = "real"
    os.environ["BACKEND_BASE_URL"] = f"http://127.0.0.1:{SIM_PORT}"
    set_mock_scenario("ecomm-manager", "chaos-exhaust")
    _reset_caches()

    client = httpx.Client(base_url=f"http://127.0.0.1:{SIM_PORT}", timeout=120.0)
    client.post("/admin/scenario/ecomm-manager-chaos-exhaust").raise_for_status()
    client.post("/admin/reset").raise_for_status()

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
    )
    return _result("LOOP-03", "chaos-exhaust", passed=passed, steps=steps, t0=t0, backend="simulator")


def run_dec_02() -> dict[str, Any]:
    """DEC-02: chaos-oos early out_of_scope."""
    _start_simulator()
    os.environ["BACKEND_MODE"] = "real"
    os.environ["BACKEND_BASE_URL"] = f"http://127.0.0.1:{SIM_PORT}"
    set_mock_scenario("ecomm-manager", "chaos-oos")
    _reset_caches()

    client = httpx.Client(base_url=f"http://127.0.0.1:{SIM_PORT}", timeout=120.0)
    client.post("/admin/scenario/ecomm-manager-chaos-oos").raise_for_status()
    client.post("/admin/reset").raise_for_status()

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

DEFAULT_SCENARIOS = ("KB-01", "DEC-01")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scenario characterization (real LLM).")
    parser.add_argument(
        "--scenarios",
        nargs="*",
        choices=[*SCENARIO_RUNNERS.keys(), "all"],
        default=list(DEFAULT_SCENARIOS),
        help="Scenario IDs from docs/test-scenario-trajectories.md",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Force LLM_MODE=mock (for CI smoke of scenario runners)",
    )
    args = parser.parse_args()
    if args.mock_llm:
        _apply_ci_mock_env()
        get_settings.cache_clear()
        build_graph.cache_clear()
    selected = list(SCENARIO_RUNNERS.keys()) if "all" in args.scenarios else args.scenarios

    results = [SCENARIO_RUNNERS[sid]() for sid in selected]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if not all(r["passed"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
