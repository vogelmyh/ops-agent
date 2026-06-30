import os

import pytest

os.environ.setdefault("BACKEND_MODE", "mock")

from app.adapters.backend_client import BackendClient
from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario
from app.config import get_settings
from app.schemas import LogQueryRequest
from app.tools.log_tools import query_app_logs, query_k8s_events
from app.tools.status_tools import get_service_status, get_stream_states


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    reset_mock_scenarios()
    get_settings.cache_clear()
    yield
    reset_mock_scenarios()
    get_settings.cache_clear()


def test_query_app_logs_ecomm_manager_rate_limit():
    set_mock_scenario("ecomm-manager", "rate-limit")
    result = query_app_logs.invoke({"service": "ecomm-manager", "keyword": "rate", "limit": 5})
    assert result["total"] >= 1
    assert any("rate" in e["message"].lower() for e in result["entries"])


def test_query_app_logs_ecomm_order_contains_app_errors():
    """ecomm-order app logs should contain process-level startup errors, NOT K8s BackOff messages."""
    set_mock_scenario("ecomm-order", "crashloop")
    result = query_app_logs.invoke({"service": "ecomm-order"})
    messages = [e["message"] for e in result["entries"]]
    assert any("startup" in m.lower() or "failed" in m.lower() for m in messages), (
        "Expected application startup error in app logs"
    )
    assert not any("CrashLoopBackOff" in m or "Back-off restarting" in m for m in messages), (
        "K8s BackOff events should not appear in application logs"
    )


def test_query_k8s_events_ecomm_order():
    """ecomm-order K8s events should contain infrastructure-layer events."""
    set_mock_scenario("ecomm-order", "crashloop")
    result = query_k8s_events.invoke({"service": "ecomm-order"})
    assert result["total"] >= 1
    reasons = [ev["reason"] for ev in result["events"]]
    assert "BackOff" in reasons, "Expected CrashLoop BackOff event in K8s events"


def test_query_k8s_events_ecomm_manager_rate_limit_empty():
    """ecomm-manager rate-limit is healthy at infra level; K8s events should be empty."""
    set_mock_scenario("ecomm-manager", "rate-limit")
    result = query_k8s_events.invoke({"service": "ecomm-manager"})
    assert result["total"] == 0


def test_service_status_ecomm_order_crashloop():
    set_mock_scenario("ecomm-order", "crashloop")
    status = get_service_status.invoke({"service": "ecomm-order"})
    assert status["replicas_ready"] == 0
    assert status["pods"][0]["phase"] == "CrashLoopBackOff"


def test_stream_states_ecomm_order_paused():
    set_mock_scenario("ecomm-order", "stream-paused")
    streams = get_stream_states.invoke({"service": "ecomm-order"})
    assert any(s["status"] == "PAUSED" for s in streams)


def test_backend_client_query_app_logs():
    set_mock_scenario("ecomm-order", "stream-paused")
    client = BackendClient()
    logs = client.query_app_logs(LogQueryRequest(service="ecomm-order", limit=10))
    assert logs.total >= 1


def test_backend_client_query_k8s_events():
    set_mock_scenario("ecomm-order", "crashloop")
    client = BackendClient()
    result = client.query_k8s_events("ecomm-order")
    assert result.total >= 1
    assert result.events[0].service == "ecomm-order"
