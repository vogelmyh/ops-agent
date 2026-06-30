"""DEC — decide termination paths (mock LLM graph contract)."""

from app.graph.runner import start_diagnosis
from app.schemas import IncidentInput


def test_dec_02_oos_early_exit(chaos_oos_env, thread_values):
    """DEC-02: patch_config morph → second decide out_of_scope → single write."""
    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降，修复后订单金额告警增多",
    )
    thread_id, response, meta = start_diagnosis(incident)

    assert response.status == "completed"
    assert response.decide_outcome == "out_of_scope"
    assert response.incident_resolved is False
    assert response.remediation_attempt == 1
    assert len(response.execution_results or []) == 1
    assert response.execution_results[0].get("action") == "patch_config"

    history = thread_values(thread_id).get("remediation_history") or []
    assert len(history) == 1

    admin = chaos_oos_env.get("/admin/state").json()
    assert admin["details"].get("fault_phase") == "REVEALED_LOGIC"
    assert admin["details"].get("out_of_scope") is True
