"""Golden case selection helpers."""

from __future__ import annotations

from tests.rag_eval.golden import REAL_LLM_SMOKE_IDS, select_golden_cases


def test_smoke_subset_size():
    cases = select_golden_cases(smoke_only=True)
    assert len(cases) == len(REAL_LLM_SMOKE_IDS)


def test_select_by_challenge():
    cases = select_golden_cases(challenge_type="novel")
    assert cases
    assert all(c.challenge_type == "novel" for c in cases)
