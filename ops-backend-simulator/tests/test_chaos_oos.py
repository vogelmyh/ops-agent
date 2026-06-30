"""State machine tests for ecomm-manager-chaos-oos (Type C-②)."""

from simulator.scenarios.ecomm_manager_chaos_oos import (
    BASELINE_VALUE,
    CONFIG_KEY,
    FaultPhase,
    State,
)


def test_oos_morph_to_logic_bug():
    s = State()
    result = s.apply_ops("patch_config", {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE})
    assert result.status.value == "SUCCEEDED"
    assert s.fault_phase == FaultPhase.REVEALED_LOGIC
    assert not s.is_recovered


def test_post_morph_ops_fail():
    s = State()
    s.apply_ops("patch_config", {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE})
    result = s.apply_ops("toggle_feature_flag", {"flag_name": "promotion-v2", "enabled": False})
    assert result.status.value == "FAILED"
    assert not s.is_recovered
