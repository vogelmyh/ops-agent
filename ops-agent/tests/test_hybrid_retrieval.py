"""Tests for hybrid BM25 + vector retrieval and rerank pipeline."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("BACKEND_MODE", "mock")

pytestmark = pytest.mark.rag_only
os.environ.setdefault("EMBEDDINGS_PROVIDER", "local-hash")

from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario
from app.config import get_settings
from app.graph.collection import collect, extract_symptoms, retrieve_runbook_candidates, serialize_collected
from app.rag.hybrid import hybrid_search_chunks, reciprocal_rank_fusion
from app.rag.rerank import lexical_overlap_score, rerank_chunks
from app.rag.retrieval import retrieve_ranked_parent_chunks
from app.rag.tokenize import tokenize


@pytest.fixture(autouse=True)
def _reset():
    reset_mock_scenarios()
    get_settings.cache_clear()
    yield
    reset_mock_scenarios()
    get_settings.cache_clear()


def test_tokenize_mixed_cn_en():
    tokens = tokenize("BackOff ecomm-order CrashLoop 限流")
    assert "backoff" in tokens
    assert "ecomm-order" in tokens
    assert "限" in tokens


def test_reciprocal_rank_fusion_combines_lists():
    fused = reciprocal_rank_fusion(
        [["a", "b", "c"], ["b", "a", "d"]],
        rrf_k=60,
    )
    assert fused["a"] > fused["c"]
    assert fused["b"] > fused["d"]


def test_lexical_overlap_prefers_matching_terms():
    q = "BackOff CrashLoopBackOff bad image upgrade"
    high = lexical_overlap_score(q, "Pod CrashLoopBackOff BackOff bad image ecomm-order:3.3.0-bad")
    low = lexical_overlap_score(q, "stream order-events paused no ingest")
    assert high > low


def test_hybrid_search_returns_fusion_and_bm25_scores():
    results = hybrid_search_chunks(
        "ecomm-order BackOff CrashLoop",
        service="ecomm-order",
    )
    if not results:
        pytest.skip("empty chroma index")
    assert any(r.get("fusion_score") for r in results)
    assert any(r.get("bm25_score") for r in results)


def test_rerank_prefers_crashloop_for_crashloop_query():
    set_mock_scenario("ecomm-order", "crashloop")
    data = serialize_collected(collect("ecomm-order"))
    query = extract_symptoms("ecomm-order", data, incident_description="CrashLoopBackOff 坏镜像")

    hybrid = hybrid_search_chunks(query, service="ecomm-order")
    if not hybrid:
        pytest.skip("empty chroma index")

    ranked = rerank_chunks(query, hybrid, top_k=10)
    parent_ids = []
    from app.rag.parent import parent_stem_from_chunk_id

    for chunk in ranked:
        stem = parent_stem_from_chunk_id(chunk["doc_id"])
        if stem and stem not in parent_ids:
            parent_ids.append(stem)

    if len(parent_ids) < 2:
        pytest.skip("not enough ecomm-order runbooks indexed")

    assert parent_ids[0] == "ecomm-order-crashloop"


def test_retrieve_ranked_parent_chunks_top3():
    set_mock_scenario("ecomm-manager", "rate-limit")
    data = serialize_collected(collect("ecomm-manager"))
    query = extract_symptoms(
        "ecomm-manager",
        data,
        incident_description="rate limit max-qps admin api qps dropped",
    )
    parents = retrieve_ranked_parent_chunks(query, service="ecomm-manager")
    if not parents:
        pytest.skip("empty chroma index")
    assert len(parents) <= 3
    assert parents[0].get("rerank_score") is not None
    assert parents[0]["chunk_type"] == "parent"


def test_retrieve_runbook_candidates_populates_retrieval_scores():
    set_mock_scenario("ecomm-order", "crashloop")
    data = serialize_collected(collect("ecomm-order"))
    query = extract_symptoms("ecomm-order", data, incident_description="CrashLoopBackOff")
    candidates = retrieve_runbook_candidates("ecomm-order", query)
    if not candidates:
        pytest.skip("empty chroma index")
    scores = candidates[0].retrieval_scores
    assert scores.bm25_score is not None or scores.rerank_score is not None
