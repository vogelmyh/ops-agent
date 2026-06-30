"""ecomm-manager chaos: initial symptoms mimic rate-limit; correct patch reveals feature-flag fault."""

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

SCENARIO_ID = "ecomm-manager-chaos-morph"
SERVICE = "ecomm-manager"
CONFIG_KEY = "rate-limit.max-qps"
BASELINE_VALUE = "5000"
BROKEN_VALUE = "50"
BROKEN_QPS = 400.0
RECOVERED_QPS = 7800.0
FLAG_NAME = "promotion-v2"


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
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.fault_phase = FaultPhase.MASKED
        self.max_qps = BROKEN_VALUE
        self.admin_api_qps = BROKEN_QPS
        self.flag_enabled = True
        self.error_rate = 0.18
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return self.phase == Phase.RECOVERED and self.error_rate < 0.02

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1

        if action == "patch_config":
            key = body.get("config_key")
            value = body.get("config_value")
            if self.fault_phase != FaultPhase.MASKED:
                result = op_result(
                    service=SERVICE,
                    action=action,
                    message=(
                        "Rate limit already patched; elevated error rate is from "
                        f"unstable feature flag {FLAG_NAME}"
                    ),
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
                msg = (
                    f"Patched {CONFIG_KEY}={value}; config reload completed"
                )
            else:
                msg = (
                    f"Patched {CONFIG_KEY}={value} but baseline is {BASELINE_VALUE}; "
                    "rate limiting persists"
                )
            result = op_result(service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}")
            self.last_operation = result
            return result

        if action == "toggle_feature_flag":
            if self.fault_phase != FaultPhase.REVEALED:
                result = op_result(
                    service=SERVICE,
                    action=action,
                    message=(
                        f"{action} rejected: preconditions not met for current service state"
                    ),
                    status=OperationStatus.FAILED,
                    op_id=f"op-{self.op_counter}",
                )
                self.last_operation = result
                return result
            flag = body.get("flag_name")
            enabled = body.get("enabled")
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
            self.flag_enabled = bool(enabled)
            if enabled is False:
                self.phase = Phase.RECOVERED
                self.error_rate = 0.01
                msg = f"Disabled {FLAG_NAME}; error rate normalized"
            else:
                self.phase = Phase.BROKEN
                self.error_rate = 0.18
                msg = f"Enabled {FLAG_NAME}; unstable code path active"
            result = op_result(service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}")
            self.last_operation = result
            return result

        result = op_result(
            service=SERVICE,
            action=action,
            message=f"{action} not applicable for chaos-morph scenario",
            status=OperationStatus.FAILED,
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {
            "fault_phase": self.fault_phase.value,
            "max_qps": self.max_qps,
            "admin_api_qps": int(self.admin_api_qps),
            "flag_name": FLAG_NAME,
            "flag_enabled": self.flag_enabled,
            "error_rate": self.error_rate,
            "phase": self.phase.value,
        }


def _pods() -> list[PodStatus]:
    return [
        PodStatus(
            name=f"ecomm-manager-{i}",
            ready=True,
            restarts=0,
            phase="Running",
            image="registry/ecomm-manager:2.0.8",
        )
        for i in range(2)
    ]


def project_logs(state: State, req: LogQueryRequest) -> LogQueryResult:
    if state.phase == Phase.RECOVERED:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="INFO",
                message=f"feature flag {FLAG_NAME} disabled, error rate normalized",
                service=SERVICE,
            ),
        ]
    elif state.fault_phase == FaultPhase.MASKED:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="WARN",
                message="rate limit exceeded for merchant-api",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message=(
                    f"RateLimitFilter: threshold misconfigured max-qps={state.max_qps} "
                    f"expected={BASELINE_VALUE}"
                ),
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="INFO",
                message=f"admin api qps dropped to {int(state.admin_api_qps)} after config reload",
                service=SERVICE,
            ),
        ]
    else:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message="NullPointerException in PromotionService.applyDiscount",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="WARN",
                message=f"feature flag {FLAG_NAME} enabled, code path unstable",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="WARN",
                message="merchant admin api error rate elevated",
                service=SERVICE,
            ),
        ]
    if req.keyword:
        kw = req.keyword.lower()
        entries = [e for e in entries if kw in e.message.lower()]
    limit = min(req.limit, len(entries))
    return LogQueryResult(query=req, total=len(entries), entries=entries[:limit])


def project_status(state: State) -> ServiceStatus:
    if state.phase == Phase.RECOVERED:
        msg = "Merchant admin API error rate within baseline"
    elif state.fault_phase == FaultPhase.MASKED:
        msg = "Merchant admin API QPS below baseline; elevated latency on admin endpoints"
    else:
        msg = "Merchant admin API 5xx rate elevated; QPS within baseline"
    return ServiceStatus(
        service=SERVICE,
        healthy=True,
        replicas_ready=2,
        replicas_desired=2,
        pods=_pods(),
        message=msg,
    )


def project_metrics(state: State) -> MetricSeries:
    if state.phase == Phase.RECOVERED or state.fault_phase == FaultPhase.REVEALED:
        return MetricSeries(
            service=SERVICE,
            metric="error_rate",
            unit="ratio",
            points=[MetricPoint(timestamp=NOW, value=state.error_rate)],
        )
    return MetricSeries(
        service=SERVICE,
        metric="admin_api_qps",
        unit="req/s",
        points=[MetricPoint(timestamp=NOW, value=state.admin_api_qps)],
    )


def project_k8s_events(_state: State) -> K8sEventResult:
    return K8sEventResult(service=SERVICE, total=0, events=[])


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(service=SERVICE, action="none", message="No recent operation")


def project_streams(_state: State) -> list:
    return []
