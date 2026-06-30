"""Projection consistency tests (L2)."""

from simulator.schemas import LogQueryRequest
from simulator.scenarios.ecomm_manager_rate_limit import (
    BASELINE_QPS,
    BASELINE_VALUE,
    BROKEN_QPS,
    BROKEN_VALUE,
    CONFIG_KEY,
    SERVICE,
    State,
    project_k8s_events,
    project_logs,
    project_metrics,
    project_status,
)


def test_broken_logs_mention_misconfiguration():
    state = State()
    result = project_logs(state, LogQueryRequest(service=SERVICE, limit=10))
    messages = " ".join(e.message for e in result.entries)
    assert BROKEN_VALUE in messages
    assert str(int(BASELINE_QPS)) in messages
    assert "rate limit" in messages.lower()


def test_recovered_logs_no_rate_limit_error():
    state = State()
    state.apply_ops(
        "patch_config",
        {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE},
    )
    result = project_logs(state, LogQueryRequest(service=SERVICE, limit=10))
    messages = " ".join(e.message for e in result.entries)
    assert "recovered" in messages.lower()
    assert "misconfigured" not in messages.lower()


def test_broken_metrics_low_qps_recovered_high():
    broken = State()
    broken_metrics = project_metrics(broken)
    assert broken_metrics.points[-1].value < 3000

    recovered = State()
    recovered.apply_ops(
        "patch_config",
        {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE},
    )
    recovered_metrics = project_metrics(recovered)
    assert recovered_metrics.points[-1].value >= 3000


def test_status_healthy_in_both_phases_no_crashloop():
    broken = project_status(State())
    assert broken.healthy is True
    assert broken.replicas_ready == 2
    assert all(p.phase == "Running" for p in broken.pods)

    recovered = State()
    recovered.apply_ops(
        "patch_config",
        {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE},
    )
    ok = project_status(recovered)
    assert "recovered" in (ok.message or "").lower() or "rate limit" in (ok.message or "").lower()


def test_k8s_events_empty_for_ecomm_manager_rate_limit():
    result = project_k8s_events(State())
    assert result.total == 0
    assert result.events == []


def test_log_keyword_filter():
    state = State()
    all_logs = project_logs(state, LogQueryRequest(service=SERVICE, limit=10))
    filtered = project_logs(state, LogQueryRequest(service=SERVICE, keyword="rate", limit=10))
    assert filtered.total <= all_logs.total
    assert all("rate" in e.message.lower() for e in filtered.entries)
