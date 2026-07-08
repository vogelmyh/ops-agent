"""Retrieve runbook candidates — collect telemetry and hybrid search (no LLM)."""

from __future__ import annotations

from app.config import get_settings
from app.graph.collection import (
    KNOWN_SERVICES,
    collect,
    extract_symptoms,
    retrieve_runbook_candidates,
    serialize_collected,
)
from app.graph.eval_schemas import RunbookCandidate
from app.graph.runbook_eval_policy import candidate_from_retrieval_dict
from app.graph.state import AgentState
from app.rag.ingest import extract_h1
from app.rag.store import DATA_DIR


def _mock_fallback_candidates(service: str) -> list[RunbookCandidate]:
    """Mock-only: load on-disk runbook when retrieval returns nothing."""
    paths = sorted((DATA_DIR / "runbooks").glob(f"{service}-*.md"))
    if not paths:
        return []
    path = paths[0]
    text = path.read_text(encoding="utf-8")
    return [candidate_from_retrieval_dict({
        "doc_id": path.stem,
        "title": extract_h1(text) or path.stem,
        "service": service,
        "chunk_type": "parent",
        "content": text,
        "rerank_score": 1.0,
    })]


def run_retrieve_runbooks(
    service: str,
    incident_description: str,
    *,
    collected_data: dict | None = None,
    settings=None,
) -> dict:
    """Collect telemetry and retrieve top-K runbook parent documents."""
    settings = settings or get_settings()
    data = dict(collected_data) if collected_data is not None else collect(service)

    symptom_query = extract_symptoms(
        service,
        data,
        incident_description=incident_description,
    )
    candidates = retrieve_runbook_candidates(service, symptom_query, settings)
    if settings.llm_is_mock and not candidates and service in KNOWN_SERVICES:
        candidates = _mock_fallback_candidates(service)

    return {
        "collected_data": serialize_collected(data),
        "symptom_query": symptom_query,
        "runbook_candidates": [c.model_dump() for c in candidates],
        "status": "runbooks_retrieved",
    }


def retrieve_runbooks_node(state: AgentState) -> dict:
    service = state["service"]
    incident = state["incident"]
    return run_retrieve_runbooks(
        service,
        incident.description,
        settings=get_settings(),
    )
