import os

import pytest

os.environ["BACKEND_MODE"] = "mock"
os.environ["LLM_MODE"] = "mock"
os.environ["EMBEDDINGS_PROVIDER"] = "local-hash"
os.environ["CHECKPOINTER"] = "memory"

from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario
from app.config import get_settings
from app.graph.decide_spec import DecideOutcome
from app.graph.nodes.decide import decide_node
from app.graph.nodes.eval_diagnosis import eval_diagnosis_node
from app.graph.nodes.eval_runbook import eval_runbook_node
from app.schemas import DecisionClass, IncidentInput
from app.tools.policy import pending_tool_calls
from app.adapters.mock_remediation import clear_remediated


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


def test_eval_diagnosis_known_service_confident():
    state = _base_state("ecomm-manager")
    state.update(eval_runbook_node(state))
    state.update({
        "root_cause": "限流阈值误配",
        "evidence": [],
    })
    result = eval_diagnosis_node(state)
    assert result["needs_human_review"] is False


def test_eval_diagnosis_novel_ambiguous_requires_review():
    state = _base_state("ecomm-catalog")
    state.update(eval_runbook_node(state))
    state.update({
        "root_cause": "商品目录索引损坏",
        "evidence": [],
        "novel_scenario": True,
    })
    result = eval_diagnosis_node(state)
    assert result["needs_human_review"] is True


def test_eval_diagnosis_novel_confident_no_review():
    state = _base_state("ecomm-cache")
    state.update(eval_runbook_node(state))
    state.update({
        "root_cause": "Redis 缓存 Pod OOMKilled，频繁重启导致连接失败",
        "evidence": [],
        "novel_scenario": True,
    })
    result = eval_diagnosis_node(state)
    assert result["needs_human_review"] is False


def test_decide_ecomm_catalog_uncertain():
    state = _base_state("ecomm-catalog")
    state.update({"root_cause": "目录服务异常", "needs_human_review": True})
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
    state.update({"root_cause": "test root cause", "needs_human_review": False})
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

    incident = IncidentInput(service="ecomm-catalog", description="【P2】ecomm-catalog 商品目录 API 错误率升高，查询超时增多")
    thread_id, response, meta = start_diagnosis(incident)
    assert meta["pending_interrupt"] is True
    assert meta["pending_node"] == "request_runbook_notes"
    assert response.decide_outcome == DecideOutcome.UNCERTAIN.value
    assert response.decision_class == DecisionClass.UNCERTAIN.value
    assert not response.pending_tool_calls

    drafted = resume_runbook_notes(thread_id, "Identified large logs under /var/log; retention policy applied.")
    assert drafted.status == "awaiting_runbook_review"
    final = resume_runbook_review(thread_id, approved=True)
    assert final.status == "completed"
