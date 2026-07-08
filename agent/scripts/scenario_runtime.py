"""Shared simulator + graph helpers for run_scenarios.py and run_demo.py."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from app.adapters.backend_client import get_backend_client
from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario
from app.adapters.mock_remediation import clear_remediated
from app.config import get_settings
from app.graph.builder import build_graph

SIM_PORT = 8081
SIMULATOR_ROOT = Path(__file__).resolve().parents[2] / "ops-backend-simulator"

_active_session: "SimulatorSession | None" = None
_thread_started_ports: set[int] = set()


def simulator_is_healthy(port: int = SIM_PORT) -> bool:
    try:
        return (
            httpx.get(f"http://127.0.0.1:{port}/actuator/health", timeout=1).status_code == 200
        )
    except Exception:
        return False


def _wait_for_simulator(port: int, *, attempts: int = 40) -> None:
    for _ in range(attempts):
        if simulator_is_healthy(port):
            return
        time.sleep(0.25)
    raise RuntimeError(f"simulator failed to start on :{port}")


def _start_simulator_thread(port: int) -> None:
    if port in _thread_started_ports and simulator_is_healthy(port):
        return
    import uvicorn
    from simulator.app import app as sim_app

    threading.Thread(
        target=lambda: uvicorn.run(sim_app, host="127.0.0.1", port=port, log_level="error"),
        daemon=True,
    ).start()
    _thread_started_ports.add(port)
    _wait_for_simulator(port)


def _start_simulator_process(port: int) -> subprocess.Popen[Any]:
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "simulator.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        cwd=str(SIMULATOR_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_simulator(port)
    return proc


def reset_scenario_caches() -> None:
    clear_remediated()
    reset_mock_scenarios()
    get_settings.cache_clear()
    build_graph.cache_clear()
    get_backend_client.cache_clear()


def bind_real_simulator_backend(port: int = SIM_PORT) -> None:
    os.environ["BACKEND_MODE"] = "real"
    os.environ["BACKEND_BASE_URL"] = f"http://127.0.0.1:{port}"
    reset_scenario_caches()


def start_simulator(port: int = SIM_PORT) -> None:
    """Idempotent: reuse healthy simulator; do not spawn a second listener."""
    if simulator_is_healthy(port):
        return
    if _active_session is not None:
        raise RuntimeError("SimulatorSession is active but simulator is not healthy")
    _start_simulator_thread(port)


def prepare_simulator(
    simulator_scenario_id: str,
    *,
    mock_service: str,
    mock_scenario: str,
    port: int = SIM_PORT,
) -> httpx.Client:
    """Configure scenario on simulator. Reuses active SimulatorSession when present."""
    if _active_session is not None:
        return _active_session.prepare_act(
            simulator_scenario_id,
            mock_service=mock_service,
            mock_scenario=mock_scenario,
        )
    start_simulator(port)
    bind_real_simulator_backend(port)
    set_mock_scenario(mock_service, mock_scenario)
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=120.0)
    client.post(f"/admin/scenario/{simulator_scenario_id}").raise_for_status()
    client.post("/admin/reset").raise_for_status()
    return client


class SimulatorSession:
    """One simulator process per script run; acts switch scenario via admin API + reset."""

    def __init__(self, port: int = SIM_PORT, *, shutdown_on_exit: bool = True) -> None:
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.shutdown_on_exit = shutdown_on_exit
        self._proc: subprocess.Popen[Any] | None = None
        self._owned = False
        self._client: httpx.Client | None = None

    def __enter__(self) -> SimulatorSession:
        global _active_session
        if _active_session is not None:
            raise RuntimeError("Only one SimulatorSession may be active")
        _active_session = self
        if simulator_is_healthy(self.port):
            self._owned = False
        else:
            self._proc = _start_simulator_process(self.port)
            self._owned = True
        bind_real_simulator_backend(self.port)
        self._client = httpx.Client(base_url=self.base_url, timeout=120.0)
        return self

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            raise RuntimeError("SimulatorSession is not active")
        return self._client

    def __exit__(self, exc_type, exc, tb) -> None:
        global _active_session
        if self._client is not None:
            self._client.close()
            self._client = None
        if self.shutdown_on_exit and self._owned and self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        _active_session = None

    def prepare_act(
        self,
        simulator_scenario_id: str,
        *,
        mock_service: str,
        mock_scenario: str,
    ) -> httpx.Client:
        if self._client is None:
            raise RuntimeError("SimulatorSession is not active")
        bind_real_simulator_backend(self.port)
        set_mock_scenario(mock_service, mock_scenario)
        self._client.post(f"/admin/scenario/{simulator_scenario_id}").raise_for_status()
        self._client.post("/admin/reset").raise_for_status()
        return self._client


def lab_health(client: httpx.Client) -> dict[str, Any]:
    r = client.get("/actuator/health")
    r.raise_for_status()
    return r.json()


def lab_admin_state(client: httpx.Client) -> dict[str, Any]:
    r = client.get("/admin/state")
    r.raise_for_status()
    return r.json()


def lab_list_scenarios(client: httpx.Client) -> list[dict[str, Any]]:
    r = client.get("/admin/scenarios")
    r.raise_for_status()
    return r.json()


def lab_load_scenario(client: httpx.Client, scenario_id: str) -> dict[str, Any]:
    r = client.post(f"/admin/scenario/{scenario_id}")
    r.raise_for_status()
    return r.json()


def lab_reset(client: httpx.Client) -> dict[str, Any]:
    r = client.post("/admin/reset")
    r.raise_for_status()
    return r.json()


def lab_ops_action(client: httpx.Client, action: str, body: dict[str, Any]) -> dict[str, Any]:
    r = client.post(f"/api/v1/ops/{action}", json=body)
    r.raise_for_status()
    return r.json()


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
