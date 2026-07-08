"""RAG golden-set end-to-end coverage eval (retrieve + oracle rubric + finalize)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("BACKEND_MODE", "mock")
os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "local-hash")

from app.config import get_settings
from app.rag.eval_harness import evaluate_coverage_golden
from tests.rag_eval.golden import GOLDEN_CASES

pytestmark = pytest.mark.rag_coverage


@pytest.fixture
def coverage_report():
    get_settings.cache_clear()
    return evaluate_coverage_golden(GOLDEN_CASES, settings=get_settings())


def test_coverage_no_must_not_selections(coverage_report):
    violations = [c for c in coverage_report.cases if c.must_not_violation]
    assert not violations, f"forbidden runbook selected: {[c.case_id for c in violations]}"


def test_coverage_runbook_unavailable_accuracy(coverage_report):
    unavailable = [c for c in coverage_report.cases if not c.expected_runbook_available]
    hits = sum(1 for c in unavailable if not c.runbook_available)
    rate = hits / max(len(unavailable), 1)
    assert rate >= 0.75, (
        f"runbook_unavailable accuracy={rate:.2f} failures: "
        f"{[c.case_id for c in unavailable if c.runbook_available]}"
    )


def test_coverage_selection_accuracy(coverage_report):
    labeled = [c for c in coverage_report.cases if c.expected_doc_id]
    hits = sum(
        1 for c in labeled
        if c.runbook_available and c.selected_runbook_id == c.expected_doc_id
    )
    rate = hits / max(len(labeled), 1)
    min_rate = 0.85 if get_settings().embeddings_provider == "local-hash" else 0.90
    assert rate >= min_rate, (
        f"selection accuracy={rate:.2f} failures: "
        f"{[c.case_id for c in labeled if c.selected_runbook_id != c.expected_doc_id or not c.runbook_available]}"
    )


def test_coverage_end_to_end_floor(coverage_report):
    rate = coverage_report.end_to_end_accuracy
    min_rate = 0.80 if get_settings().embeddings_provider == "local-hash" else 0.88
    failed = [c.case_id for c in coverage_report.cases if not c.passed]
    assert rate >= min_rate, f"e2e={rate:.2f} failed: {failed}"
