"""ecomm-manager Type C-①: morph after rate-limit patch; catalog tools never resolve incident."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from simulator.schemas import (
    K8sEventResult,
    LogEntry,
    LogQueryRequest,
    LogQueryResult,
    MetricPoint,
    MetricSeries,
    OperationResult,
    OperationStatus,
    PodStatus,
    ServiceStatus,
)
from simulator.scenarios.common import NOW, Phase, op_result
from simulator.scenarios import ecomm_manager_chaos_morph as morph

SCENARIO_ID = "ecomm-manager-chaos-exhaust"
SERVICE = morph.SERVICE
CONFIG_KEY = morph.CONFIG_KEY
BASELINE_VALUE = morph.BASELINE_VALUE
BROKEN_VALUE = morph.BROKEN_VALUE
BROKEN_QPS = morph.BROKEN_QPS
RECOVERED_QPS = morph.RECOVERED_QPS
FLAG_NAME = morph.FLAG_NAME


class FaultPhase(str, Enum):
    MASKED = "MASKED"
    REVEALED = "REVEALED"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    fault_phase: FaultPhase = FaultPhase.MASKED
    max_qps: str = BROKEN_VALUE
    admin_api_qps: float = BROKEN_QPS
    flag_enabled: bool = True
    error_rate: float = 0.18
    restart_count: int = 0
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.fault_phase = FaultPhase.MASKED
        self.max_qps = BROKEN_VALUE
        self.admin_api_qps = BROKEN_QPS
        self.flag_enabled = True
        self.error_rate = 0.18
        self.restart_count = 0
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return False

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1

        if action == "patch_config":
            key = body.get("config_key")
            value = body.get("config_value")
            if self.fault_phase != FaultPhase.MASKED:
                result = op_result(
                    service=SERVICE,
                    action=action,
                    message="Config patch already applied for rate-limit key",
                    status=OperationStatus.FAILED,
                    op_id=f"op-{self.op_counter}",
                )
                self.last_operation = result
                return result
            if key != CONFIG_KEY:
                result = op_result(
                    service=SERVICE,
                    action=action,
                    message=f"Unknown config_key {key!r}; expected {CONFIG_KEY}",
                    status=OperationStatus.FAILED,
                    op_id=f"op-{self.op_counter}",
                )
                self.last_operation = result
                return result
            self.max_qps = str(value)
            if str(value) == BASELINE_VALUE:
                self.fault_phase = FaultPhase.REVEALED
                self.admin_api_qps = RECOVERED_QPS
                msg = f"Patched {CONFIG_KEY}={value}; config reload completed"
            else:
                msg = (
                    f"Patched {CONFIG_KEY}={value} but baseline is {BASELINE_VALUE}; "
                    "rate limiting persists"
                )
            result = op_result(
                service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}"
            )
            self.last_operation = result
            return result

        if action == "toggle_feature_flag":
            if self.fault_phase != FaultPhase.REVEALED:
                result = op_result(
                    service=SERVICE,
                    action=action,
                    message=f"{action} rejected: preconditions not met for current service state",
                    status=OperationStatus.FAILED,
                    op_id=f"op-{self.op_counter}",
                )
                self.last_operation = result
                return result
            flag = body.get("flag_name")
            if flag != FLAG_NAME:
                result = op_result(
                    service=SERVICE,
                    action=action,
                    message=f"Unknown flag_name {flag!r}; expected {FLAG_NAME}",
                    status=OperationStatus.FAILED,
                    op_id=f"op-{self.op_counter}",
                )
                self.last_operation = result
                return result
            self.flag_enabled = bool(body.get("enabled"))
            self.error_rate = 0.17 if self.flag_enabled is False else 0.19
            msg = (
                f"Updated {FLAG_NAME} enabled={self.flag_enabled}; "
                "merchant API error rate remains elevated"
            )
            result = op_result(
                service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}"
            )
            self.last_operation = result
            return result

        if action == "restart_pods":
            if self.fault_phase != FaultPhase.REVEALED:
                result = op_result(
                    service=SERVICE,
                    action=action,
                    message=f"{action} rejected: preconditions not met for current service state",
                    status=OperationStatus.FAILED,
                    op_id=f"op-{self.op_counter}",
                )
                self.last_operation = result
                return result
            self.restart_count += 1
            self.error_rate = max(0.12, self.error_rate - 0.02)
            msg = "Rolling restart completed; error rate dipped but remains above baseline"
            result = op_result(
                service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}"
            )
            self.last_operation = result
            return result

        result = op_result(
            service=SERVICE,
            action=action,
            message=f"{action} not applicable for chaos-exhaust scenario",
            status=OperationStatus.FAILED,
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {
            "chaos_type": "C-exhaust",
            "fault_phase": self.fault_phase.value,
            "max_qps": self.max_qps,
            "admin_api_qps": int(self.admin_api_qps),
            "flag_name": FLAG_NAME,
            "flag_enabled": self.flag_enabled,
            "error_rate": self.error_rate,
            "restart_count": self.restart_count,
            "phase": self.phase.value,
            "recoverable": False,
        }


def _morph_shadow(state: State) -> morph.State:
    return morph.State(
        phase=state.phase,
        fault_phase=morph.FaultPhase(state.fault_phase.value),
        max_qps=state.max_qps,
        admin_api_qps=state.admin_api_qps,
        flag_enabled=state.flag_enabled,
        error_rate=state.error_rate,
    )


def project_logs(state: State, req: LogQueryRequest) -> LogQueryResult:
    return morph.project_logs(_morph_shadow(state), req)


def project_status(state: State) -> ServiceStatus:
    return morph.project_status(_morph_shadow(state))


def project_metrics(state: State) -> MetricSeries:
    return morph.project_metrics(_morph_shadow(state))


def project_k8s_events(_state: State) -> K8sEventResult:
    return morph.project_k8s_events(_state)


def project_streams(_state: State) -> list:
    return morph.project_streams(_state)


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(service=SERVICE, action="none", message="No recent operation")
