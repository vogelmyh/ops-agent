"""RAG offline golden-set retrieval evaluation."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("BACKEND_MODE", "mock")
os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "local-hash")
os.environ.setdefault("CHECKPOINTER", "memory")

from app.config import get_settings
from app.rag.eval_harness import evaluate_retrieval_golden
from tests.rag_eval.golden import GOLDEN_CASES

pytestmark = pytest.mark.rag_eval


@pytest.fixture
def report():
    get_settings.cache_clear()
    return evaluate_retrieval_golden(GOLDEN_CASES, settings=get_settings())


def test_golden_corpus_size():
    assert len(GOLDEN_CASES) >= 40


def test_easy_match_recall(report):
    easy = [c for c in report.cases if c.challenge_type == "easy_match"]
    hits = sum(1 for c in easy if c.recall_at_3)
    rate = hits / max(len(easy), 1)
    assert rate >= 0.70, f"easy_match recall@3={rate:.2f} failed cases: {[c.case_id for c in easy if not c.recall_at_3]}"


def test_no_must_not_top1_violations(report):
    violations = [c for c in report.cases if c.must_not_violation]
    assert not violations, f"must_not_select in top1: {[c.case_id for c in violations]}"


def test_same_service_disambiguation_recall(report):
    hard = [c for c in report.cases if c.challenge_type == "same_service_disambiguation"]
    hits = sum(1 for c in hard if c.recall_at_3)
    rate = hits / max(len(hard), 1)
    # BM25 + lexical rerank on local-hash; threshold rises with real embeddings
    min_rate = 0.45 if get_settings().embeddings_provider == "local-hash" else 0.65
    assert rate >= min_rate, (
        f"disambig recall@3={rate:.2f} failures: "
        f"{[c.case_id for c in hard if not c.recall_at_3]}"
    )


def test_overall_recall_floor(report):
    with_expected = [c for c in report.cases if c.expected_doc_id]
    hits = sum(1 for c in with_expected if c.recall_at_3)
    rate = hits / max(len(with_expected), 1)
    min_rate = 0.55 if get_settings().embeddings_provider == "local-hash" else 0.75
    assert rate >= min_rate, f"overall recall@3={rate:.2f}"
