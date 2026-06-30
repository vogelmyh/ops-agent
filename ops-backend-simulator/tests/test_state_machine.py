"""State machine unit tests (L1)."""

from simulator.scenarios.ecomm_manager_rate_limit import (
    BASELINE_VALUE,
    BROKEN_QPS,
    BROKEN_VALUE,
    CONFIG_KEY,
    Phase,
    RECOVERED_QPS,
    State as ManagerRateLimitState,
)


def test_ecomm_manager_rate_limit_initial_state_is_broken():
    s = ManagerRateLimitState()
    assert s.phase == Phase.BROKEN
    assert s.max_qps == BROKEN_VALUE
    assert s.admin_api_qps == BROKEN_QPS


def test_ecomm_manager_rate_limit_patch_config_recovers():
    s = ManagerRateLimitState()
    result = s.apply_ops(
        "patch_config",
        {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE},
    )
    assert result.status.value == "SUCCEEDED"
    assert s.phase == Phase.RECOVERED
    assert s.admin_api_qps == RECOVERED_QPS
    assert s.is_recovered


def test_ecomm_manager_rate_limit_wrong_patch_stays_broken():
    s = ManagerRateLimitState()
    s.apply_ops("patch_config", {"config_key": CONFIG_KEY, "config_value": BROKEN_VALUE})
    assert s.phase == Phase.BROKEN
    assert not s.is_recovered


def test_ecomm_manager_rate_limit_wrong_key_stays_broken():
    s = ManagerRateLimitState()
    s.apply_ops("patch_config", {"config_key": "other.key", "config_value": BASELINE_VALUE})
    assert s.phase == Phase.BROKEN
    assert not s.is_recovered


def test_reset_restores_broken():
    s = ManagerRateLimitState()
    s.apply_ops("patch_config", {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE})
    s.reset()
    assert s.phase == Phase.BROKEN
