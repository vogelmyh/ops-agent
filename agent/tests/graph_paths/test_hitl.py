"""HITL — human-in-the-loop gates (mock LLM graph contract)."""

from app.adapters.mock_data import set_mock_scenario
from app.graph.runner import (
    resume_approval,
    resume_runbook_notes,
    resume_runbook_review,
    start_diagnosis,
)
from app.schemas import IncidentInput


def test_hitl_01_approval_rejected_no_write(thread_values):
    """HITL-01: high-risk rollback rejected → summarize without write."""
    set_mock_scenario("ecomm-manager", "crashloop")
    incident = IncidentInput(
        service="ecomm-manager",
        description="【P0】ecomm-manager 全部 Pod CrashLoopBackOff，持续 10 分钟",
    )
    thread_id, response, meta = start_diagnosis(incident)

    assert response.decide_outcome == "actionable"
    assert meta["pending_node"] == "approve"
    assert response.needs_approval is True
    assert response.pending_tool_calls[0]["name"] == "rollback_deployment"
    assert not response.execution_results

    final = resume_approval(thread_id, approved=False)
    assert final.status == "completed"
    assert not final.execution_results
    assert final.incident_resolved is not True

    state = thread_values(thread_id)
    assert (state.get("approval") or {}).get("approved") is False


def test_hitl_02_runbook_review_rejected(thread_values):
    """HITL-02: novel service → notes → draft → review reject → no ingest."""
    incident = IncidentInput(
        service="ecomm-search",
        description="【P2】ecomm-search 搜索延迟升高，索引任务失败",
    )
    thread_id, response, meta = start_diagnosis(incident)

    assert response.runbook_available is False
    assert response.decide_outcome == "skipped_low_confidence"
    assert meta["pending_node"] == "request_runbook_notes"

    response = resume_runbook_notes(thread_id, "Rebuilt search index from backup snapshot.")
    assert response.status == "awaiting_runbook_review"

    final = resume_runbook_review(thread_id, approved=False)
    assert final.status == "runbook_rejected"

    state = thread_values(thread_id)
    assert state.get("runbook_approved") is False
    assert not state.get("runbook_saved_path")
