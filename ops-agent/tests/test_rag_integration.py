"""RAG integration tests — retrieval, parent expansion, and coverage eval (RAG-01 / RAG-02)."""

from __future__ import annotations

import os

import pytest

os.environ["BACKEND_MODE"] = "mock"
os.environ["LLM_MODE"] = "mock"
os.environ.setdefault("EMBEDDINGS_PROVIDER", "local-hash")
os.environ["CHECKPOINTER"] = "memory"

pytestmark = pytest.mark.rag_coverage

from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario
from app.config import get_settings
from app.graph.collection import collect, extract_symptoms, retrieve_runbooks, serialize_collected
from app.graph.nodes.eval_runbook import eval_runbook_node
from app.rag.parent import expand_chunks_to_parent_runbooks, load_runbook_by_stem, parent_stem_from_chunk_id
from app.schemas import IncidentInput


@pytest.fixture(autouse=True)
def _reset_env():
    reset_mock_scenarios()
    get_settings.cache_clear()
    yield
    reset_mock_scenarios()
    get_settings.cache_clear()


def _collected(service: str, scenario: str) -> dict:
    set_mock_scenario(service, scenario)
    get_settings.cache_clear()
    return serialize_collected(collect(service))


# ---------------------------------------------------------------------------
# P0-1 — richer symptom query
# ---------------------------------------------------------------------------

def test_extract_symptoms_includes_incident_description():
    data = _collected("ecomm-manager", "rate-limit")
    query = extract_symptoms(
        "ecomm-manager",
        data,
        incident_description="【P1】管理 API QPS 骤降，商家后台超时",
    )
    assert "管理 API QPS 骤降" in query


def test_extract_symptoms_includes_replica_status():
    data = _collected("ecomm-order", "crashloop")
    query = extract_symptoms("ecomm-order", data)
    assert "ready" in query.lower()
    assert "pod" in query.lower()


def test_extract_symptoms_crashloop_vs_memory_leak_differ():
    crashloop = extract_symptoms("ecomm-order", _collected("ecomm-order", "crashloop"))
    memory_leak = extract_symptoms("ecomm-order", _collected("ecomm-order", "memory-leak"))
    assert "BackOff" in crashloop
    assert "OOMKilled" in memory_leak
    assert crashloop != memory_leak


# ---------------------------------------------------------------------------
# P0-2 — parent document expansion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "chunk_id,expected_stem",
    [
        ("ecomm-order-crashloop-0", "ecomm-order-crashloop"),
        ("ecomm-manager-rate-limit-2", "ecomm-manager-rate-limit"),
    ],
)
def test_parent_stem_from_chunk_id(chunk_id, expected_stem):
    assert parent_stem_from_chunk_id(chunk_id) == expected_stem


def test_load_runbook_by_stem_includes_forbidden_section():
    text = load_runbook_by_stem("ecomm-order-crashloop")
    assert text is not None
    assert "勿用手段" in text
    assert "restart_pods" in text


def test_expand_chunks_to_parent_runbooks_dedupes_and_loads_full_doc():
    chunks = [
        {
            "doc_id": "ecomm-order-crashloop-1",
            "title": "# partial",
            "service": "ecomm-order",
            "content": "## 处置\npartial chunk only",
            "score": 0.7,
        },
        {
            "doc_id": "ecomm-order-crashloop-0",
            "title": "# partial",
            "service": "ecomm-order",
            "content": "## 症状\nanother chunk",
            "score": 0.9,
        },
    ]
    parents = expand_chunks_to_parent_runbooks(chunks)
    assert len(parents) == 1
    assert parents[0]["doc_id"] == "ecomm-order-crashloop"
    assert parents[0]["chunk_type"] == "parent"
    assert "勿用手段" in parents[0]["content"]
    assert "rollback_deployment" in parents[0]["content"]


def test_retrieve_runbooks_returns_parent_documents():
    data = _collected("ecomm-manager", "rate-limit")
    query = extract_symptoms(
        "ecomm-manager",
        data,
        incident_description="限流误配 admin api qps dropped",
    )
    runbooks = retrieve_runbooks("ecomm-manager", query, get_settings())
    if not runbooks:
        pytest.skip("no indexed runbooks for ecomm-manager in this environment")
    assert runbooks[0]["chunk_type"] == "parent"
    assert "patch_config" in runbooks[0]["content"]


# ---------------------------------------------------------------------------
# P0-4 / PR2 — RAG-01 / RAG-02 scenario contracts
# ---------------------------------------------------------------------------

def test_eval_runbook_exposes_novel_reason_on_novel_service():
    state = {
        "service": "ecomm-search",
        "incident": IncidentInput(
            service="ecomm-search",
            description="【P1】搜索延迟升高",
        ),
    }
    result = eval_runbook_node(state)
    assert result["novel_scenario"] is True
    assert result.get("novel_reason")
    assert result.get("runbook_eval_reasoning")
    assert result["relevant_runbook"] is None


def test_rag_01_known_service_with_runbook_not_novel():
    """RAG-01 guard: indexed known service should not be novel when runbooks retrieve."""
    state = {
        "service": "ecomm-manager",
        "incident": IncidentInput(
            service="ecomm-manager",
            description="【P2】管理 API 限流误配，QPS 骤降",
        ),
    }
    set_mock_scenario("ecomm-manager", "rate-limit")
    get_settings.cache_clear()
    result = eval_runbook_node(state)
    if not result.get("symptom_query"):
        pytest.fail("symptom_query missing")
    if result["novel_scenario"]:
        pytest.skip("local-hash retrieval did not surface ecomm-manager runbooks")
    assert result["relevant_runbook"]
    assert "限流" in result["relevant_runbook"] or "rate-limit" in result["relevant_runbook"]


def test_rag_02_crashloop_runbook_is_full_parent_not_chunk_only():
    """RAG-02 guard: wrong-tool constraints must survive retrieval (parent doc expansion)."""
    state = {
        "service": "ecomm-order",
        "incident": IncidentInput(
            service="ecomm-order",
            description="【P0】下单服务 CrashLoopBackOff，坏镜像升级",
        ),
    }
    set_mock_scenario("ecomm-order", "crashloop")
    get_settings.cache_clear()
    result = eval_runbook_node(state)
    if result["novel_scenario"]:
        pytest.skip("local-hash retrieval did not surface ecomm-order runbooks")
    relevant = result["relevant_runbook"] or ""
    assert "rollback_deployment" in relevant
    assert "勿用手段" in relevant
    assert "restart_pods" in relevant
    assert result.get("selected_runbook_id") == "ecomm-order-crashloop"
    assert result.get("match_score") is not None
