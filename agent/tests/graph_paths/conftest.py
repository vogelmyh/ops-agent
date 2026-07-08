"""Shared fixtures for graph path tests (mock LLM + mock or simulator backend)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("BACKEND_MODE", "mock")
os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "local-hash")
os.environ.setdefault("CHECKPOINTER", "memory")

OPS_AGENT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = OPS_AGENT_ROOT / "scripts"
SIM_ROOT = OPS_AGENT_ROOT.parent / "ops-backend-simulator"
sys.path.insert(0, str(SIM_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import scenario_runtime as rt

from app.adapters.backend_client import get_backend_client
from app.adapters.mock_data import reset_mock_scenarios
from app.adapters.mock_remediation import clear_remediated
from app.config import get_settings
from app.graph.builder import build_graph
from app.memory.short_term import get_checkpointer


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
    with rt.SimulatorSession(port=8083) as session:
        yield session


def _simulator_env(session: rt.SimulatorSession, scenario_id: str, mock_key: str):
    client = session.prepare_act(
        scenario_id,
        mock_service="ecomm-manager",
        mock_scenario=mock_key,
    )
    return client


@pytest.fixture
def chaos_morph_env(simulator_8083):
    client = _simulator_env(simulator_8083, "ecomm-manager-chaos-morph", "chaos-morph")
    yield client
    os.environ["BACKEND_MODE"] = "mock"


@pytest.fixture
def cascade_exhaust_env(simulator_8083):
    client = _simulator_env(simulator_8083, "ecomm-manager-cascade-exhaust", "cascade-exhaust")
    yield client
    os.environ["BACKEND_MODE"] = "mock"


@pytest.fixture
def chaos_oos_env(simulator_8083):
    client = _simulator_env(simulator_8083, "ecomm-manager-chaos-oos", "chaos-oos")
    yield client
    os.environ["BACKEND_MODE"] = "mock"
