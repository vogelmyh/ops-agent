"""Offline RAG retrieval and coverage metrics over golden cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.graph.collection import extract_symptoms, retrieve_runbook_candidates
from app.graph.nodes.eval_runbook import run_runbook_eval


@dataclass
class CaseResult:
    case_id: str
    challenge_type: str
    difficulty: str
    expected_doc_id: str | None
    expected_runbook_available: bool
    top_doc_ids: list[str]
    recall_at_3: bool
    mrr: float
    wrong_top1: bool
    must_not_violation: bool
    symptom_query: str


@dataclass
class CoverageCaseResult:
    case_id: str
    challenge_type: str
    difficulty: str
    expected_doc_id: str | None
    expected_runbook_available: bool
    selected_runbook_id: str | None
    runbook_available: bool
    runbook_unavailable_reason: str | None
    passed: bool
    retrieval_recall_at_3: bool
    must_not_violation: bool
    symptom_query: str


@dataclass
class CoverageEvalReport:
    total: int
    end_to_end_accuracy: float
    runbook_unavailable_accuracy: float
    selection_accuracy: float
    must_not_violation_rate: float
    by_challenge: dict[str, dict[str, float]] = field(default_factory=dict)
    cases: list[CoverageCaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "end_to_end_accuracy": round(self.end_to_end_accuracy, 4),
            "runbook_unavailable_accuracy": round(self.runbook_unavailable_accuracy, 4),
            "selection_accuracy": round(self.selection_accuracy, 4),
            "must_not_violation_rate": round(self.must_not_violation_rate, 4),
            "by_challenge": self.by_challenge,
            "failed_cases": [
                {
                    "id": c.case_id,
                    "expected_doc": c.expected_doc_id,
                    "expected_runbook_available": c.expected_runbook_available,
                    "selected": c.selected_runbook_id,
                    "runbook_available": c.runbook_available,
                    "runbook_unavailable_reason": c.runbook_unavailable_reason,
                    "recall_at_3": c.retrieval_recall_at_3,
                }
                for c in self.cases
                if not c.passed
            ],
        }


@dataclass
class EvalReport:
    total: int
    recall_at_3: float
    mrr_at_1: float
    wrong_top1_rate: float
    must_not_violation_rate: float
    by_challenge: dict[str, dict[str, float]] = field(default_factory=dict)
    cases: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "recall_at_3": round(self.recall_at_3, 4),
            "mrr_at_1": round(self.mrr_at_1, 4),
            "wrong_top1_rate": round(self.wrong_top1_rate, 4),
            "must_not_violation_rate": round(self.must_not_violation_rate, 4),
            "by_challenge": self.by_challenge,
            "failed_cases": [
                {
                    "id": c.case_id,
                    "expected": c.expected_doc_id,
                    "got": c.top_doc_ids[:3],
                    "query": c.symptom_query[:200],
                }
                for c in self.cases
                if not c.recall_at_3 or c.must_not_violation
            ],
        }


def _mrr(rank: int | None) -> float:
    return 0.0 if rank is None else 1.0 / rank


def evaluate_retrieval_case(
    case: Any,
    *,
    settings=None,
) -> CaseResult:
    """Run retrieval for one golden case (no LLM eval)."""
    telemetry = getattr(case, "telemetry", {}) or {}
    symptom_query = extract_symptoms(
        case.service,
        telemetry,
        incident_description=case.incident_description,
    )
    candidates = retrieve_runbook_candidates(case.service, symptom_query, settings)
    top_ids = [c.doc_id for c in candidates]

    expected = case.expected_doc_id
    recall = False
    rank: int | None = None
    if expected:
        if expected in top_ids:
            recall = True
            rank = top_ids.index(expected) + 1
        else:
            recall = False
    elif not case.expected_runbook_available:
        # No runbook expected: empty or low-confidence retrieval is acceptable.
        recall = True
        rank = None

    must_not = set(getattr(case, "must_not_select", []) or [])
    violation = bool(must_not & set(top_ids[:1]))

    wrong_top1 = False
    if expected and top_ids and top_ids[0] != expected:
        wrong_top1 = True

    return CaseResult(
        case_id=case.id,
        challenge_type=case.challenge_type,
        difficulty=case.difficulty,
        expected_doc_id=expected,
        expected_runbook_available=case.expected_runbook_available,
        top_doc_ids=top_ids,
        recall_at_3=recall if expected else (not violation),
        mrr=_mrr(rank),
        wrong_top1=wrong_top1,
        must_not_violation=violation,
        symptom_query=symptom_query,
    )


def evaluate_retrieval_golden(
    cases: list[Any],
    *,
    settings=None,
) -> EvalReport:
    results = [evaluate_retrieval_case(c, settings=settings) for c in cases]
    with_expected = [r for r in results if r.expected_doc_id]
    total = len(results)
    recall = sum(1 for r in with_expected if r.recall_at_3) / max(len(with_expected), 1)
    mrr = sum(r.mrr for r in with_expected) / max(len(with_expected), 1)
    wrong = sum(1 for r in with_expected if r.wrong_top1) / max(len(with_expected), 1)
    violations = sum(1 for r in results if r.must_not_violation) / max(total, 1)

    by_challenge: dict[str, dict[str, float]] = {}
    for r in results:
        bucket = by_challenge.setdefault(r.challenge_type, {"n": 0, "recall": 0, "wrong": 0})
        bucket["n"] += 1
        if r.expected_doc_id and r.recall_at_3:
            bucket["recall"] += 1
        if r.wrong_top1:
            bucket["wrong"] += 1
    for bucket in by_challenge.values():
        n = max(int(bucket["n"]), 1)
        bucket["recall_at_3"] = round(bucket.pop("recall", 0) / n, 4)
        bucket["wrong_top1_rate"] = round(bucket.pop("wrong", 0) / n, 4)

    return EvalReport(
        total=total,
        recall_at_3=recall,
        mrr_at_1=mrr,
        wrong_top1_rate=wrong,
        must_not_violation_rate=violations,
        by_challenge=by_challenge,
        cases=results,
    )


def _coverage_pass(
    *,
    expected_doc_id: str | None,
    expected_runbook_available: bool,
    selected_runbook_id: str | None,
    runbook_available: bool,
    must_not_violation: bool,
) -> bool:
    if must_not_violation:
        return False
    if not expected_runbook_available:
        return runbook_available is False
    return (
        runbook_available
        and selected_runbook_id == expected_doc_id
    )


def evaluate_coverage_case(case: Any, *, settings=None) -> CoverageCaseResult:
    """Full pipeline: retrieve → oracle rubric (mock) → finalize."""
    return _evaluate_coverage_from_result(case, _run_eval_for_case(case, settings, golden_oracle=True), settings)


def evaluate_real_llm_case(case: Any, *, settings=None) -> CoverageCaseResult:
    """Full pipeline with real LLM rubric (no golden oracle)."""
    return _evaluate_coverage_from_result(case, _run_eval_for_case(case, settings, golden_oracle=False), settings)


def _run_eval_for_case(case: Any, settings, *, golden_oracle: bool) -> dict:
    telemetry = getattr(case, "telemetry", {}) or {}
    return run_runbook_eval(
        case.service,
        case.incident_description,
        collected_data=telemetry,
        settings=settings,
        golden_oracle=golden_oracle,
        oracle_expected_doc_id=case.expected_doc_id,
        oracle_expected_runbook_available=case.expected_runbook_available,
    )


def _evaluate_coverage_from_result(case: Any, result: dict, settings) -> CoverageCaseResult:
    retrieval = evaluate_retrieval_case(case, settings=settings)
    must_not = set(getattr(case, "must_not_select", []) or [])
    selected = result.get("selected_runbook_id")
    violation = bool(selected and selected in must_not)

    return CoverageCaseResult(
        case_id=case.id,
        challenge_type=case.challenge_type,
        difficulty=case.difficulty,
        expected_doc_id=case.expected_doc_id,
        expected_runbook_available=case.expected_runbook_available,
        selected_runbook_id=selected,
        runbook_available=bool(result.get("runbook_available")),
        runbook_unavailable_reason=result.get("runbook_unavailable_reason"),
        passed=_coverage_pass(
            expected_doc_id=case.expected_doc_id,
            expected_runbook_available=case.expected_runbook_available,
            selected_runbook_id=selected,
            runbook_available=bool(result.get("runbook_available")),
            must_not_violation=violation,
        ),
        retrieval_recall_at_3=retrieval.recall_at_3,
        must_not_violation=violation,
        symptom_query=result.get("symptom_query", ""),
    )


def _build_coverage_report(results: list[CoverageCaseResult]) -> CoverageEvalReport:
    total = len(results)
    e2e = sum(1 for r in results if r.passed) / max(total, 1)
    unavailable_cases = [r for r in results if not r.expected_runbook_available]
    unavailable_acc = sum(
        1 for r in unavailable_cases if not r.runbook_available
    ) / max(len(unavailable_cases), 1)
    selection_cases = [r for r in results if r.expected_doc_id]
    selection_acc = sum(
        1 for r in selection_cases
        if r.runbook_available and r.selected_runbook_id == r.expected_doc_id
    ) / max(len(selection_cases), 1)
    violations = sum(1 for r in results if r.must_not_violation) / max(total, 1)

    by_challenge: dict[str, dict[str, float]] = {}
    for r in results:
        bucket = by_challenge.setdefault(r.challenge_type, {"n": 0, "pass": 0})
        bucket["n"] += 1
        if r.passed:
            bucket["pass"] += 1
    for bucket in by_challenge.values():
        n = max(int(bucket["n"]), 1)
        bucket["end_to_end_accuracy"] = round(bucket.pop("pass", 0) / n, 4)

    return CoverageEvalReport(
        total=total,
        end_to_end_accuracy=e2e,
        runbook_unavailable_accuracy=unavailable_acc,
        selection_accuracy=selection_acc,
        must_not_violation_rate=violations,
        by_challenge=by_challenge,
        cases=results,
    )


def evaluate_coverage_golden(
    cases: list[Any],
    *,
    settings=None,
) -> CoverageEvalReport:
    results = [evaluate_coverage_case(c, settings=settings) for c in cases]
    return _build_coverage_report(results)


def evaluate_real_llm_golden(
    cases: list[Any],
    *,
    settings=None,
) -> CoverageEvalReport:
    results = [evaluate_real_llm_case(c, settings=settings) for c in cases]
    return _build_coverage_report(results)
