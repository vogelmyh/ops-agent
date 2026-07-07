"""Shared fixtures for graph path tests (mock LLM + mock or simulator backend)."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

os.environ.setdefault("BACKEND_MODE", "mock")
os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "local-hash")
os.environ.setdefault("CHECKPOINTER", "memory")

SIM_ROOT = Path(__file__).resolve().parents[3] / "ops-backend-simulator"
sys.path.insert(0, str(SIM_ROOT))

from simulator.app import app as sim_app

from app.adapters.backend_client import get_backend_client
from app.adapters.mock_data import reset_mock_scenarios
from app.adapters.mock_remediation import clear_remediated
from app.config import get_settings
from app.graph.builder import build_graph
from app.memory.short_term import get_checkpointer


def start_simulator(port: int) -> None:
    threading.Thread(
        target=lambda: uvicorn.run(sim_app, host="127.0.0.1", port=port, log_level="error"),
        daemon=True,
    ).start()
    for _ in range(40):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/actuator/health", timeout=1).status_code == 200:
                return
        except Exception:
            time.sleep(0.25)
    pytest.fail(f"simulator failed to start on :{port}")


@pytest.fixture(autouse=True)
def _reset_graph_path_caches():
    os.environ["BACKEND_MODE"] = "mock"
    clear_remediated()
    reset_mock_scenarios()
    get_settings.cache_clear()
    build_graph.cache_clear()
    get_backend_client.cache_clear()
    get_checkpointer.cache_clear()
    yield
    clear_remediated()
    reset_mock_scenarios()
    build_graph.cache_clear()
    get_checkpointer.cache_clear()


@pytest.fixture
def thread_values():
    def _read(thread_id: str) -> dict:
        graph = build_graph()
        snap = graph.get_state({"configurable": {"thread_id": thread_id}})
        return dict(snap.values or {})

    return _read


@pytest.fixture
def resume_until_approved():
    from app.graph.runner import resume_approval

    def _run(thread_id: str, response, max_steps: int = 8):
        steps = 0
        while response.status != "completed" and steps < max_steps:
            if response.status == "awaiting_approval":
                response = resume_approval(thread_id, approved=True)
            else:
                break
            steps += 1
        return response

    return _run


@pytest.fixture(scope="module")
def simulator_8083():
    start_simulator(8083)
    yield


def _simulator_env(scenario_id: str, mock_key: str):
    from app.adapters.mock_data import set_mock_scenario

    os.environ["BACKEND_MODE"] = "real"
    os.environ["BACKEND_BASE_URL"] = "http://127.0.0.1:8083"
    set_mock_scenario("ecomm-manager", mock_key)
    get_settings.cache_clear()
    build_graph.cache_clear()
    get_backend_client.cache_clear()

    client = httpx.Client(base_url="http://127.0.0.1:8083", timeout=60.0)
    client.post(f"/admin/scenario/{scenario_id}").raise_for_status()
    client.post("/admin/reset").raise_for_status()
    return client


@pytest.fixture
def chaos_morph_env(simulator_8083):
    client = _simulator_env("ecomm-manager-chaos-morph", "chaos-morph")
    yield client
    os.environ["BACKEND_MODE"] = "mock"


@pytest.fixture
def cascade_exhaust_env(simulator_8083):
    client = _simulator_env("ecomm-manager-cascade-exhaust", "cascade-exhaust")
    yield client
    os.environ["BACKEND_MODE"] = "mock"


@pytest.fixture
def chaos_oos_env(simulator_8083):
    client = _simulator_env("ecomm-manager-chaos-oos", "chaos-oos")
    yield client
    os.environ["BACKEND_MODE"] = "mock"
