"""State machine tests for ecomm-manager-cascade-exhaust (LOOP-03)."""

from simulator.scenarios.ecomm_manager_cascade_exhaust import (
    BASELINE_VALUE,
    CONFIG_KEY,
    FLAG_NAME,
    FaultLayer,
    LOG_PATH,
    Phase,
    State,
)


def test_cascade_never_recovers_after_three_writes():
    s = State()
    s.apply_ops("patch_config", {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE})
    assert s.fault_layer == FaultLayer.FEATURE_FLAG
    s.apply_ops("toggle_feature_flag", {"flag_name": FLAG_NAME, "enabled": False})
    assert s.fault_layer == FaultLayer.DISK_FULL
    s.apply_ops(
        "cleanup_storage",
        {"path": LOG_PATH, "retention_days": 7},
    )
    assert s.fault_layer == FaultLayer.CONN_LEAK
    assert s.phase == Phase.BROKEN
    assert not s.is_recovered


def test_patch_advances_from_rate_limit():
    s = State()
    result = s.apply_ops("patch_config", {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE})
    assert result.status.value == "SUCCEEDED"
    assert s.fault_layer == FaultLayer.FEATURE_FLAG
    assert s.admin_api_qps > 3000
