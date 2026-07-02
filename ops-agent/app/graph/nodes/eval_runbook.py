"""Offline harness — retrieve runbooks + runbook coverage (Track B entry)."""

from __future__ import annotations

from app.config import get_settings
from app.graph.eval_schemas import RunbookCandidate
from app.graph.nodes.retrieve_runbooks import run_retrieve_runbooks
from app.graph.runbook_coverage import evaluate_runbook_coverage


def run_retrieve_and_coverage(
    service: str,
    incident_description: str,
    *,
    collected_data: dict | None = None,
    settings=None,
    golden_oracle: bool = False,
    oracle_expected_doc_id: str | None = None,
    oracle_expected_novel: bool = False,
) -> dict:
    """Retrieve top-K runbooks and evaluate runbook coverage (offline golden harness)."""
    settings = settings or get_settings()
    retrieved = run_retrieve_runbooks(
        service,
        incident_description,
        collected_data=collected_data,
        settings=settings,
    )
    candidates = [
        RunbookCandidate.model_validate(item)
        for item in retrieved.get("runbook_candidates", [])
    ]
    coverage = evaluate_runbook_coverage(
        service,
        incident_description,
        collected_data=retrieved["collected_data"],
        candidates=candidates,
        settings=settings,
        golden_oracle=golden_oracle,
        oracle_expected_doc_id=oracle_expected_doc_id,
        oracle_expected_novel=oracle_expected_novel,
    )
    return {
        **retrieved,
        **coverage,
        "status": "runbook_coverage_evaluated",
    }


run_runbook_eval = run_retrieve_and_coverage


def coverage_harness_node(state):  # pragma: no cover - deprecated graph node name
    from app.graph.state import AgentState

    service = state["service"]
    incident = state["incident"]
    return run_retrieve_and_coverage(service, incident.description, settings=get_settings())


eval_runbook_node = coverage_harness_node
