"""Optional real-LLM rubric smoke (skipped in CI unless RAG_EVAL_REAL_LLM=1)."""

from __future__ import annotations

import os

import pytest

from app.config import get_settings
from app.rag.eval_harness import evaluate_real_llm_golden
from tests.rag_eval.golden import REAL_LLM_SMOKE_IDS, select_golden_cases

pytestmark = [pytest.mark.rag_eval, pytest.mark.real_llm_rag]

_requires_real = pytest.mark.skipif(
    os.environ.get("RAG_EVAL_REAL_LLM") != "1",
    reason="Set RAG_EVAL_REAL_LLM=1 and OPENAI_API_KEY to run real LLM rubric smoke",
)


@_requires_real
def test_real_llm_smoke_subset():
    os.environ["LLM_MODE"] = "real"
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.openai_api_key:
        pytest.skip("OPENAI_API_KEY not configured")

    cases = select_golden_cases(smoke_only=True)
    assert len(cases) == len(REAL_LLM_SMOKE_IDS)

    report = evaluate_real_llm_golden(cases, settings=settings)
    # Informational floor — real LLM may score lower than oracle; tune after baseline run.
    assert report.must_not_violation_rate == 0.0, "must not select forbidden runbooks"
    assert report.end_to_end_accuracy >= 0.5, (
        f"real LLM e2e={report.end_to_end_accuracy:.2f} "
        f"failed: {[c.case_id for c in report.cases if not c.passed]}"
    )
