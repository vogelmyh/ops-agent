import os

import pytest

os.environ["BACKEND_MODE"] = "mock"
os.environ["LLM_MODE"] = "mock"

from langchain_core.messages import AIMessage, ToolMessage

from app.adapters.mock_data import reset_mock_scenarios
from app.adapters.mock_remediation import (
    block_remediation,
    clear_remediated,
    is_remediated,
    mark_remediated,
)
from app.graph.nodes.eval_remediation import eval_remediation_node
from app.schemas import IncidentInput


@pytest.fixture(autouse=True)
def _reset_mock_remediation():
    clear_remediated()
    reset_mock_scenarios()
    yield
    clear_remediated()
    reset_mock_scenarios()


def _state_after_write(service: str) -> dict:
    return {
        "service": service,
        "incident": IncidentInput(service=service, description="test"),
        "root_cause": "test root cause",
        "remediation_attempt": 0,
        "remediation_history": [],
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "patch_config", "args": {}, "id": "c1"}],
            ),
            ToolMessage(
                content='{"status": "SUCCEEDED", "message": "Mock config patch"}',
                tool_call_id="c1",
            ),
        ],
    }


def test_eval_remediation_resolved_ecomm_manager():
    mark_remediated("ecomm-manager")
    result = eval_remediation_node(_state_after_write("ecomm-manager"))
    assert result["incident_resolved"] is True
    assert result["remediation_attempt"] == 1


def test_eval_remediation_unresolved_without_mark():
    block_remediation("ecomm-manager")
    result = eval_remediation_node(_state_after_write("ecomm-manager"))
    assert result["incident_resolved"] is False
    assert result["remediation_history"][0]["resolved"] is False


def test_block_remediation_prevents_recovery():
    block_remediation("ecomm-manager")
    result = eval_remediation_node(_state_after_write("ecomm-manager"))
    assert is_remediated("ecomm-manager") is False
    assert result["incident_resolved"] is False
    assert result["remediation_history"][0]["tools_attempted"] == ["patch_config"]
