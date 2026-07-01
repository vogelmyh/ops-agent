"""Tests for RAG observability helpers and run_scenarios smoke (mock LLM)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

os.environ.setdefault("BACKEND_MODE", "mock")
os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "local-hash")
os.environ.setdefault("CHECKPOINTER", "memory")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario
from app.config import get_settings
from app.graph.builder import build_graph
from app.graph.rag_observability import (
    compact_runbook_candidates,
    rag_snapshot_from_state,
)
from app.graph.eval_schemas import RunbookCoverageRubric, RunbookRelevanceRubric
from app.observability.tracing import _clear_tracing_env


def _reset_langsmith_context() -> None:
    import langsmith._internal._context as ls_context
    import langsmith.utils as ls_utils

    ls_context._GLOBAL_TRACING_ENABLED = None
    ls_context._TRACING_ENABLED.set(None)
    ls_utils.get_env_var.cache_clear()


@pytest.fixture(autouse=True)
def _reset():
    reset_mock_scenarios()
    get_settings.cache_clear()
    build_graph.cache_clear()
    yield
    reset_mock_scenarios()
    get_settings.cache_clear()
    build_graph.cache_clear()
    _clear_tracing_env()
    _reset_langsmith_context()


def test_compact_runbook_candidates_omits_full_content():
    candidates = [
        {
            "doc_id": "ecomm-order-crashloop",
            "service": "ecomm-order",
            "content": "# long runbook\n" + ("x" * 5000),
            "retrieval_scores": {
                "vector_score": 0.4,
                "bm25_score": 2.1,
                "rerank_score": 0.88,
            },
            "relevance": RunbookRelevanceRubric(
                doc_id="ecomm-order-crashloop",
                service_scope_match=0.25,
                symptom_match=0.25,
                telemetry_match=0.20,
                exclusion_clear=0.15,
            ).model_dump(),
            "coverage": RunbookCoverageRubric(
                doc_id="ecomm-order-crashloop",
                root_cause_fit=0.25,
                remediation_fit=0.25,
                forbidden_clear=0.20,
                verification_fit=0.15,
            ).model_dump(),
        },
    ]
    compact = compact_runbook_candidates(candidates)
    assert "content" not in compact[0]
    assert compact[0]["doc_id"] == "ecomm-order-crashloop"
    assert compact[0]["retrieval"]["rerank_score"] == 0.88
    assert compact[0]["relevance_score"] == pytest.approx(0.85)


def test_rag_snapshot_from_state():
    snap = rag_snapshot_from_state({
        "symptom_query": "ecomm-order BackOff CrashLoop",
        "novel_scenario": False,
        "novel_reason": None,
        "selected_runbook_id": "ecomm-order-crashloop",
        "coverage_confidence": 0.82,
        "runbook_eval_reasoning": "matched crashloop",
        "relevant_runbook": "# CrashLoop\n\n## 症状\nBackOff",
        "runbook_candidates": [],
    })
    assert snap["symptom_query"] == "ecomm-order BackOff CrashLoop"
    assert snap["selected_runbook_id"] == "ecomm-order-crashloop"
    assert snap["runbook_eval_reasoning"] == "matched crashloop"
    assert snap["relevant_runbook_title"] == "CrashLoop"
    assert snap["relevant_runbook_chars"] > 0


def test_run_kb_01_mock_scenario_runner():
    from scripts.run_scenarios import run_kb_01

    result = run_kb_01()
    assert result["passed"] is True
    step0 = result["steps"][0]
    assert step0["thread_id"]
    assert "rag" in step0
    assert step0["rag"]["novel_scenario"] is True
    assert step0["rag"].get("novel_reason")
    assert step0["rag"].get("runbook_eval_reasoning")
    assert step0["response"]["symptom_query"]


def test_run_kb_02_mock_scenario_runner():
    from scripts.run_scenarios import run_kb_02

    set_mock_scenario("ecomm-cache", "default")
    result = run_kb_02()
    assert result["passed"] is True
    rag = result["steps"][0]["rag"]
    assert rag["novel_scenario"] is True
    assert result["steps"][0]["response"]["decide_outcome"] == "actionable"


def test_run_scenarios_cli_mock_llm_kb01():
    script = os.path.join(ROOT, "scripts", "run_scenarios.py")
    proc = subprocess.run(
        [sys.executable, script, "--scenarios", "KB-01", "--mock-llm"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CHECKPOINTER": "memory",
            "BACKEND_MODE": "mock",
            "EMBEDDINGS_PROVIDER": "local-hash",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
        },
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload[0]["scenario_id"] == "KB-01"
    assert payload[0]["passed"] is True
    assert payload[0]["llm"] == "mock"
    assert payload[0]["steps"][0]["rag"]["symptom_query"]


def test_reset_caches_clears_prior_mock_scenario():
    """set_mock_scenario must run after _reset_caches in scenario runners."""
    from app.adapters.mock_data import get_mock_scenario
    from scripts.run_scenarios import _reset_caches

    set_mock_scenario("ecomm-manager", "discount-bug")
    _reset_caches()
    assert get_mock_scenario("ecomm-manager") == "rate-limit"
    set_mock_scenario("ecomm-manager", "discount-bug")
    assert get_mock_scenario("ecomm-manager") == "discount-bug"


def test_run_dec_01_mock_scenario_runner():
    from scripts.run_scenarios import run_dec_01

    result = run_dec_01()
    assert result["passed"] is True
    assert result["steps"][0]["response"]["decide_outcome"] == "out_of_scope"
    assert not result["steps"][0]["response"].get("execution_results")


def test_run_scenarios_cli_mock_llm_all():
    script = os.path.join(ROOT, "scripts", "run_scenarios.py")
    proc = subprocess.run(
        [sys.executable, script, "--scenarios", "all", "--mock-llm"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CHECKPOINTER": "memory",
            "BACKEND_MODE": "mock",
            "EMBEDDINGS_PROVIDER": "local-hash",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
        },
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout)
    assert len(payload) == 6
    assert all(row["passed"] for row in payload), [
        (row["scenario_id"], row["passed"]) for row in payload if not row["passed"]
    ]


def test_check_dec_01_passed_novel_hitl_path():
    from types import SimpleNamespace

    from scripts.run_scenarios import check_dec_01_passed

    resp = SimpleNamespace(
        decide_outcome="out_of_scope",
        execution_results=[],
        novel_scenario=True,
        status="awaiting_runbook_notes",
    )
    meta = {"pending_node": "request_runbook_notes", "pending_interrupt": True}
    sim_before = {"phase": "BROKEN"}
    sim_after = {"recovered": False}
    assert check_dec_01_passed(resp, meta, sim_before=sim_before, sim_after=sim_after)


def test_check_dec_01_passed_completed_when_not_novel():
    from types import SimpleNamespace

    from scripts.run_scenarios import check_dec_01_passed

    resp = SimpleNamespace(
        decide_outcome="out_of_scope",
        execution_results=[],
        novel_scenario=False,
        status="completed",
    )
    meta = {"pending_interrupt": False, "pending_node": None}
    assert check_dec_01_passed(
        resp, meta, sim_before={"phase": "BROKEN"}, sim_after={"recovered": False},
    )


def test_check_dec_01_fails_when_novel_but_completed_status():
    from types import SimpleNamespace

    from scripts.run_scenarios import check_dec_01_passed

    resp = SimpleNamespace(
        decide_outcome="out_of_scope",
        execution_results=[],
        novel_scenario=True,
        status="completed",
    )
    meta = {"pending_node": None, "pending_interrupt": False}
    assert not check_dec_01_passed(
        resp, meta, sim_before={"phase": "BROKEN"}, sim_after={"recovered": False},
    )
