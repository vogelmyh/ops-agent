"""Phase B: interactive simulator lab."""

from __future__ import annotations

from typing import Any

import httpx

import scenario_runtime as rt
from demo_presenter import console

# Default POST bodies for ops lab (service filled from admin state).
OPS_SAMPLES: dict[str, dict[str, Any]] = {
    "rollback_deployment": {"target_version": "v1.2.0"},
    "scale_deployment": {"replicas": 3},
    "restart_deployment": {"strategy": "rolling"},
    "delete_pod": {"pod_name": "ecomm-manager-0", "grace_period_seconds": 30},
    "cordon_node": {"node_name": "worker-node-1"},
    "drain_node": {"node_name": "worker-node-1", "force": False, "delete_emptydir": False},
    "enable_circuit_breaker": {"upstream": "payment-gw", "state": "open"},
    "flush_cache": {"cache_key_pattern": "catalog:*"},
    "patch_config": {"config_key": "rate_limit.qps", "config_value": "500"},
    "toggle_feature_flag": {"flag_name": "discount_v2", "enabled": False},
}

LAB_MENU: dict[str, str] = {
    "health": "GET /actuator/health",
    "scenarios": "GET /admin/scenarios",
    "state": "GET /admin/state",
    "reset": "POST /admin/reset",
    "ops": "POST /api/v1/ops/{action}",
    "done": "完成实验室，进入剧本目录",
}


def _active_service(client: httpx.Client) -> str:
    state = rt.lab_admin_state(client)
    return state.get("service") or "ecomm-manager"


def _run_ops(client: httpx.Client) -> None:
    actions = sorted(OPS_SAMPLES)
    choices = {a: a for a in actions}
    action = console.prompt_choice("选择 ops action", choices)
    if not action:
        return
    body = dict(OPS_SAMPLES[action])
    body["service"] = _active_service(client)
    print(f"  POST /api/v1/ops/{action}")
    print(f"  body: {body}")
    if not console.prompt_yes_no("确认发送？", default=False):
        return
    result = rt.lab_ops_action(client, action, body)
    print(f"  → status={result.get('status')} message={result.get('message', '')[:120]}")


def run_lab(client: httpx.Client) -> None:
    console.heading("Simulator 实验室 (B)")
    print("  可先探查健康检查、加载场景、手动触发 ops 写操作。")
    while True:
        choice = console.prompt_choice("实验室操作", LAB_MENU)
        if choice is None or choice == "done":
            break
        if choice == "health":
            print(f"  {rt.lab_health(client)}")
        elif choice == "scenarios":
            for row in rt.lab_list_scenarios(client):
                print(f"    - {row.get('id')}: {row.get('title', row.get('name', ''))}")
        elif choice == "state":
            import json

            print(json.dumps(rt.lab_admin_state(client), ensure_ascii=False, indent=2)[:2000])
        elif choice == "reset":
            print(rt.lab_reset(client))
        elif choice == "ops":
            _run_ops(client)
