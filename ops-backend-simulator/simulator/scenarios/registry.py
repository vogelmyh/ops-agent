"""Scenario registry — load scenario modules by id."""

from __future__ import annotations

from types import ModuleType

from simulator.scenarios import (
    ecomm_manager_cascade_exhaust,
    ecomm_manager_chaos_morph,
    ecomm_manager_chaos_oos,
    ecomm_manager_crashloop,
    ecomm_manager_discount_bug,
    ecomm_manager_disk_full,
    ecomm_manager_feature_flag,
    ecomm_manager_rate_limit,
    ecomm_order_crashloop,
    ecomm_order_memory_leak,
    ecomm_order_payment_circuit,
    ecomm_order_rds_timeout,
    ecomm_order_stream_paused,
)

DEFAULT_SCENARIO_ID = "ecomm-manager-rate-limit"

_MODULES: list[ModuleType] = [
    ecomm_manager_rate_limit,
    ecomm_manager_feature_flag,
    ecomm_manager_chaos_morph,
    ecomm_manager_cascade_exhaust,
    ecomm_manager_chaos_oos,
    ecomm_manager_crashloop,
    ecomm_manager_discount_bug,
    ecomm_manager_disk_full,
    ecomm_order_stream_paused,
    ecomm_order_memory_leak,
    ecomm_order_payment_circuit,
    ecomm_order_crashloop,
    ecomm_order_rds_timeout,
]

SCENARIOS: dict[str, ModuleType] = {m.SCENARIO_ID: m for m in _MODULES}


def get_scenario(scenario_id: str) -> ModuleType:
    if scenario_id not in SCENARIOS:
        raise KeyError(scenario_id)
    return SCENARIOS[scenario_id]


def list_scenarios() -> list[dict[str, str]]:
    return [{"id": m.SCENARIO_ID, "service": m.SERVICE} for m in _MODULES]
