"""Shared simulator + graph helpers for run_scenarios.py and run_demo.py."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx
import uvicorn

from app.adapters.backend_client import get_backend_client
from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario
from app.adapters.mock_remediation import clear_remediated
from app.config import get_settings
from app.graph.builder import build_graph

SIM_PORT = 8081


def reset_scenario_caches() -> None:
    clear_remediated()
    reset_mock_scenarios()
    get_settings.cache_clear()
    build_graph.cache_clear()
    get_backend_client.cache_clear()


def start_simulator() -> None:
    from simulator.app import app as sim_app

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


def bind_real_simulator_backend() -> None:
    os.environ["BACKEND_MODE"] = "real"
    os.environ["BACKEND_BASE_URL"] = f"http://127.0.0.1:{SIM_PORT}"
    reset_scenario_caches()


def prepare_simulator(
    simulator_scenario_id: str,
    *,
    mock_service: str,
    mock_scenario: str,
) -> httpx.Client:
    """Start simulator, select scenario, reset state, align mock_data key."""
    start_simulator()
    bind_real_simulator_backend()
    set_mock_scenario(mock_service, mock_scenario)
    client = httpx.Client(base_url=f"http://127.0.0.1:{SIM_PORT}", timeout=120.0)
    client.post(f"/admin/scenario/{simulator_scenario_id}").raise_for_status()
    client.post("/admin/reset").raise_for_status()
    return client


def pending_meta(thread_id: str) -> dict[str, Any]:
    graph = build_graph()
    snap = graph.get_state({"configurable": {"thread_id": thread_id}})
    if snap and snap.next:
        return {"pending_interrupt": True, "pending_node": snap.next[0]}
    return {"pending_interrupt": False, "pending_node": None}


def response_dict(resp) -> dict[str, Any]:
    return {
        "status": resp.status,
        "runbook_available": resp.runbook_available,
        "symptom_query": resp.symptom_query,
        "runbook_unavailable_reason": resp.runbook_unavailable_reason,
        "selected_runbook_id": resp.selected_runbook_id,
        "match_gate_reason": resp.match_gate_reason,
        "root_cause": resp.root_cause,
        "confidence_gate_reason": resp.confidence_gate_reason,
        "confidence_sufficient": resp.confidence_sufficient,
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
