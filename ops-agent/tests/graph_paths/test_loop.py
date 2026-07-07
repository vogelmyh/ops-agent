"""LOOP — remediation feedback loop (mock LLM graph contract)."""

from app.adapters.mock_remediation import block_remediation
from app.config import get_settings
from app.graph.runner import resume_approval, start_diagnosis
from app.schemas import IncidentInput


def test_loop_01_retry_exhausted_without_resolution(thread_values):
    """LOOP-01: mock-only graph contract — verify react loop exhausts (see test-scenario-trajectories §LOOP-01).

    Intentionally repeats patch_config each round (mock oracle ignores DECIDE_RETRY_GUIDANCE).
    Not a real-LLM characterization scenario.
    """
    block_remediation("ecomm-manager")

    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager admin_api_qps 低于阈值，持续 10 分钟",
    )
    thread_id, response, meta = start_diagnosis(incident)

    assert meta["pending_interrupt"] is True
    assert meta["pending_node"] == "approve"
    assert response.incident_resolved is False
    assert response.remediation_attempt == 1
    assert response.pending_tool_calls[0]["name"] == "patch_config"

    history = (thread_values(thread_id).get("remediation_history") or [])
    assert len(history) == 1
    assert history[0]["resolved"] is False

    final = response
    for _ in range(5):
        if final.status == "completed":
            break
        final = resume_approval(thread_id, approved=True)
    else:
        raise AssertionError("graph did not reach completed status")

    assert final.incident_resolved is False
    assert final.remediation_attempt == get_settings().max_remediation_attempts
    history = (thread_values(thread_id).get("remediation_history") or [])
    assert len(history) == get_settings().max_remediation_attempts
    assert all(not h["resolved"] for h in history)
    assert "not resolved after 3 attempt" in final.summary


def test_loop_02_morph_recovers_via_two_tools(chaos_morph_env, thread_values, resume_until_approved):
    """LOOP-02: patch_config → morph → toggle_feature_flag → resolved (demo)."""
    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降超 80%，持续 15 分钟",
    )
    thread_id, response, meta = start_diagnosis(incident)

    assert response.runbook_available is True
    assert response.decide_outcome == "actionable"
    assert response.remediation_attempt == 1
    assert meta["pending_node"] == "approve"
    assert response.pending_tool_calls[0]["name"] == "toggle_feature_flag"

    admin = chaos_morph_env.get("/admin/state").json()
    assert admin["details"]["fault_phase"] == "REVEALED"

    final = resume_until_approved(thread_id, response)
    assert final.incident_resolved is True
    assert final.remediation_attempt == 2

    history = thread_values(thread_id).get("remediation_history") or []
    assert len(history) == 2
    assert history[1]["resolved"] is True

    sim_after = chaos_morph_env.get("/admin/state").json()
    assert sim_after.get("phase") == "RECOVERED"


def test_loop_03_exhaust_never_resolves(cascade_exhaust_env, thread_values, resume_until_approved):
    """LOOP-03: cascade layers after each write; 3 rounds; incident stays unresolved."""
    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降超 80%，持续 15 分钟",
    )
    thread_id, response, meta = start_diagnosis(incident)

    assert response.decide_outcome == "actionable"
    assert response.remediation_attempt == 1
    assert response.incident_resolved is False

    final = resume_until_approved(thread_id, response)
    assert final.incident_resolved is False
    assert final.remediation_attempt == get_settings().max_remediation_attempts

    history = thread_values(thread_id).get("remediation_history") or []
    assert len(history) == 3
    assert all(not h["resolved"] for h in history)

    admin = cascade_exhaust_env.get("/admin/state").json()
    assert admin.get("phase") == "BROKEN"
    assert admin["details"].get("fault_layer") == "CONN_LEAK"
    assert admin["details"].get("recoverable") is False
