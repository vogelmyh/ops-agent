"""KB — knowledge / runbook lifecycle (mock LLM graph contract)."""

from app.graph.runner import (
    resume_runbook_notes,
    resume_runbook_review,
    start_diagnosis,
)
from app.schemas import IncidentInput


def test_kb_01_novel_ambiguous_runbook_writeback(thread_values):
    """KB-01: novel + ambiguous diagnosis → uncertain → notes → review approve → ingest."""
    incident = IncidentInput(
        service="ecomm-search",
        description="【P1】ecomm-search 商品搜索 P99 延迟超 5s，索引重建任务失败",
    )
    thread_id, response, meta = start_diagnosis(incident)

    assert response.novel_scenario is True
    assert response.decide_outcome == "uncertain"
    assert not response.pending_tool_calls
    assert meta["pending_node"] == "request_runbook_notes"

    response = resume_runbook_notes(
        thread_id,
        "Identified stale search index; rebuilt from backup snapshot.",
    )
    assert response.status == "awaiting_runbook_review"

    final = resume_runbook_review(thread_id, approved=True)
    assert final.status == "completed"
    assert thread_values(thread_id).get("runbook_saved_path")


def test_kb_02_novel_actionable_then_runbook_writeback(thread_values):
    """KB-02: novel + clear OOM pattern → actionable fix → summarize → runbook writeback."""
    incident = IncidentInput(
        service="ecomm-cache",
        description="【P1】ecomm-cache Redis 缓存连接失败，读延迟飙升，Pod 频繁重启",
    )
    thread_id, response, meta = start_diagnosis(incident)

    assert response.novel_scenario is True
    assert response.decide_outcome == "actionable"
    assert response.pending_tool_calls[0]["name"] == "restart_pods"
    assert response.incident_resolved is True
    assert meta["pending_node"] == "request_runbook_notes"

    response = resume_runbook_notes(
        thread_id,
        "OOMKilled pod; rolling restart recovered cache connections.",
    )
    assert response.status == "awaiting_runbook_review"

    final = resume_runbook_review(thread_id, approved=True)
    assert final.status == "completed"
    assert thread_values(thread_id).get("runbook_saved_path")
