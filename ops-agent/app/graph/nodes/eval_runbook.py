"""Legacy eval_runbook entry — retrieval + diagnose Step1 for offline harness."""

from __future__ import annotations

from app.config import get_settings
from app.graph.diagnose_runbook_step import run_diagnose_step1
from app.graph.eval_schemas import RunbookCandidate
from app.graph.nodes.retrieve_runbooks import run_retrieve_runbooks


def run_runbook_eval(
    service: str,
    incident_description: str,
    *,
    collected_data: dict | None = None,
    settings=None,
    golden_oracle: bool = False,
    oracle_expected_doc_id: str | None = None,
    oracle_expected_novel: bool = False,
) -> dict:
    """Retrieve top-K runbooks and run diagnose Step1 rubric finalize (harness / tests)."""
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
    step1 = run_diagnose_step1(
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
        **step1,
        "status": "runbook_evaluated",
    }


def eval_runbook_node(state):  # pragma: no cover - deprecated graph node name
    from app.graph.state import AgentState

    service = state["service"]
    incident = state["incident"]
    return run_runbook_eval(service, incident.description, settings=get_settings())
