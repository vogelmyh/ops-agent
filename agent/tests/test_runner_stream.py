"""Tests for graph runner stream APIs."""

from __future__ import annotations

import os

import pytest

os.environ["BACKEND_MODE"] = "mock"
os.environ["LLM_MODE"] = "mock"
os.environ["EMBEDDINGS_PROVIDER"] = "local-hash"
os.environ["CHECKPOINTER"] = "memory"
os.environ["LANGSMITH_TRACING"] = "false"

from app.adapters.backend_client import get_backend_client  # noqa: E402
from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario  # noqa: E402
from app.adapters.mock_remediation import clear_remediated  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.graph.builder import build_graph  # noqa: E402
from app.graph.runner import stream_diagnosis, stream_resume  # noqa: E402
from app.schemas import IncidentInput  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_caches(monkeypatch):
    monkeypatch.setenv("BACKEND_MODE", "mock")
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "local-hash")
    monkeypatch.setenv("CHECKPOINTER", "memory")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    clear_remediated()
    reset_mock_scenarios()
    get_settings.cache_clear()
    build_graph.cache_clear()
    get_backend_client.cache_clear()


def test_stream_diagnosis_emits_node_updates():
    visited: list[str] = []

    def on_node(name: str, _update: dict) -> None:
        visited.append(name)

    set_mock_scenario("ecomm-order", "stream-paused")
    incident = IncidentInput(
        service="ecomm-order",
        description="test stream diagnosis",
    )
    thread_id, resp, meta, stream_visited = stream_diagnosis(
        incident,
        on_node_update=on_node,
    )
    assert thread_id
    assert resp.status in {"completed", "awaiting_approval", "awaiting_runbook_notes"}
    assert visited == stream_visited
    assert visited[0] == "triage"
    assert "retrieve_runbooks" in visited
    assert "diagnose" in visited
    assert isinstance(meta["visited_nodes"], list)


def test_stream_diagnosis_hits_approve_interrupt():
    set_mock_scenario("ecomm-manager", "crashloop")
    incident = IncidentInput(
        service="ecomm-manager",
        description="crashloop HITL interrupt",
    )
    thread_id, resp, meta, visited = stream_diagnosis(incident)
    assert thread_id
    assert resp.status == "awaiting_approval"
    assert "approve" in visited
    assert "__interrupt__" not in visited
    assert meta["pending_interrupt"] is True
    assert meta["pending_node"] == "approve"


def test_hitl_path_matches_expected_after_resume():
    from demo_presenter.graph_art import EXPECTED_PATHS
    from demo_presenter.narrator import StreamNarrator

    set_mock_scenario("ecomm-manager", "crashloop")
    narrator = StreamNarrator(interactive=False)
    incident = IncidentInput(service="ecomm-manager", description="crashloop recap path")
    thread_id, resp, _meta, _ = stream_diagnosis(incident, on_node_update=narrator.on_node)
    assert resp.status == "awaiting_approval"
    stream_resume(thread_id, {"approved": True}, on_node_update=narrator.on_node)
    assert narrator.visited == EXPECTED_PATHS["DEMO-02"]


def test_stream_resume_after_hitl_mock():
    set_mock_scenario("ecomm-manager", "crashloop")
    incident = IncidentInput(
        service="ecomm-manager",
        description="crashloop stream resume",
    )
    thread_id, resp, meta, _ = stream_diagnosis(incident)
    assert resp.status == "awaiting_approval"
    more: list[str] = []
    resp2, meta2, visited = stream_resume(
        thread_id,
        {"approved": True},
        on_node_update=lambda n, _u: more.append(n),
    )
    assert resp2.thread_id == thread_id
    assert meta2["visited_nodes"] == visited
    assert visited == ["approve", "write_tools", "verify_remediation", "summarize"]
    assert resp2.status in {"completed", "awaiting_approval"}
