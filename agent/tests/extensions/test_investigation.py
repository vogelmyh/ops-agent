"""Smoke tests for detached investigation extension (not wired to main graph)."""

import os

import pytest

os.environ["BACKEND_MODE"] = "mock"
os.environ["LLM_MODE"] = "mock"
os.environ["CHECKPOINTER"] = "memory"

from langgraph.graph import StateGraph

from app.graph.extensions.investigation import attach_investigation
from app.graph.extensions.investigation.nodes import (
    investigate_agent_node,
    investigate_finalize_node,
)
from app.graph.state import AgentState
from app.schemas import IncidentInput


def test_investigation_nodes_importable():
    state: AgentState = {
        "service": "ecomm-catalog",
        "incident": IncidentInput(service="ecomm-catalog", description="catalog service anomaly"),
        "messages": [],
    }
    agent_result = investigate_agent_node(state)
    assert agent_result["messages"]

    state.update(agent_result)
    state["investigation_done"] = True
    finalize_result = investigate_finalize_node(state)
    assert finalize_result["investigation_summary"]
    assert finalize_result["investigation_done"] is True


def test_attach_investigation_registers_nodes():
    graph = StateGraph(AgentState)
    graph.add_node("decide", lambda s: s)
    graph.add_node("approve", lambda s: s)
    graph.add_node("summarize", lambda s: s)
    attach_investigation(graph)
    # Nodes registered without error; compile not required for this smoke test
    assert "investigate_agent" in graph.nodes
    assert "escalate" in graph.nodes
