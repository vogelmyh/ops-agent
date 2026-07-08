"""Tests for demo_presenter helpers (no real LLM)."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS)

from demo_presenter import catalog, graph_art  # noqa: E402
from demo_presenter.narrator import NODE_STAGE  # noqa: E402


def test_present_catalog_has_seven_acts():
    assert len(catalog.PRESENT_ACT_IDS) == 7
    assert "DEMO-02" in catalog.PRESENT_ACT_IDS
    assert "DEMO-KB-01" not in catalog.PRESENT_ACT_IDS


def test_expected_paths_cover_present_acts():
    for act_id in catalog.PRESENT_ACT_IDS:
        assert act_id in graph_art.EXPECTED_PATHS
        assert graph_art.EXPECTED_PATHS[act_id][0] == "triage"


def test_render_path_includes_short_labels():
    line = graph_art.render_path(["triage", "decide", "summarize"])
    assert "采集" in line
    assert "决策" in line


def test_node_stage_labels_include_main_graph():
    assert NODE_STAGE["retrieve_runbooks"] == "[RAG·检索]"
    assert NODE_STAGE["verify_remediation"] == "[验收]"


def test_demo_04_path_includes_decide_before_summarize():
    path = graph_art.EXPECTED_PATHS["DEMO-04"]
    assert path == [
        "triage",
        "retrieve_runbooks",
        "diagnose",
        "decide",
        "summarize",
    ]


def test_demo_03_and_05_second_loop_ends_decide_summarize():
    second_loop_tail = ["retrieve_runbooks", "diagnose", "decide", "summarize"]
    for act_id in ("DEMO-03", "DEMO-05"):
        path = graph_art.EXPECTED_PATHS[act_id]
        assert path[-4:] == second_loop_tail


def test_demo_02_requires_hitl_pause():
    assert catalog.ACT_RUNTIME["DEMO-02"].pause_before_approve is True
    assert catalog.ACT_RUNTIME["DEMO-01"].pause_before_approve is False
