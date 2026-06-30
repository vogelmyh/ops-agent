"""State machine tests for ecomm-manager-chaos-morph scenario."""

from simulator.scenarios.ecomm_manager_chaos_morph import (
    BASELINE_VALUE,
    BROKEN_QPS,
    BROKEN_VALUE,
    CONFIG_KEY,
    FLAG_NAME,
    FaultPhase,
    Phase,
    State,
)


def test_chaos_morph_initial_masked_symptoms():
    s = State()
    assert s.fault_phase == FaultPhase.MASKED
    assert s.phase == Phase.BROKEN
    assert s.admin_api_qps == BROKEN_QPS


def test_patch_config_reveals_feature_flag_fault():
    s = State()
    result = s.apply_ops(
        "patch_config",
        {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE},
    )
    assert result.status.value == "SUCCEEDED"
    assert s.fault_phase == FaultPhase.REVEALED
    assert s.phase == Phase.BROKEN
    assert s.admin_api_qps > 3000
    assert s.error_rate >= 0.1
    assert not s.is_recovered


def test_toggle_flag_before_reveal_fails():
    s = State()
    result = s.apply_ops(
        "toggle_feature_flag",
        {"flag_name": FLAG_NAME, "enabled": False},
    )
    assert result.status.value == "FAILED"
    assert s.fault_phase == FaultPhase.MASKED


def test_full_recovery_after_two_step_remediation():
    s = State()
    s.apply_ops(
        "patch_config",
        {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE},
    )
    result = s.apply_ops(
        "toggle_feature_flag",
        {"flag_name": FLAG_NAME, "enabled": False},
    )
    assert result.status.value == "SUCCEEDED"
    assert s.phase == Phase.RECOVERED
    assert s.is_recovered
    assert s.error_rate < 0.02


def test_metrics_switch_after_reveal():
    from simulator.scenarios import ecomm_manager_chaos_morph as mod

    masked = State()
    masked_metrics = mod.project_metrics(masked)
    assert masked_metrics.metric == "admin_api_qps"

    revealed = State()
    revealed.apply_ops(
        "patch_config",
        {"config_key": CONFIG_KEY, "config_value": BASELINE_VALUE},
    )
    revealed_metrics = mod.project_metrics(revealed)
    assert revealed_metrics.metric == "error_rate"
