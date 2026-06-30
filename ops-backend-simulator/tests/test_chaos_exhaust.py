"""State machine tests for ecomm-manager-chaos-exhaust (Type C-①)."""

from simulator.scenarios.ecomm_manager_chaos_exhaust import (
    BASELINE_VALUE,
    CONFIG_KEY,
    FLAG_NAME,
    FaultPhase,
    Phase,
    State,
)


def test_exhaust_never_recovers():
    s = State()
    s.apply_ops("patch_config", {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE})
    s.apply_ops("toggle_feature_flag", {"flag_name": FLAG_NAME, "enabled": False})
    s.apply_ops("restart_pods", {"strategy": "rolling"})
    assert s.phase == Phase.BROKEN
    assert not s.is_recovered
    assert s.error_rate >= 0.1


def test_patch_reveals_phase_b():
    s = State()
    result = s.apply_ops("patch_config", {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE})
    assert result.status.value == "SUCCEEDED"
    assert s.fault_phase == FaultPhase.REVEALED
    assert not s.is_recovered
