"""REM — main-path remediation (mock LLM graph contract)."""

import pytest

from app.adapters.mock_data import set_mock_scenario
from app.graph.runner import resume_approval, start_diagnosis
from app.schemas import IncidentInput


@pytest.mark.parametrize(
    "service,scenario,expected_snippet,needs_approval",
    [
        ("ecomm-manager", "rate-limit", "限流", False),
        ("ecomm-order", "crashloop", "坏镜像", True),
        ("ecomm-order", "stream-paused", "暂停", False),
    ],
    ids=["REM-01-rate-limit", "REM-02-crashloop", "REM-01-stream-paused"],
)
def test_rem_low_or_high_risk_remediation(
    service, scenario, expected_snippet, needs_approval
):
    """REM-01: low-risk auto write+resolve; REM-02: high-risk approve then resolve."""
    set_mock_scenario(service, scenario)
    incident = IncidentInput(service=service, description=f"故障演练 {service}")
    thread_id, response, meta = start_diagnosis(incident)

    assert expected_snippet in response.root_cause
    assert response.evidence
    if needs_approval:
        assert meta["pending_interrupt"] is True
        assert response.status == "awaiting_approval"
        final = resume_approval(thread_id, approved=True)
        assert final.summary
    else:
        assert response.status == "completed"
