import os

import pytest

os.environ["BACKEND_MODE"] = "mock"
os.environ["LLM_MODE"] = "mock"
os.environ["EMBEDDINGS_PROVIDER"] = "local-hash"
os.environ["CHECKPOINTER"] = "memory"

from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario
from app.adapters.mock_remediation import clear_remediated
from app.config import get_settings
from app.graph.decide_spec import DecideOutcome
from app.graph.nodes.decide import decide_node
from app.graph.nodes.diagnose import SKIPPED_LOW_CONFIDENCE, diagnose_node
from app.graph.nodes.eval_runbook import eval_runbook_node
from app.graph.nodes.retrieve_runbooks import retrieve_runbooks_node
from app.schemas import DecisionClass, IncidentInput
from app.tools.policy import compute_needs_approval, pending_tool_calls


@pytest.fixture(autouse=True)
def _reset_caches():
    from app.graph.builder import build_graph
    from app.memory.short_term import get_checkpointer

    clear_remediated()
    reset_mock_scenarios()
    get_settings.cache_clear()
    build_graph.cache_clear()
    get_checkpointer.cache_clear()
    yield
    clear_remediated()
    reset_mock_scenarios()
    get_settings.cache_clear()
    build_graph.cache_clear()
    get_checkpointer.cache_clear()


def _base_state(service: str) -> dict:
    return {
        "service": service,
        "incident": IncidentInput(service=service, description=f"test {service}"),
    }


@pytest.mark.parametrize("service,expected_novel", [
    ("ecomm-manager", False),
    ("ecomm-order", False),
    ("ecomm-catalog", True),
])
def test_eval_runbook_novel_scenario(service, expected_novel):
    result = eval_runbook_node(_base_state(service))
    assert result["novel_scenario"] is expected_novel
    assert result["collected_data"]
    if expected_novel:
        assert result.get("novel_reason")
        assert result.get("runbook_eval_reasoning")
    else:
        assert result.get("runbook_eval_reasoning")
        assert result.get("selected_runbook_id")
        assert result.get("coverage_confidence") is not None


def test_diagnose_ecomm_manager_confident():
    state = _base_state("ecomm-manager")
    state.update(retrieve_runbooks_node(state))
    result = diagnose_node(state)
    assert result["confidence_sufficient"] is True
    assert result["needs_human_review"] is False
    assert result.get("decide_outcome") is None


def test_diagnose_ecomm_search_low_confidence_skips_decide():
    state = _base_state("ecomm-search")
    state.update(retrieve_runbooks_node(state))
    result = diagnose_node(state)
    assert result["novel_scenario"] is True
    assert result["confidence_sufficient"] is False
    assert result["needs_human_review"] is True
    assert result["decide_outcome"] == SKIPPED_LOW_CONFIDENCE


def test_diagnose_ecomm_cache_confident_novel():
    state = _base_state("ecomm-cache")
    state.update(retrieve_runbooks_node(state))
    result = diagnose_node(state)
    assert result["novel_scenario"] is True
    assert result["confidence_sufficient"] is True
    assert result.get("decide_outcome") is None


def test_decide_ecomm_catalog_uncertain():
    state = _base_state("ecomm-catalog")
    state.update({"root_cause": "目录服务异常", "novel_scenario": True})
    result = decide_node(state)
    assert result["decide_outcome"] == DecideOutcome.UNCERTAIN.value
    assert result["decision_class"] == DecisionClass.UNCERTAIN.value
    assert pending_tool_calls(result.get("messages", [])) == []
    assert result["recommendations"]
    assert result["knowledge_gaps"]


@pytest.mark.parametrize("service,scenario,tool_name,decision_class", [
    ("ecomm-manager", "rate-limit", "patch_config", DecisionClass.EXECUTE),
    ("ecomm-order", "crashloop", "rollback_deployment", DecisionClass.APPROVE),
    ("ecomm-order", "stream-paused", "resume_event_stream", DecisionClass.EXECUTE),
])
def test_decide_actionable_services(service, scenario, tool_name, decision_class):
    set_mock_scenario(service, scenario)
    state = _base_state(service)
    state.update({"root_cause": "test root cause", "novel_scenario": False})
    result = decide_node(state)
    assert result["decide_outcome"] == DecideOutcome.ACTIONABLE.value
    assert result["decision_class"] == decision_class.value
    assert pending_tool_calls(result["messages"])[0]["name"] == tool_name


def test_novel_scenario_ecomm_catalog_completes_to_runbook():
    from app.graph.runner import (
        resume_runbook_notes,
        resume_runbook_review,
        start_diagnosis,
    )

    incident = IncidentInput(
        service="ecomm-catalog",
        description="【P2】ecomm-catalog 商品目录 API 错误率升高，查询超时增多",
    )
    thread_id, response, meta = start_diagnosis(incident)
    assert meta["pending_interrupt"] is True
    assert meta["pending_node"] == "request_runbook_notes"
    assert response.decide_outcome == SKIPPED_LOW_CONFIDENCE
    assert not response.pending_tool_calls

    drafted = resume_runbook_notes(thread_id, "Identified large logs under /var/log; retention policy applied.")
    assert drafted.status == "awaiting_runbook_review"
    final = resume_runbook_review(thread_id, approved=True)
    assert final.status == "completed"


def test_policy_novel_requires_approval():
    tool_calls = [{"name": "restart_pods", "args": {"service": "ecomm-cache"}}]
    assert compute_needs_approval({"novel_scenario": True}, tool_calls) is True
    assert compute_needs_approval({"novel_scenario": False}, tool_calls) is False
